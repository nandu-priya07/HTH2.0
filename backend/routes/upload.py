import os
import uuid
import json
import logging
import tempfile
from pathlib import Path
from typing import Dict, Any, Optional, List
from fastapi import APIRouter, File, Form, UploadFile, status, HTTPException
from fastapi.responses import JSONResponse

from file_processing.pipeline import process_file, FileProcessingError
from storage.dataset_manager import (
    DATASET_REGISTRY,
    BASE_DIR,
    register_dataset,
    save_dataset_meta,
    persist_dataset_to_supabase,
    get_or_load_dataset,
    list_all_datasets,
    generate_suggestions
)
from services.storage_service import SupabaseStorageService
from chat import get_chat_service
from chat.models import utc_now_iso
from auth import is_persistent_session, current_user, current_guest_id
from file_processing.insights_generator import generate_dataset_insights
from file_processing.decision_generator import generate_dataset_decisions

logger = logging.getLogger(__name__)

router = APIRouter(tags=["upload"])

ALLOWED_EXTENSIONS = {".csv", ".xlsx", ".xls"}
STORAGE_CHATS_DIR = BASE_DIR / "storage" / "chats"
RAW_DIR = BASE_DIR / "uploads" / "raw"
PROCESSED_DIR = BASE_DIR / "uploads" / "processed"
UPLOAD_DIR = RAW_DIR


def _get_session_dataset(dataset_id: str):
    service = get_chat_service()
    for conversation in service.list_conversations(limit=500):
        attached = {item.get("file_id") for item in service.get_files(conversation.id)}
        if conversation.dataset_id == dataset_id or dataset_id in attached:
            return get_or_load_dataset(dataset_id, chat_id=conversation.id)
    # Check directly by dataset_id
    return get_or_load_dataset(dataset_id)


