"""
API Route for Natural Language Query Processing and Analytics Execution.
Powered by local Ollama Qwen3:8b model, deterministic Pandas executor, and persistent conversation management.
"""

import logging
from typing import Any, Dict, List, Optional
from pydantic import BaseModel
from fastapi import APIRouter, status
from fastapi.responses import JSONResponse

from analyst import process_query_with_llm, execute_query, execute_queries, LLMResponse, QueryResult, ResponseType
from storage.dataset_manager import get_or_load_dataset
from visualization.selector import select_visualizations
from chat import get_chat_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["query"])


class QueryRequest(BaseModel):
    question: Optional[str] = None
    message: Optional[str] = None
    dataset_id: Optional[str] = None
    conversation_id: Optional[str] = None


@router.post("/query")
@router.post("/chat")
async def execute_user_query(payload: QueryRequest):
    """
    Main endpoint for Qwen3:8b query routing, Pandas analytics execution, and conversation history persistence.
    Supports single queries, multi-queries, and multi-column conditional counts.
    """
    raw_query = (payload.question or payload.message or "").strip()
    if not raw_query:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"type": "error", "error": "Question or message cannot be empty."}
        )

    # 1. Initialize Chat Service & Conversation Session
    chat_service = get_chat_service()
    conversation = chat_service.handle_query_session(
        conversation_id=payload.conversation_id,
        user_message_text=raw_query,
        dataset_id=payload.dataset_id
    )
    cid = conversation.id

    # 2. Persist User Message
    user_msg = chat_service.add_user_message(conversation_id=cid, content=raw_query)

    # 3. Resolve Target Dataset from Conversation or Payload
    # The active conversation is the primary source of truth for dataset association
    target_dataset_id = payload.dataset_id or conversation.dataset_id

    dataset_info = None
    if target_dataset_id:
        dataset_info = get_or_load_dataset(target_dataset_id)

    if not dataset_info:
        no_ds_text = "Please upload a CSV or Excel dataset first before asking data-analysis questions. Click the **+** button below to attach a file."
        assistant_msg = chat_service.add_assistant_message(
            conversation_id=cid,
            content=no_ds_text
        )
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "conversation_id": cid,
                "user_message": user_msg.to_dict(),
                "assistant_message": assistant_msg.to_dict(),
                "type": "direct_answer",
                "status": "no_dataset",
                "answer": no_ds_text,
                "text": no_ds_text,
                "dataset_id": None
            }
        )

    schema = dataset_info.get("schema") or dataset_info.get("result", {}).get("schema")
    profile = dataset_info.get("profile") or dataset_info.get("result", {}).get("profile")
    df = dataset_info.get("data")
    ds_id = dataset_info.get("dataset_id")

    # Ensure conversation permanently associates this dataset_id
    if ds_id and conversation.dataset_id != ds_id:
        chat_service.associate_dataset(conversation_id=cid, dataset_id=ds_id)

    # 4. Call Qwen3:8b Query Processor
    try:
        llm_resp: LLMResponse = process_query_with_llm(
            question=raw_query,
            schema=schema,
            profile=profile,
            df=df,
            dataset_id=ds_id
        )
    except ConnectionError as e:
        err_text = "The local query model is currently unavailable. Please make sure Ollama is running."
        assistant_msg = chat_service.add_assistant_message(
            conversation_id=cid,
            content=err_text
        )
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "conversation_id": cid,
                "user_message": user_msg.to_dict(),
                "assistant_message": assistant_msg.to_dict(),
                "type": "error",
                "status": "error",
                "error": err_text,
                "text": err_text
            }
        )
    except Exception as e:
        logger.error(f"Error processing query with Qwen3: {e}")
        err_text = f"An error occurred while processing your query: {str(e)}"
        assistant_msg = chat_service.add_assistant_message(
            conversation_id=cid,
            content=err_text
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "conversation_id": cid,
                "user_message": user_msg.to_dict(),
                "assistant_message": assistant_msg.to_dict(),
                "type": "error",
                "status": "error",
                "error": err_text,
                "text": err_text
            }
        )

    # 5. Handle Direct Answer
    if llm_resp.type == ResponseType.DIRECT_ANSWER.value or llm_resp.type == "direct_answer":
        answer_text = llm_resp.answer or "I processed your request."
        assistant_msg = chat_service.add_assistant_message(
            conversation_id=cid,
            content=answer_text
        )
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "conversation_id": cid,
                "user_message": user_msg.to_dict(),
                "assistant_message": assistant_msg.to_dict(),
                "type": "direct_answer",
                "status": "conversational",
                "answer": answer_text,
                "text": answer_text,
                "dataset_id": ds_id
            }
        )

    # 6. Handle Clarification
    if llm_resp.type == ResponseType.CLARIFICATION.value or llm_resp.type == "clarification":
        answer_text = llm_resp.answer or "Could you please clarify your question?"
        assistant_msg = chat_service.add_assistant_message(
            conversation_id=cid,
            content=answer_text
        )
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "conversation_id": cid,
                "user_message": user_msg.to_dict(),
                "assistant_message": assistant_msg.to_dict(),
                "type": "clarification",
                "status": "clarification",
                "answer": answer_text,
                "text": answer_text,
                "dataset_id": ds_id
            }
        )

    # 7. Handle Data Query -> Execute with Pandas
    if llm_resp.type == ResponseType.DATA_QUERY.value or llm_resp.type == "data_query":
        queries = llm_resp.all_queries
        if not queries:
            clarify_text = "Could you please specify which metric or column you would like to analyze?"
            assistant_msg = chat_service.add_assistant_message(
                conversation_id=cid,
                content=clarify_text
            )
            return JSONResponse(
                status_code=status.HTTP_200_OK,
                content={
                    "conversation_id": cid,
                    "user_message": user_msg.to_dict(),
                    "assistant_message": assistant_msg.to_dict(),
                    "type": "clarification",
                    "status": "clarification",
                    "answer": clarify_text,
                    "text": clarify_text,
                    "dataset_id": ds_id
                }
            )

        exec_res: QueryResult = execute_queries(queries, df)

        if not exec_res.success:
            err_text = f"Error executing query: {exec_res.error}"
            assistant_msg = chat_service.add_assistant_message(
                conversation_id=cid,
                content=err_text
            )
            return JSONResponse(
                status_code=status.HTTP_200_OK,
                content={
                    "conversation_id": cid,
                    "user_message": user_msg.to_dict(),
                    "assistant_message": assistant_msg.to_dict(),
                    "type": "error",
                    "status": "error",
                    "error": exec_res.error,
                    "text": err_text,
                    "dataset_id": ds_id
                }
            )

        # 8. Select Visualization(s) based on result & schema
        primary_spec = queries[0] if queries else None
        visualizations = select_visualizations(
            spec=primary_spec,
            query_result=exec_res,
            schema=schema,
            df=df,
            raw_question=raw_query
        )
        primary_vis = visualizations[0] if visualizations else None

        # 9. Persist Assistant Message with Analytical Result & Visualization Metadata
        structured_result = {
            "query": exec_res.query,
            "queries": exec_res.queries,
            "result": exec_res.result,
            "results": exec_res.results,
            "table": exec_res.table,
            "tables": exec_res.tables,
            "scalar": exec_res.scalar,
            "scalars": exec_res.scalars,
            "list": exec_res.list,
            "metadata": exec_res.metadata
        }

        assistant_msg = chat_service.add_assistant_message(
            conversation_id=cid,
            content=exec_res.text or "Here are your analytical results.",
            result_json=structured_result,
            visualization_json=primary_vis or visualizations
        )

        # Build comprehensive response payload for frontend
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "conversation_id": cid,
                "user_message": user_msg.to_dict(),
                "assistant_message": assistant_msg.to_dict(),
                "type": "data_result",
                "status": "success",
                "query": exec_res.query,
                "queries": exec_res.queries,
                "result": exec_res.result,
                "results": exec_res.results,
                "table": exec_res.table,
                "tables": exec_res.tables,
                "scalar": exec_res.scalar,
                "scalars": exec_res.scalars,
                "list": exec_res.list,
                "text": exec_res.text,
                "metadata": exec_res.metadata,
                "dataset_id": ds_id,
                "visualization": primary_vis,
                "visualizations": visualizations
            }
        )

    # Fallback generic direct answer
    fallback_text = llm_resp.answer or "I processed your request."
    assistant_msg = chat_service.add_assistant_message(
        conversation_id=cid,
        content=fallback_text
    )
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "conversation_id": cid,
            "user_message": user_msg.to_dict(),
            "assistant_message": assistant_msg.to_dict(),
            "type": "direct_answer",
            "answer": fallback_text,
            "text": fallback_text,
            "dataset_id": ds_id
        }
    )
