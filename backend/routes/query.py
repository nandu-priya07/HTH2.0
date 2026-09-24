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
from analyst.follow_up import resolve_analytical_follow_up, AGGREGATE_OPS
from analyst.semantics import apply_semantic_layer
from analyst.summarizer import generate_answer, describe_no_data
from storage.dataset_manager import get_or_load_dataset
from visualization.selector import select_visualizations
from chat import get_chat_service
from decision_engine import detect_decision, run_decision_analysis

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
    conversation = chat_service.handle_query_session(
        conversation_id=payload.conversation_id,
        user_message_text=raw_query,
        dataset_id=payload.dataset_id
    )
    cid = conversation.id

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

    # 5a. Aggregate follow-ups ("what about Germany?", "break that down by region", "average instead")
    #     are resolved deterministically against the previous plan. The grade-oriented context
    #     resolver must not reinterpret them as conditional counts.
    prev_spec_dict = next((m.query_spec for m in reversed(history)
                           if m.role == "assistant" and m.query_spec and m.file_id in (None, ds_id)), None)
    aggregate_follow_up = resolve_analytical_follow_up(raw_query, prev_spec_dict, df)
    if aggregate_follow_up is not None:
        follow_resp = apply_semantic_layer(
            LLMResponse(type="data_query", query=aggregate_follow_up, queries=[aggregate_follow_up]),
            raw_query, df)
        if follow_resp.type == "data_query":
            resolved_spec = follow_resp.all_queries[0]
        else:
            resolved_spec = None
            llm_resp = follow_resp
    elif resolved_spec is not None and prev_spec_dict and \
            str(prev_spec_dict.get("operation") or "").lower() in AGGREGATE_OPS:
        resolved_spec = None

    if llm_resp is None and resolved_spec:
        # Context Resolver successfully inherited previous query state (Requirement 5 & 15)
        queries = [resolved_spec]
        llm_resp = LLMResponse(type="data_query", query=resolved_spec, queries=queries)
    elif llm_resp is None:
        # Call Query Processor with LLM
        try:
            call_kwargs = {
                "question": raw_query,
                "schema": schema,
                "profile": profile,
                "df": df,
                "dataset_id": ds_id
            }
            prev_q = compact_context.get("previous_query")
            if prev_q:
                import inspect
                sig = inspect.signature(process_query_with_llm)
                if "previous_query" in sig.parameters or any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()):
                    call_kwargs["previous_query"] = prev_q

            llm_resp = process_query_with_llm(**call_kwargs)
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
        options = (llm_resp.details or {}).get("options")
        assistant_msg = chat_service.add_assistant_message(
            conversation_id=cid,
            content=answer_text,
            result_json={"status": "clarification", "options": options} if options else None,
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
                "answer": answer_text,
                "text": answer_text,
                "options": options,
                "dataset_id": ds_id
            }
        )

    # 7b. Requested metric / period isn't in the dataset and can't be derived: say so, never estimate.
    if llm_resp and llm_resp.type == ResponseType.NOT_AVAILABLE.value:
        answer_text = llm_resp.answer or "That information isn't available in this dataset."
        details = llm_resp.details or {}
        assistant_msg = chat_service.add_assistant_message(
            conversation_id=cid,
            content=answer_text,
            result_json={"status": "not_available", **details},
            file_id=ds_id
        )
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "conversation_id": cid,
                "chat_id": cid,
                "user_message": user_msg.to_dict(),
                "assistant_message": assistant_msg.to_dict(),
                "type": "not_available",
                "status": "not_available",
                "answer": answer_text,
                "text": answer_text,
                "summary": answer_text,
                "requested_metric": details.get("requested_metric"),
                "reason": details.get("reason"),
                "available_fields": details.get("available_fields"),
                "suggestion": details.get("suggestion"),
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

    # 8b. Valid query, zero matching rows: report it instead of falling back to the whole dataset.
    if not exec_res.success and exec_res.status == "no_data":
        failed_spec = next((q for q in exec_queries
                            if exec_res.filters_applied == [f.to_dict() for f in q.filters]), exec_queries[0])
        no_data_text = describe_no_data(failed_spec, exec_res, df)
        assistant_msg = chat_service.add_assistant_message(
            conversation_id=cid,
            content=no_data_text,
            result_json={"status": "no_data", "metadata": exec_res.metadata,
                         "filters_applied": exec_res.filters_applied},
            query_spec={**failed_spec.to_dict(), "file_id": ds_id},
            file_id=ds_id
        )
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "conversation_id": cid,
                "chat_id": cid,
                "user_message": user_msg.to_dict(),
                "assistant_message": assistant_msg.to_dict(),
                "type": "no_data",
                "status": "no_data",
                "answer": no_data_text,
                "text": no_data_text,
                "summary": no_data_text,
                "query_spec": {**failed_spec.to_dict(), "file_id": ds_id},
                "filters_applied": exec_res.filters_applied,
                "rows_before_filter": exec_res.rows_before_filter,
                "rows_after_filter": 0,
                "metadata": exec_res.metadata,
                "dataset_id": ds_id
            }
        )

    if not exec_res.success:
        err_text = exec_res.error or "Error executing query."
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

    # 9. Natural-language answer from the deterministic result (LLM may only rephrase verified facts)
    answer_text, answer_source = generate_answer(raw_query, exec_queries, exec_res)
    if answer_text:
        exec_res.text = answer_text
        exec_res.summary = answer_text

    # 9b. Select Visualizations
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

    canonical = {
        "status": "success",
        "summary": exec_res.summary,
        "answer_source": answer_source,
        "fields_used": exec_res.fields_used,
        "filters_applied": exec_res.filters_applied,
        "rows_before_filter": exec_res.rows_before_filter,
        "rows_after_filter": exec_res.rows_after_filter,
        "aggregation": exec_res.aggregation,
        "group_by": exec_res.group_by,
        "calculation_steps": exec_res.calculation_steps,
        "derived_metric": exec_res.derived_metric,
    }

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
        "metadata": exec_res.metadata,
        **canonical
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
            **canonical,
            "query_plan": query_spec_payload,
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