def process_and_store_chat_file(
    content: bytes,
    filename: str,
    chat_id: str
) -> tuple[Dict[str, Any], Dict[str, Any]]:
    """
    Saves raw and cleaned dataset files to Supabase Storage and PostgreSQL master tables,
    indexes schema, and registers file metadata in conversation history.
    """
    user = current_user()
    user_id = str(user["id"]) if user else current_guest_id() or "guest"
    ext = os.path.splitext(filename)[1].lower()
    clean_ext = ext.lstrip(".")
    file_id = f"file_{uuid.uuid4().hex[:8]}"

    storage_service = SupabaseStorageService()

    # 1. Process file through pipeline in a temporary directory
    with tempfile.TemporaryDirectory(prefix="hth-upload-") as tmp_dir:
        tmp_path = Path(tmp_dir)
        raw_tmp_path = tmp_path / f"{file_id}.raw.{clean_ext}"
        with open(raw_tmp_path, "wb") as f:
            f.write(content)

        process_result = process_file(
            file_path=raw_tmp_path,
            dataset_id=file_id,
            original_filename=filename,
            processed_dir=tmp_path
        )
        processed_tmp_path = tmp_path / process_result["processed_filename"]
        with open(processed_tmp_path, "rb") as pf:
            processed_bytes = pf.read()

    # 2. Register in memory dataset registry & persist to Supabase PostgreSQL master datasets table FIRST
    # (Required so Foreign Key constraint on public.dataset_files(dataset_id) references an existing dataset row)
    dataset_entry = {
        "dataset_id": file_id,
        "filename": filename,
        "stored_filename": f"{file_id}.{clean_ext}",
        "processed_filename": process_result["processed_filename"],
        "file_path": f"{user_id}/{chat_id}/{file_id}/processed/{process_result['processed_filename']}",
        "file_type": clean_ext,
        "file_size": len(content),
        "status": "processed",
        "result": process_result,
        "data": process_result["data"],
        "metadata": process_result["metadata"],
        "schema": process_result["schema"],
        "profile": process_result["profile"],
        "cleaning_report": process_result["cleaning_report"]
    }
    register_dataset(file_id, dataset_entry)
    persist_dataset_to_supabase(file_id, dataset_entry, chat_id=chat_id, user_id=user_id)

    # 3. Upload RAW file to Supabase Storage
    raw_storage_path = storage_service.build_storage_path(
        chat_id=chat_id, dataset_id=file_id, file_role="raw", filename=filename, user_id=user_id
    )
    storage_service.upload_file(
        storage_path=raw_storage_path,
        content=content,
        file_type=clean_ext,
        file_role="raw",
        dataset_id=file_id,
        chat_id=chat_id,
        user_id=user_id
    )

    # 4. Upload PROCESSED file to Supabase Storage
    processed_storage_path = storage_service.build_storage_path(
        chat_id=chat_id, dataset_id=file_id, file_role="processed", filename=process_result["processed_filename"], user_id=user_id
    )
    storage_service.upload_file(
        storage_path=processed_storage_path,
        content=processed_bytes,
        file_type="csv",
        file_role="processed",
        dataset_id=file_id,
        chat_id=chat_id,
        user_id=user_id
    )

    # 5. Upload METADATA artifact to Supabase Storage
    meta_json_bytes = json.dumps({
        "dataset_id": file_id,
        "filename": filename,
        "file_type": clean_ext,
        "file_size": len(content),
        "schema": process_result["schema"],
        "metadata": process_result["metadata"],
        "profile": process_result["profile"],
        "cleaning_report": process_result["cleaning_report"]
    }).encode("utf-8")
    meta_storage_path = storage_service.build_storage_path(
        chat_id=chat_id, dataset_id=file_id, file_role="metadata", filename="schema.json", user_id=user_id
    )
    storage_service.upload_file(
        storage_path=meta_storage_path,
        content=meta_json_bytes,
        file_type="json",
        file_role="metadata",
        dataset_id=file_id,
        chat_id=chat_id,
        user_id=user_id
    )

    file_meta = {
        "file_id": file_id,
        "filename": filename,
        "stored_filename": f"{file_id}.{clean_ext}",
        "processed_filename": process_result["processed_filename"],
        "storage_path": raw_storage_path,
        "processed_path": processed_storage_path,
        "file_type": clean_ext,
        "file_size": len(content),
        "schema": process_result["schema"],
        "metadata": process_result["metadata"],
        "profile": process_result["profile"],
        "cleaning_report": process_result["cleaning_report"],
        "created_at": utc_now_iso()
    }

    # 6. Register in chat conversation repository
    service = get_chat_service()
    service.add_file(chat_id, file_meta)

    return file_meta, process_result


@router.get("/api/datasets")
@router.get("/datasets")
async def get_datasets_list():
    """
    Returns list of all active/processed datasets with their schema and metadata summaries.
    """
    try:
        datasets = list_all_datasets()
        service = get_chat_service()
        conversations = service.list_conversations()
        allowed = {file.get("file_id") for conv in conversations for file in service.get_files(conv.id)}
        allowed.update(conv.dataset_id for conv in conversations if conv.dataset_id)
        if is_persistent_session():
            datasets = [item for item in datasets if item.get("dataset_id") in allowed or True]
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "success": True,
                "datasets": datasets,
                "total": len(datasets)
            }
        )
    except Exception as e:
        logger.error(f"Error listing datasets: {e}")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"success": False, "error": f"Failed to retrieve datasets: {str(e)}"}
        )


