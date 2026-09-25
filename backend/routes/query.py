"""
API Route for Natural Language Query Processing, Analytics Execution, and Context Resolution.
"""

import logging
import re
from typing import Any, Dict, List, Optional
from pydantic import BaseModel
from fastapi import APIRouter, status, HTTPException
from fastapi.responses import JSONResponse

from analyst import process_query_with_llm, execute_query, execute_queries, LLMResponse, QueryResult, ResponseType
from analyst.models import QuerySpec
from storage.dataset_manager import get_or_load_dataset
from visualization.selector import select_visualizations
from chat import get_chat_service
from decision_engine import detect_decision, run_decision_analysis
from geo import run_geo_analysis

logger = logging.getLogger(__name__)

router = APIRouter(tags=["query"])


class QueryRequest(BaseModel):
    question: Optional[str] = None
    message: Optional[str] = None
    dataset_id: Optional[str] = None
    conversation_id: Optional[str] = None


@router.post("/chats/{chat_id}/messages")
@router.post("/api/chats/{chat_id}/messages")
@router.post("/api/conversations/{chat_id}/messages")
async def execute_chat_message(chat_id: str, payload: QueryRequest):
    """
    POST /chats/{chat_id}/messages
    Executes query in a chat, resolving context from conversation.json.
    """
    payload.conversation_id = chat_id
    return await execute_user_query(payload)


