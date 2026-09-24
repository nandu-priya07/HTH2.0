"""
API Route for Natural Language Query Processing and Analytics Execution.
Powered by local Ollama Qwen3:8b model and deterministic Pandas executor.
"""

import logging
from typing import Any, Dict, List, Optional
from pydantic import BaseModel
from fastapi import APIRouter, status
from fastapi.responses import JSONResponse

from analyst import process_query_with_llm, execute_query, LLMResponse, QueryResult, ResponseType
from storage.dataset_manager import get_or_load_dataset

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["query"])


class QueryRequest(BaseModel):
    question: Optional[str] = None
    message: Optional[str] = None
    dataset_id: Optional[str] = None


@router.post("/query")
@router.post("/chat")
async def execute_user_query(payload: QueryRequest):
    """
    Main endpoint for Qwen3:8b query routing and Pandas analytics execution.
    """
    raw_query = (payload.question or payload.message or "").strip()
    if not raw_query:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"type": "error", "error": "Question or message cannot be empty."}
        )

    # 1. Retrieve Dataset
    dataset_info = get_or_load_dataset(payload.dataset_id)
    if not dataset_info:
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "type": "direct_answer",
                "status": "no_dataset",
                "answer": "Please upload a CSV or Excel dataset first before asking data-analysis questions. Click the **+** button below to attach a file.",
                "text": "Please upload a CSV or Excel dataset first before asking data-analysis questions. Click the **+** button below to attach a file."
            }
        )

    schema = dataset_info.get("schema") or dataset_info.get("result", {}).get("schema")
    profile = dataset_info.get("profile") or dataset_info.get("result", {}).get("profile")
    df = dataset_info.get("data")
    ds_id = dataset_info.get("dataset_id")

    # 2. Call Qwen3:8b Query Processor
    try:
        llm_resp: LLMResponse = process_query_with_llm(
            question=raw_query,
            schema=schema,
            profile=profile,
            df=df,
            dataset_id=ds_id
        )
    except ConnectionError as e:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "type": "error",
                "status": "error",
                "error": "The local query model is currently unavailable. Please make sure Ollama is running.",
                "text": "The local query model is currently unavailable. Please make sure Ollama is running."
            }
        )
    except Exception as e:
        logger.error(f"Error processing query with Qwen3: {e}")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "type": "error",
                "status": "error",
                "error": f"An error occurred while processing your query: {str(e)}",
                "text": f"An error occurred while processing your query: {str(e)}"
            }
        )

    # 3. Handle Direct Answer
    if llm_resp.type == ResponseType.DIRECT_ANSWER.value or llm_resp.type == "direct_answer":
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "type": "direct_answer",
                "status": "conversational",
                "answer": llm_resp.answer,
                "text": llm_resp.answer,
                "dataset_id": ds_id
            }
        )

    # 4. Handle Clarification
    if llm_resp.type == ResponseType.CLARIFICATION.value or llm_resp.type == "clarification":
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "type": "clarification",
                "status": "clarification",
                "answer": llm_resp.answer,
                "text": llm_resp.answer,
                "dataset_id": ds_id
            }
        )

    # 5. Handle Data Query -> Execute with Pandas
    if llm_resp.type == ResponseType.DATA_QUERY.value or llm_resp.type == "data_query":
        query_spec = llm_resp.query
        if not query_spec:
            return JSONResponse(
                status_code=status.HTTP_200_OK,
                content={
                    "type": "clarification",
                    "status": "clarification",
                    "answer": "Could you please specify which metric or column you would like to analyze?",
                    "text": "Could you please specify which metric or column you would like to analyze?",
                    "dataset_id": ds_id
                }
            )

        exec_res: QueryResult = execute_query(query_spec, df)

        if not exec_res.success:
            return JSONResponse(
                status_code=status.HTTP_200_OK,
                content={
                    "type": "error",
                    "status": "error",
                    "error": exec_res.error,
                    "text": f"Error executing query: {exec_res.error}",
                    "dataset_id": ds_id
                }
            )

        # Build response payload for frontend
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "type": "data_result",
                "status": "success",
                "query": exec_res.query,
                "result": exec_res.result,
                "table": exec_res.table,
                "scalar": exec_res.scalar,
                "list": exec_res.list,
                "text": exec_res.text,
                "metadata": exec_res.metadata,
                "dataset_id": ds_id
            }
        )

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "type": "direct_answer",
            "answer": llm_resp.answer or "I processed your request.",
            "text": llm_resp.answer or "I processed your request.",
            "dataset_id": ds_id
        }
    )