@router.post("/chats/{chat_id}/files")
@router.post("/api/chats/{chat_id}/files")
@router.post("/api/conversations/{chat_id}/files")
async def upload_file_to_chat(
    chat_id: str,
    file: UploadFile = File(...)
):
    """
    POST /chats/{chat_id}/files
    Uploads a file for a specific chat and persists to Supabase Storage & PostgreSQL.
    """
    if not file or not file.filename or file.filename.strip() == "":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No file uploaded")

    filename = file.filename
    ext = os.path.splitext(filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported file type. Only CSV and Excel files are allowed."
        )

    try:
        content = await file.read()
        if len(content) == 0:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Uploaded file is empty")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to read uploaded file: {str(e)}")

    service = get_chat_service()
    conv = service.get_conversation(chat_id)
    if not conv:
        conv = service.create_conversation(conversation_id=chat_id, title="New Chat")

    try:
        file_meta, process_result = process_and_store_chat_file(content, filename, chat_id)
        service.associate_dataset(chat_id, file_meta["file_id"])
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "success": True,
                "chat_id": chat_id,
                "file_id": file_meta["file_id"],
                "dataset_id": file_meta["file_id"],
                "filename": filename,
                "file_type": file_meta["file_type"],
                "file_size": file_meta["file_size"],
                "storage_path": file_meta["storage_path"],
                "schema": file_meta["schema"],
                "metadata": file_meta["metadata"],
                "profile": file_meta["profile"],
                "cleaning_report": file_meta["cleaning_report"]
            }
        )
    except FileProcessingError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Dataset processing error during [{e.stage}]: {e.error}")
    except Exception as e:
        logger.error(f"Error processing file upload for chat {chat_id}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal error processing dataset file")


@router.get("/chats/{chat_id}/files")
@router.get("/api/chats/{chat_id}/files")
@router.get("/api/conversations/{chat_id}/files")
async def get_chat_files(chat_id: str):
    """
    GET /chats/{chat_id}/files
    Retrieves all files associated with a specific chat.
    """
    service = get_chat_service()
    conv = service.get_conversation(chat_id)
    if not conv:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Chat '{chat_id}' not found")

    files = service.get_files(chat_id)
    return JSONResponse(status_code=status.HTTP_200_OK, content={"chat_id": chat_id, "files": files})


@router.delete("/chats/{chat_id}/files/{file_id}")
@router.delete("/api/chats/{chat_id}/files/{file_id}")
@router.delete("/api/conversations/{chat_id}/files/{file_id}")
async def delete_chat_file(chat_id: str, file_id: str):
    """
    DELETE /chats/{chat_id}/files/{file_id}
    Removes a file reference from conversation files and deletes from Supabase Storage & PostgreSQL.
    """
    service = get_chat_service()
    deleted = service.delete_file(chat_id, file_id)
    storage_service = SupabaseStorageService()
    storage_service.delete_dataset_files(file_id)

    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"File '{file_id}' not found in chat '{chat_id}'")
    return {"success": True, "chat_id": chat_id, "file_id": file_id, "message": "File deleted"}


@router.post("/api/upload")
async def upload_file(
    file: UploadFile = File(None),
    conversation_id: Optional[str] = Form(None)
):
    """
    Legacy API endpoint for dataset upload using Supabase backend.
    """
    if not file or not file.filename or file.filename.strip() == "":
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"success": False, "error": "No file uploaded"}
        )

    filename = file.filename
    ext = os.path.splitext(filename)[1].lower()

    if ext not in ALLOWED_EXTENSIONS:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "success": False,
                "error": "Unsupported file type. Only CSV and Excel files are allowed."
            }
        )

    try:
        content = await file.read()
        file_size = len(content)
        if file_size == 0:
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={"success": False, "error": "Uploaded file is empty"}
            )
    except Exception as e:
        logger.error(f"Error reading upload stream: {e}")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"success": False, "error": "Failed to read uploaded file"}
        )

    service = get_chat_service()
    cid = conversation_id
    if not cid:
        title = filename.rsplit(".", 1)[0].replace("_", " ").title()
        conv = service.create_conversation(title=title)
        cid = conv.id

    try:
        file_meta, process_result = process_and_store_chat_file(content, filename, cid)
        file_id = file_meta["file_id"]
        service.associate_dataset(cid, file_id)

        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "success": True,
                "dataset_id": file_id,
                "file_id": file_id,
                "conversation_id": cid,
                "filename": filename,
                "stored_filename": file_meta["stored_filename"],
                "processed_filename": file_meta["processed_filename"],
                "file_type": file_meta["file_type"],
                "file_size": file_size,
                "status": "processed",
                "metadata": process_result["metadata"],
                "schema": process_result["schema"],
                "profile": process_result["profile"],
                "cleaning_report": process_result["cleaning_report"]
            }
        )
    except FileProcessingError as e:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "success": False,
                "stage": e.stage,
                "error": f"Dataset processing error during [{e.stage}]: {e.error}"
            }
        )
    except Exception as e:
        logger.error(f"Unhandled file processing error: {e}")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"success": False, "stage": "processing", "error": "Internal error during dataset processing"}
        )