@router.post("/api/query")
@router.post("/api/chat")
async def execute_user_query(payload: QueryRequest):
    """
    Main endpoint for Qwen3 / Context Resolver routing, DuckDB/Pandas analytics execution,
    and conversation history persistence in conversation.json.
    """
    raw_query = (payload.question or payload.message or "").strip()
    if not raw_query:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"type": "error", "error": "Question or message cannot be empty."}
        )

    # 1. Initialize Chat Service & Conversation Session
    chat_service = get_chat_service()
    requested_chat = chat_service.get_conversation(payload.conversation_id) if payload.conversation_id else None
    if payload.conversation_id and not requested_chat:
        raise HTTPException(status_code=404, detail="Chat not found for this session.")
    allowed_datasets = set()
    for owned_conversation in chat_service.list_conversations(limit=500):
        if owned_conversation.dataset_id:
            allowed_datasets.add(owned_conversation.dataset_id)
        allowed_datasets.update(file.get("file_id") for file in chat_service.get_files(owned_conversation.id))
    if payload.dataset_id and payload.dataset_id not in allowed_datasets:
        raise HTTPException(status_code=403, detail="The selected dataset is not available in this session.")
    conversation = chat_service.handle_query_session(
        conversation_id=payload.conversation_id,
        user_message_text=raw_query,
        dataset_id=payload.dataset_id
    )
    cid = conversation.id

    # Dataset IDs are accepted only when they are attached to one of this
    # account's chats. This keeps the process-wide analysis cache from becoming
    # a cross-account file browser.
    if payload.conversation_id and payload.dataset_id:
        current_files = {file.get("file_id") for file in chat_service.get_files(cid)}
        if payload.dataset_id != conversation.dataset_id and payload.dataset_id not in current_files:
            raise HTTPException(status_code=403, detail="The selected dataset is not attached to this chat.")

    # 2. Context Resolver Step (Requirement 5 & 6)
    resolved_spec, compact_context, selected_file_id = chat_service.resolve_query_context(
        conversation_id=cid,
        user_query=raw_query
    )

    # 3. Resolve Target Dataset for this Chat
    target_dataset_id = payload.dataset_id or selected_file_id or conversation.dataset_id

    # Search chat-scoped files if dataset_id not explicitly set
    if not target_dataset_id:
        chat_files = chat_service.get_files(cid)
        if chat_files:
            target_dataset_id = chat_files[-1].get("file_id")

    dataset_info = None
    if target_dataset_id:
        dataset_info = get_or_load_dataset(target_dataset_id, chat_id=cid)

    # 4. Persist User Message to conversation.json
    user_msg = chat_service.add_user_message(
        conversation_id=cid,
        content=raw_query,
        file_id=target_dataset_id
    )

    if not dataset_info:
        no_ds_text = "Please upload a CSV or Excel dataset first before asking data-analysis questions. Click the **+** button below to attach a file."
        assistant_msg = chat_service.add_assistant_message(
            conversation_id=cid,
            content=no_ds_text,
            file_id=None
        )
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "conversation_id": cid,
                "chat_id": cid,
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

    # Decision intent is an additional route layered before the existing analyst flow.
    history = chat_service.get_messages(cid)
    previous_trace = next((m.result_json.get("decision_analysis") for m in reversed(history)
                           if m.role == "assistant" and m.file_id == ds_id and m.result_json
                           and m.result_json.get("decision_analysis")), None)
    decision_intent = detect_decision(raw_query, list(df.columns) if df is not None else [], previous_trace)
    if decision_intent.get("is_decision"):
        if previous_trace:
            prior_intent = previous_trace.get("intent", {})
            decision_intent["target_metric"] = decision_intent.get("target_metric") or prior_intent.get("target_metric")
            decision_intent["target_value"] = decision_intent.get("target_value") or prior_intent.get("target_value")
            decision_intent["objective"] = prior_intent.get("objective", decision_intent.get("objective"))
            decision_intent["decision_variable"] = prior_intent.get("decision_variable") or decision_intent.get("decision_variable")
            decision_intent["parent_decision_question"] = prior_intent.get("parent_decision_question") or prior_intent.get("decision_question")
            decision_intent["decision_question"] = raw_query
            if re.search(r"\bwhat if\b", raw_query, re.I):
                pct = re.search(r"(\d+(?:\.\d+)?)\s*%", raw_query)
                if pct:
                    decision_intent["requested_percent"] = float(pct.group(1))
        decision_intent["decision_question"] = decision_intent.get("decision_question") or raw_query
        outcome = run_decision_analysis(df, decision_intent, ds_id, previous_trace)
        answer = outcome.get("answer")
        analysis = outcome.get("decision_analysis")
        if analysis:
            boundary = analysis["boundary"]
            if boundary.get("boundary_value") is not None:
                answer = (f"Based on the observed data and proportional scenario model, the first evaluated level "
                          f"to reach the target is {boundary['boundary_value']:g}%. This is an estimate, not a causal guarantee.")
            else:
                answer = "I evaluated the available scenarios, but the data does not support a clear decision boundary. See the scenario and evidence details below."
        assistant_msg = chat_service.add_assistant_message(
            conversation_id=cid, content=answer,
            result_json={"decision_analysis": analysis} if analysis else None,
            visualization_json=analysis.get("visualization") if analysis else None,
            intent={"type": "decision", **decision_intent}, file_id=ds_id)
        return JSONResponse(status_code=status.HTTP_200_OK, content={
            "conversation_id": cid, "chat_id": cid,
            "user_message": user_msg.to_dict(), "assistant_message": assistant_msg.to_dict(),
            "type": "decision_analysis", "status": "clarification" if not analysis else "success",
            "text": answer, "answer": answer, "dataset_id": ds_id,
            "decision_analysis": analysis,
            "visualization": analysis.get("visualization") if analysis else None
        })

    if ds_id and conversation.dataset_id != ds_id:
        chat_service.associate_dataset(conversation_id=cid, dataset_id=ds_id)

    # 5. Execute Query using Resolved Spec or LLM Processor
    queries: List[QuerySpec] = []
    llm_resp: Optional[LLMResponse] = None

    # Let the LLM interpret geographic follow-ups with the prior geo spec in context.
    prior_geo = next((m for m in reversed(chat_service.get_messages(cid))
                      if m.role == "assistant" and m.file_id == ds_id and m.query_spec
                      and m.query_spec.get("analysis_type") == "geographic_analysis"), None)
    if prior_geo:
        resolved_spec = None

    if resolved_spec:
        # Context Resolver successfully inherited previous query state (Requirement 5 & 15)
        queries = [resolved_spec]
        llm_resp = LLMResponse(type="data_query", query=resolved_spec, queries=queries)
    else:
        # Call Query Processor with LLM
        try:
            llm_resp = process_query_with_llm(
                question=raw_query,
                schema=schema,
                profile=profile,
                df=df,
                dataset_id=ds_id,
                conversation_context=compact_context if prior_geo else None
            )
        except ConnectionError:
            err_text = "The local query model is currently unavailable. Please make sure Ollama is running."
            assistant_msg = chat_service.add_assistant_message(
                conversation_id=cid,
                content=err_text,
                file_id=ds_id
            )
            return JSONResponse(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                content={
                    "conversation_id": cid,
                    "chat_id": cid,
                    "user_message": user_msg.to_dict(),
                    "assistant_message": assistant_msg.to_dict(),
                    "type": "error",
                    "status": "error",
                    "error": err_text,
                    "text": err_text
                }
            )
        except Exception as e:
            logger.error(f"Error processing query: {e}")
            err_text = f"An error occurred while processing your query: {str(e)}"
            assistant_msg = chat_service.add_assistant_message(
                conversation_id=cid,
                content=err_text,
                file_id=ds_id
            )
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content={
                    "conversation_id": cid,
                    "chat_id": cid,
                    "user_message": user_msg.to_dict(),
                    "assistant_message": assistant_msg.to_dict(),
                    "type": "error",
                    "status": "error",
                    "error": err_text,
                    "text": err_text
                }
            )

    # 6. Handle Direct Answer / Conversational
    if llm_resp and (llm_resp.type == ResponseType.DIRECT_ANSWER.value or llm_resp.type == "direct_answer"):
        answer_text = llm_resp.answer or "I processed your request."
        assistant_msg = chat_service.add_assistant_message(
            conversation_id=cid,
            content=answer_text,
            file_id=ds_id
        )
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "conversation_id": cid,
                "chat_id": cid,
                "user_message": user_msg.to_dict(),
                "assistant_message": assistant_msg.to_dict(),
                "type": "direct_answer",
                "status": "conversational",
                "answer": answer_text,
                "text": answer_text,
                "dataset_id": ds_id
            }
        )

    # 7. Handle Clarification
    if llm_resp and (llm_resp.type == ResponseType.CLARIFICATION.value or llm_resp.type == "clarification"):
        answer_text = llm_resp.answer or "Could you please clarify your question?"
        assistant_msg = chat_service.add_assistant_message(
            conversation_id=cid,
            content=answer_text,
            file_id=ds_id
        )

    # LLM-authored geographic intent is validated and calculated deterministically.
    geo_spec = llm_resp.geo_query if llm_resp else None
    if geo_spec:
        geo_spec = {**geo_spec, "question": raw_query}
        geo_outcome = run_geo_analysis(df, geo_spec)
        if not geo_outcome.get("success"):
            answer_text = geo_outcome.get("error", "Geographic analysis could not be completed.")
            assistant_msg = chat_service.add_assistant_message(conversation_id=cid, content=answer_text, result_json={"analysis_type": "geographic_analysis", "error": answer_text}, intent={"type": "geographic_analysis"}, file_id=ds_id)
            return JSONResponse(status_code=200, content={"conversation_id":cid,"chat_id":cid,"user_message":user_msg.to_dict(),"assistant_message":assistant_msg.to_dict(),"type":"error","status":"error","error":answer_text,"text":answer_text,"dataset_id":ds_id,"analysis_type":"geographic_analysis"})
        answer_text = geo_outcome["answer"]
        stored = {k:v for k,v in geo_outcome.items() if k != "answer"}
        assistant_msg = chat_service.add_assistant_message(conversation_id=cid, content=answer_text, result_json=stored, visualization_json=geo_outcome["visualization"], intent={"type":"geographic_analysis","intent":geo_spec.get("intent")}, query_spec=geo_spec, file_id=ds_id)
        return JSONResponse(status_code=200, content={"conversation_id":cid,"chat_id":cid,"user_message":user_msg.to_dict(),"assistant_message":assistant_msg.to_dict(),"type":"geographic_analysis","status":"success","analysis_type":"geographic_analysis","answer":answer_text,"text":answer_text,"dataset_id":ds_id,**stored})
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "conversation_id": cid,
                "chat_id": cid,
                "user_message": user_msg.to_dict(),
                "assistant_message": assistant_msg.to_dict(),
                "type": "clarification",
                "status": "clarification",
                "answer": answer_text,
                "text": answer_text,
                "dataset_id": ds_id
            }
        )

    # 8. Handle Analytical Query Execution (DuckDB / Pandas)
    exec_queries = queries or (llm_resp.all_queries if llm_resp else [])
    if not exec_queries:
        clarify_text = "Could you please specify which metric or column you would like to analyze?"
        assistant_msg = chat_service.add_assistant_message(
            conversation_id=cid,
            content=clarify_text,
            file_id=ds_id
        )
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "conversation_id": cid,
                "chat_id": cid,
                "user_message": user_msg.to_dict(),
                "assistant_message": assistant_msg.to_dict(),
                "type": "clarification",
                "status": "clarification",
                "answer": clarify_text,
                "text": clarify_text,
                "dataset_id": ds_id
            }
        )

    exec_res: QueryResult = execute_queries(exec_queries, df)

    if not exec_res.success:
        err_text = f"Error executing query: {exec_res.error}"
        assistant_msg = chat_service.add_assistant_message(
            conversation_id=cid,
            content=err_text,
            file_id=ds_id
        )
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "conversation_id": cid,
                "chat_id": cid,
                "user_message": user_msg.to_dict(),
                "assistant_message": assistant_msg.to_dict(),
                "type": "error",
                "status": "error",
                "error": exec_res.error,
                "text": err_text,
                "dataset_id": ds_id
            }
        )

    # 9. Select Visualizations
    primary_spec = exec_queries[0] if exec_queries else None
    visualizations = select_visualizations(
        spec=primary_spec,
        query_result=exec_res,
        schema=schema,
        df=df,
        raw_question=raw_query
    )
    primary_vis = visualizations[0] if visualizations else None

    # 10. Construct Intent & Query Spec to persist in conversation.json (Requirements 13 & 14)
    intent_payload = {
        "operation": primary_spec.operation if primary_spec else "analytics",
        "condition": primary_spec.condition.to_dict() if primary_spec and primary_spec.condition else None,
        "scope": "all_subject_columns" if primary_spec and primary_spec.columns else (primary_spec.column if primary_spec else None)
    }

    query_spec_payload = primary_spec.to_dict() if primary_spec else None
    if query_spec_payload:
        query_spec_payload["file_id"] = ds_id

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

    # Persist Assistant Message in conversation.json
    assistant_msg = chat_service.add_assistant_message(
        conversation_id=cid,
        content=exec_res.text or "Here are your analytical results.",
        result_json=structured_result,
        visualization_json=primary_vis or visualizations,
        intent=intent_payload,
        query_spec=query_spec_payload,
        file_id=ds_id
    )

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "conversation_id": cid,
            "chat_id": cid,
            "user_message": user_msg.to_dict(),
            "assistant_message": assistant_msg.to_dict(),
            "type": "data_result",
            "status": "success",
            "query": exec_res.query,
            "queries": exec_res.queries,
            "query_spec": query_spec_payload,
            "intent": intent_payload,
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
