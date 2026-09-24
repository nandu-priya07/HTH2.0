import os
import uuid
import logging
from pathlib import Path
from typing import Dict, Any
from fastapi import APIRouter, File, UploadFile, status
from fastapi.responses import JSONResponse

from file_processing.pipeline import process_file, FileProcessingError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["upload"])

# Base uploads directory: backend/uploads/raw
BASE_DIR = Path(__file__).resolve().parent.parent
UPLOAD_DIR = BASE_DIR / "uploads" / "raw"

ALLOWED_EXTENSIONS = {".csv", ".xlsx", ".xls"}

# In-memory Dataset Registry for backend consumption
DATASET_REGISTRY: Dict[str, Dict[str, Any]] = {}

@router.post("/upload")
async def upload_file(file: UploadFile = File(None)):
    # 1. Validate file presence
    if not file or not file.filename or file.filename.strip() == "":
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"success": False, "error": "No file uploaded"}
        )

    filename = file.filename
    ext = os.path.splitext(filename)[1].lower()

    # 2. Validate file extension
    if ext not in ALLOWED_EXTENSIONS:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "success": False,
                "error": "Unsupported file type. Only CSV and Excel files are allowed."
            }
        )

    # 3. Read file contents and check for empty file
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

    # 4. Generate unique dataset_id and save raw file
    dataset_id = str(uuid.uuid4())
    clean_ext = ext.lstrip(".")
    stored_filename = f"{dataset_id}.{clean_ext}"

    try:
        os.makedirs(UPLOAD_DIR, exist_ok=True)
        file_path = UPLOAD_DIR / stored_filename
        with open(file_path, "wb") as f:
            f.write(content)
    except Exception as e:
        logger.error(f"Error writing raw file: {e}")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"success": False, "error": "Failed to save file to server storage"}
        )

    # 5. Execute 4-Stage File Processing Pipeline
    try:
        process_result = process_file(
            file_path=file_path,
            dataset_id=dataset_id,
            original_filename=filename
        )
    except FileProcessingError as e:
        logger.error(f"File processing failed for {dataset_id} at stage [{e.stage}]: {e.error}")
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "success": False,
                "stage": e.stage,
                "error": f"Dataset processing error during [{e.stage}]: {e.error}"
            }
        )
    except Exception as e:
        logger.error(f"Unhandled file processing error for {dataset_id}: {e}")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "success": False,
                "stage": "processing",
                "error": "Internal error during dataset processing"
            }
        )

    # 6. Store in server-side DATASET_REGISTRY
    DATASET_REGISTRY[dataset_id] = {
        "dataset_id": dataset_id,
        "filename": filename,
        "stored_filename": stored_filename,
        "processed_filename": process_result["processed_filename"],
        "file_path": str(file_path),
        "status": "processed",
        "result": process_result,
        "data": process_result["data"]  # Standardized pd.DataFrame held in memory
    }

    # 7. Return JSON response (Without sending entire 10k-row DataFrame)
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "success": True,
            "dataset_id": dataset_id,
            "filename": filename,
            "stored_filename": stored_filename,
            "processed_filename": process_result["processed_filename"],
            "file_type": clean_ext,
            "file_size": file_size,
            "status": "processed",
            "metadata": process_result["metadata"],
            "schema": process_result["schema"],
            "profile": process_result["profile"],
            "cleaning_report": process_result["cleaning_report"]
        }
    )

@router.get("/dataset/{dataset_id}")
async def get_dataset_info(dataset_id: str):
    if dataset_id not in DATASET_REGISTRY:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"success": False, "error": f"Dataset '{dataset_id}' not found in registry"}
        )

    ds_info = DATASET_REGISTRY[dataset_id]
    res = ds_info["result"]
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "success": True,
            "dataset_id": dataset_id,
            "filename": ds_info["filename"],
            "status": ds_info["status"],
            "metadata": res["metadata"],
            "schema": res["schema"],
            "profile": res["profile"],
            "cleaning_report": res["cleaning_report"]
        }
    )