@router.get("/api/dataset/{dataset_id}")
async def get_dataset_info(dataset_id: str):
    """
    Returns full metadata, schema, and profile for a specific dataset.
    """
    ds_info = _get_session_dataset(dataset_id)
    if not ds_info:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"success": False, "error": f"Dataset '{dataset_id}' not found in registry"}
        )

    res = ds_info.get("result", {})
    metadata = ds_info.get("metadata") or res.get("metadata", {})
    schema = ds_info.get("schema") or res.get("schema", {})
    profile = ds_info.get("profile") or res.get("profile", {})
    cleaning_report = ds_info.get("cleaning_report") or res.get("cleaning_report", {})

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "success": True,
            "dataset_id": dataset_id,
            "filename": ds_info.get("filename", f"{dataset_id}.csv"),
            "status": ds_info.get("status", "processed"),
            "metadata": metadata,
            "schema": schema,
            "profile": profile,
            "cleaning_report": cleaning_report
        }
    )


@router.get("/api/dataset/{dataset_id}/suggestions")
async def get_dataset_suggestions_endpoint(dataset_id: str):
    """
    Generates dynamic analytical question suggestions based on the dataset's schema and column types.
    """
    ds_info = _get_session_dataset(dataset_id)
    if not ds_info:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"success": False, "error": f"Dataset '{dataset_id}' not found in registry"}
        )

    schema = ds_info.get("schema") or ds_info.get("result", {}).get("schema")
    profile = ds_info.get("profile") or ds_info.get("result", {}).get("profile")

    suggestions = generate_suggestions(schema, profile)

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "success": True,
            "dataset_id": dataset_id,
            "suggestions": suggestions
        }
    )


@router.get("/api/dataset/{dataset_id}/insights")
async def get_dataset_insights_endpoint(dataset_id: str):
    """
    Returns dynamically computed analytical insights, comparisons, time-series trends,
    and outlier anomalies for the requested dataset.
    """
    ds_info = _get_session_dataset(dataset_id)
    if not ds_info:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"success": False, "error": f"Dataset '{dataset_id}' not found in registry"}
        )

    df = ds_info.get("data")
    schema = ds_info.get("schema") or ds_info.get("result", {}).get("schema", {})
    profile = ds_info.get("profile") or ds_info.get("result", {}).get("profile", {})

    insights = generate_dataset_insights(df=df, schema=schema, profile=profile, dataset_id=dataset_id)
    return JSONResponse(status_code=status.HTTP_200_OK, content={"success": True, **insights})


@router.get("/api/dataset/{dataset_id}/decisions")
async def get_dataset_decisions_endpoint(dataset_id: str):
    """
    Returns dynamically computed evidence-backed decision findings,
    comparisons, concentration, trends, and anomalies for the requested dataset.
    """
    ds_info = _get_session_dataset(dataset_id)
    if not ds_info:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"success": False, "error": f"Dataset '{dataset_id}' not found in registry"}
        )

    df = ds_info.get("data")
    schema = ds_info.get("schema") or ds_info.get("result", {}).get("schema", {})
    profile = ds_info.get("profile") or ds_info.get("result", {}).get("profile", {})

    decisions = generate_dataset_decisions(df=df, schema=schema, profile=profile, dataset_id=dataset_id)
    return JSONResponse(status_code=status.HTTP_200_OK, content={"success": True, **decisions})
