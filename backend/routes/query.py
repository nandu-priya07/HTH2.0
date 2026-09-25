"""
API Route for Natural Language Query Processing, Analytics Execution, and Context Resolution.
"""

import logging
import re
import time
from typing import Any, Dict, List, Optional
from pydantic import BaseModel
from fastapi import APIRouter, status, HTTPException
from fastapi.responses import JSONResponse

from analyst import process_query_with_llm, execute_query, execute_queries, LLMResponse, QueryResult, ResponseType
from analyst.response_generator import ResponseGenerator
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
    Executes query in a chat, resolving context from conversation session.
    """
    payload.conversation_id = chat_id
    return await execute_user_query(payload)


def _build_timing(
    t_req_start: float,
    t_chat_ms: float = 0.0,
    t_context_ms: float = 0.0,
    t_runtime_ms: float = 0.0,
    t_llm_ms: float = 0.0,
    t_exec_ms: float = 0.0,
    t_format_ms: float = 0.0,
    llm_timing: Optional[Dict[str, Any]] = None,
    cache_hit: bool = True
) -> Dict[str, Any]:
    t_total_ms = (time.perf_counter() - t_req_start) * 1000
    pre_ms = (llm_timing or {}).get("preprocess_ms", 0.0)
    cand_ms = (llm_timing or {}).get("candidate_resolution_ms", 0.0)
    prompt_ms = (llm_timing or {}).get("prompt_build_ms", 0.0)
    prompt_chars = (llm_timing or {}).get("prompt_chars", 0)
    est_tokens = (llm_timing or {}).get("estimated_tokens", 0)
    rows = (llm_timing or {}).get("row_count", 0)
    cols = (llm_timing or {}).get("col_count", 0)
    llm_calls = (llm_timing or {}).get("llm_calls", 1 if t_llm_ms > 0 else 0)

    timing_dict = {
        "total_ms": round(t_total_ms, 2),
        "chat_ms": round(t_chat_ms, 2),
        "context_ms": round(t_context_ms, 2),
        "runtime_ms": round(t_runtime_ms, 2),
        "preprocess_ms": round(pre_ms, 2),
        "candidate_resolution_ms": round(cand_ms, 2),
        "prompt_build_ms": round(prompt_ms, 2),
        "llm_ms": round(t_llm_ms, 2),
        "duckdb_ms": round(t_exec_ms, 2),
        "exec_ms": round(t_exec_ms, 2),
        "format_ms": round(t_format_ms, 2),
        "cache_status": "HIT" if cache_hit else "MISS",
        "prompt_metrics": {
            "char_count": prompt_chars,
            "estimated_token_count": est_tokens,
            "dataset_rows": rows,
            "dataset_columns": cols,
            "llm_calls": llm_calls
        },
        "steps": {
            "request_received": "0.00ms",
            "chat_context": f"{t_chat_ms:.2f}ms",
            "context_resolution": f"{t_context_ms:.2f}ms",
            "runtime_cache_lookup": f"{t_runtime_ms:.2f}ms ({'HIT' if cache_hit else 'MISS'})",
            "preprocess": f"{pre_ms:.2f}ms",
            "value_resolution": f"{cand_ms:.2f}ms",
            "prompt_build": f"{prompt_ms:.2f}ms ({prompt_chars} chars, ~{est_tokens} tokens)",
            "llm_query_understanding": f"{t_llm_ms:.2f}ms ({llm_calls} call)",
            "analytical_execution": f"{t_exec_ms:.2f}ms",
            "response_formatting": f"{t_format_ms:.2f}ms",
            "total_request_time": f"{t_total_ms:.2f}ms"
        }
    }
    if llm_timing:
        timing_dict["llm_breakdown"] = llm_timing
    return timing_dict


@router.post("/api/query")
@router.post("/api/chat")
async def execute_user_query(payload: QueryRequest):
    """
    Main endpoint for Qwen3 / Context Resolver routing, DuckDB/Pandas analytics execution,
    and conversation history persistence in Supabase PostgreSQL / conversation session.
    """
    t_req_start = time.perf_counter()

    raw_query = (payload.question or payload.message or "").strip()
    if not raw_query:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"type": "error", "error": "Question or message cannot be empty."}
        )

    # 1. Initialize Chat Service & Conversation Session
    t0 = time.perf_counter()
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
        if get_or_load_dataset(payload.dataset_id) is not None and len(allowed_datasets) > 0:
            raise HTTPException(status_code=403, detail="The selected dataset is not available in this session.")
    conversation = chat_service.handle_query_session(
        conversation_id=payload.conversation_id,
        user_message_text=raw_query,
        dataset_id=payload.dataset_id
    )
    cid = conversation.id
    t_chat_ms = (time.perf_counter() - t0) * 1000

    if payload.conversation_id and payload.dataset_id:
        current_files = {file.get("file_id") for file in chat_service.get_files(cid)}
        if payload.dataset_id != conversation.dataset_id and payload.dataset_id not in current_files:
            raise HTTPException(status_code=403, detail="The selected dataset is not attached to this chat.")

    # 2. Context Resolver Step
    t0 = time.perf_counter()
    resolved_spec, compact_context, selected_file_id = chat_service.resolve_query_context(
        conversation_id=cid,
        user_query=raw_query
    )
    t_context_ms = (time.perf_counter() - t0) * 1000

    # 3. Resolve Target Dataset & Lookup Dataset Runtime Cache
    t0 = time.perf_counter()
    target_dataset_id = payload.dataset_id or selected_file_id or conversation.dataset_id
    if not target_dataset_id:
        chat_files = chat_service.get_files(cid)
        if chat_files:
            target_dataset_id = chat_files[-1].get("file_id")

    dataset_info = None
    if target_dataset_id:
        dataset_info = get_or_load_dataset(target_dataset_id, chat_id=cid)
    t_runtime_ms = (time.perf_counter() - t0) * 1000

    user_msg = chat_service.add_user_message(
        conversation_id=cid,
        content=raw_query,
        file_id=target_dataset_id
    )

    if not dataset_info:
        no_ds_text = "Please upload a CSV or Excel dataset first before asking data-analysis questions. Click the **+** button below to attach a file."
        timing = _build_timing(t_req_start, t_chat_ms, t_context_ms, t_runtime_ms)
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
                "dataset_id": None,
                "timing": timing
            }
        )

    schema = dataset_info.get("schema") or dataset_info.get("result", {}).get("schema")
    profile = dataset_info.get("profile") or dataset_info.get("result", {}).get("profile")
    df = dataset_info.get("data")
    ds_id = dataset_info.get("dataset_id")

    # Decision intent path
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

    # 4. LLM Query Processing / Candidate Resolution Stage
    t0 = time.perf_counter()
    queries: List[QuerySpec] = []
    llm_resp: Optional[LLMResponse] = None

    prior_geo = next((m for m in reversed(chat_service.get_messages(cid))
                      if m.role == "assistant" and m.file_id == ds_id and m.query_spec
                      and m.query_spec.get("analysis_type") == "geographic_analysis"), None)
    if prior_geo:
        resolved_spec = None

    if resolved_spec:
        queries = [resolved_spec]
        llm_resp = LLMResponse(type="data_query", query=resolved_spec, queries=queries)
    else:
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
            err_text = "I couldn't interpret your query against the current dataset. Please rephrase or specify a metric."
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
    t_llm_ms = (time.perf_counter() - t0) * 1000

    # Direct answer / Conversational
    if llm_resp and (llm_resp.type == ResponseType.DIRECT_ANSWER.value or llm_resp.type == "direct_answer"):
        answer_text = llm_resp.answer or "I processed your request."
        llm_t = getattr(llm_resp, "timing", None)
        timing = _build_timing(t_req_start, t_chat_ms, t_context_ms, t_runtime_ms, t_llm_ms=t_llm_ms, llm_timing=llm_t)
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
                "dataset_id": ds_id,
                "timing": timing
            }
        )

    # Clarification
    if llm_resp and (llm_resp.type == ResponseType.CLARIFICATION.value or llm_resp.type == "clarification"):
        answer_text = llm_resp.answer or "Could you please clarify your question?"
        assistant_msg = chat_service.add_assistant_message(
            conversation_id=cid,
            content=answer_text,
            file_id=ds_id
        )

    # Geographic intent path
    geo_spec = llm_resp.geo_query if llm_resp else None
    if geo_spec:
        t0 = time.perf_counter()
        geo_spec = {**geo_spec, "question": raw_query}
        geo_outcome = run_geo_analysis(df, geo_spec)
        t_exec_ms = (time.perf_counter() - t0) * 1000
        llm_t = getattr(llm_resp, "timing", None)
        timing = _build_timing(t_req_start, t_chat_ms, t_context_ms, t_runtime_ms, t_llm_ms=t_llm_ms, t_exec_ms=t_exec_ms, llm_timing=llm_t)
        if not geo_outcome.get("success"):
            answer_text = geo_outcome.get("error", "Geographic analysis could not be completed.")
            assistant_msg = chat_service.add_assistant_message(conversation_id=cid, content=answer_text, result_json={"analysis_type": "geographic_analysis", "error": answer_text, "timing": timing}, intent={"type": "geographic_analysis"}, file_id=ds_id)
            return JSONResponse(status_code=200, content={"conversation_id":cid,"chat_id":cid,"user_message":user_msg.to_dict(),"assistant_message":assistant_msg.to_dict(),"type":"error","status":"error","error":answer_text,"text":answer_text,"dataset_id":ds_id,"analysis_type":"geographic_analysis","timing":timing})
        answer_text = geo_outcome["answer"]
        stored = {k:v for k,v in geo_outcome.items() if k != "answer"}
        stored["timing"] = timing
        assistant_msg = chat_service.add_assistant_message(conversation_id=cid, content=answer_text, result_json=stored, visualization_json=geo_outcome["visualization"], intent={"type":"geographic_analysis","intent":geo_spec.get("intent")}, query_spec=geo_spec, file_id=ds_id)

        t_total_ms = timing["total_ms"]
        logger.info(
            f"[QUERY] total: {t_total_ms:.1f}ms | [CHAT] {t_chat_ms:.1f}ms | [RUNTIME] {t_runtime_ms:.1f}ms | "
            f"[CONTEXT] {t_context_ms:.1f}ms | [LLM] {t_llm_ms:.1f}ms | [GEO/EXEC] {t_exec_ms:.1f}ms"
        )
        return JSONResponse(status_code=200, content={"conversation_id":cid,"chat_id":cid,"user_message":user_msg.to_dict(),"assistant_message":assistant_msg.to_dict(),"type":"geographic_analysis","status":"success","analysis_type":"geographic_analysis","answer":answer_text,"text":answer_text,"dataset_id":ds_id,"timing":timing,**stored})

    # 5. Analytical Execution Stage (DuckDB / Pandas)
    t0 = time.perf_counter()
    exec_queries = queries or (llm_resp.all_queries if llm_resp else [])
    if not exec_queries:
        clarify_text = "Could you please specify which metric or column you would like to analyze?"
        llm_t = getattr(llm_resp, "timing", None)
        timing = _build_timing(t_req_start, t_chat_ms, t_context_ms, t_runtime_ms, t_llm_ms=t_llm_ms, llm_timing=llm_t)
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
                "dataset_id": ds_id,
                "timing": timing
            }
        )

    exec_res: QueryResult = execute_queries(exec_queries, df)
    t_exec_ms = (time.perf_counter() - t0) * 1000

    if not exec_res.success:
        err_text = "I couldn't apply the specified filter or query criteria to the dataset. Please try again."
        logger.warning(f"Query execution failed: {exec_res.error}")
        llm_t = getattr(llm_resp, "timing", None)
        timing = _build_timing(t_req_start, t_chat_ms, t_context_ms, t_runtime_ms, t_llm_ms=t_llm_ms, t_exec_ms=t_exec_ms, llm_timing=llm_t)
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
                "dataset_id": ds_id,
                "timing": timing
            }
        )

    # 6. Response Formatting & Visualization Selection Stage
    t0 = time.perf_counter()
    primary_spec = exec_queries[0] if exec_queries else None
    visualizations = select_visualizations(
        spec=primary_spec,
        query_result=exec_res,
        schema=schema,
        df=df,
        raw_question=raw_query
    )
    primary_vis = visualizations[0] if visualizations else None

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

    formatted_text = ResponseGenerator.generate_response(exec_res, raw_query, spec=primary_spec)
    exec_res.text = formatted_text
    t_format_ms = (time.perf_counter() - t0) * 1000

    llm_t = getattr(llm_resp, "timing", None)
    timing = _build_timing(
        t_req_start, t_chat_ms, t_context_ms, t_runtime_ms,
        t_llm_ms=t_llm_ms, t_exec_ms=t_exec_ms, t_format_ms=t_format_ms,
        llm_timing=llm_t
    )

    if exec_res.metadata is None:
        exec_res.metadata = {}
    exec_res.metadata["timing"] = timing
    structured_result["metadata"] = exec_res.metadata
    structured_result["timing"] = timing

    assistant_msg = chat_service.add_assistant_message(
        conversation_id=cid,
        content=formatted_text,
        result_json=structured_result,
        visualization_json=primary_vis or visualizations,
        intent=intent_payload,
        query_spec=query_spec_payload,
        file_id=ds_id
    )

    t_total_ms = timing["total_ms"]
    logger.info(
        f"[QUERY] total: {t_total_ms:.1f}ms | [CHAT] {t_chat_ms:.1f}ms | [RUNTIME] {t_runtime_ms:.1f}ms | "
        f"[CONTEXT] {t_context_ms:.1f}ms | [LLM] {t_llm_ms:.1f}ms | [DUCKDB] {t_exec_ms:.1f}ms | [FORMAT] {t_format_ms:.1f}ms"
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
            "text": formatted_text,
            "answer": formatted_text,
            "metadata": exec_res.metadata,
            "timing": timing,
            "dataset_id": ds_id,
            "visualization": primary_vis,
            "visualizations": visualizations
        }
    )
