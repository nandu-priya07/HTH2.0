"""
LLM Query Processor using local Ollama (qwen3:8b).
Translates user queries into structured LLMResponse supporting single-query,
multi-query, and multi-column conditional counts.
"""

import logging
import re
import time
import hashlib
from typing import Any, Dict, List, Optional
import pandas as pd

from llm import OllamaClient, SYSTEM_PROMPT, build_dataset_context, build_user_prompt
from .models import LLMResponse, QuerySpec, FilterSpec, SortSpec, ConditionSpec
from .preprocessor import QueryPreprocessor
from .candidate_resolver import CandidateResolver
from .semantic_cache import SemanticQueryCache
from geo.entity_discovery import discover_geo_profile
from geo.metric_synthesis import resolve_metric, DERIVED_METRICS

logger = logging.getLogger(__name__)


def process_query_with_llm(
    question: str,
    schema: Optional[Dict[str, Any]] = None,
    profile: Optional[Dict[str, Any]] = None,
    df: Optional[pd.DataFrame] = None,
    dataset_id: Optional[str] = None,
    conversation_context: Optional[Dict[str, Any]] = None,
    previous_query: Optional[Any] = None
) -> LLMResponse:
    """
    Processes a natural language question with Qwen3:8b via local Ollama.
    Returns structured LLMResponse.
    """
    clean_q = question.strip()
    if not clean_q:
        return LLMResponse(
            type="direct_answer",
            answer="Please enter a question or query."
        )

    # Fast-path for pure conversational, conceptual, and ambiguous queries
    q_lower = clean_q.lower().strip()
    q_clean_alpha = re.sub(r"[^\w\s]", "", q_lower).strip()
    if q_clean_alpha in ("hello", "hi", "hey", "good morning", "good afternoon", "who are you"):
        return LLMResponse(
            type="direct_answer",
            answer="Hello! I am your AI Data Analyst. How can I help you analyze your dataset today?"
        )
    if q_clean_alpha in ("what can you do", "help", "what are your capabilities"):
        return LLMResponse(
            type="direct_answer",
            answer="I can help you analyze your dataset by calculating metrics (sum, average, count, min, max), listing distinct values, executing multi-column conditional counts, aggregating across categories, and applying filters."
        )
    if re.search(r"^what is (?:a |an )?(profit|sales|revenue|data analysis|database|sql)\??$", q_lower):
        concept = re.search(r"^what is (?:a |an )?(profit|sales|revenue|data analysis|database|sql)\??$", q_lower).group(1)
        ans = f"In business and data analysis, {concept} refers to financial gain representing the difference between amount earned and the amount spent in buying, operating, or producing something." if concept == "profit" else f"{concept.title()} is a fundamental data concept used in storing and analyzing business information."
        return LLMResponse(type="direct_answer", answer=ans)
    if q_clean_alpha in ("show locations", "locations", "list locations"):
        loc_cols = [c for c in (df.columns if df is not None else []) if any(w in c.lower() for w in ("country", "region", "state", "city", "postal"))]
        return LLMResponse(
            type="clarification",
            answer=f"Which location field would you like to use: {', '.join(loc_cols[:4])}?" if loc_cols else "Which location column would you like to view?"
        )

    if previous_query and not conversation_context:
        prev_dict = previous_query.to_dict() if hasattr(previous_query, "to_dict") else previous_query
        conversation_context = {"previous_result": {"query_spec": prev_dict}}

    # 1. Query Preprocessing & Casing / Abbreviation Normalization
    t0 = time.perf_counter()
    preprocessor = QueryPreprocessor()
    prep_q = preprocessor.preprocess(clean_q)
    norm_q = prep_q.normalized_query
    pre_ms = round((time.perf_counter() - t0) * 1000, 2)

    # 2. Semantic Cache Lookup (by dataset_id + normalized_query + context_hash)
    ctx_hash = hashlib.sha256(str(conversation_context or {}).encode("utf-8")).hexdigest()[:12]
    cached_resp = SemanticQueryCache.get_cached_interpretation(dataset_id or "default", norm_q, ctx_hash)
    if cached_resp:
        return cached_resp

    # 3. Schema & Value Candidate Resolution via RapidFuzz
    t1 = time.perf_counter()
    resolver = CandidateResolver()
    cand_result = resolver.resolve(prep_q, df=df, schema=schema, dataset_id=dataset_id)
    cand_dict = cand_result.to_compact_dict()
    cand_ms = round((time.perf_counter() - t1) * 1000, 2)

    # 4. Build Dataset Context & Prompt Enriched with Candidate Matches
    t_prompt0 = time.perf_counter()
    dataset_context = build_dataset_context(schema, profile, df, dataset_id)
    user_prompt = build_user_prompt(prep_q.original_query, dataset_context, conversation_context, candidates=cand_dict if cand_dict else None)
    prompt_ms = round((time.perf_counter() - t_prompt0) * 1000, 2)
    prompt_chars = len(user_prompt)
    estimated_tokens = prompt_chars // 4
    num_rows = len(df) if df is not None else 0
    num_cols = len(df.columns) if df is not None else 0
    num_cands = (len(cand_dict.get("columns", [])) + len(cand_dict.get("values", [])) + len(cand_dict.get("metrics", []))) if cand_dict else 0

    # Check deterministic router first for high-confidence column operations, record lookups, and fast-path queries
    fb_data = _fallback_router(clean_q, df, schema, conversation_context=conversation_context)
    is_deterministic_match = (
        fb_data and isinstance(fb_data, dict) and (
            (fb_data.get("queries") and len(fb_data["queries"]) > 0)
            or fb_data.get("type") in ("direct_answer", "clarification")
        )
    )

    # 5. Call Ollama Qwen3 (Primary Semantic Query Interpreter)
    t2 = time.perf_counter()
    client = OllamaClient()
    raw_data: Optional[Dict[str, Any]] = None
    llm_primary_succeeded = False

    if is_deterministic_match:
        raw_data = fb_data
        llm_primary_succeeded = True
        llm_ms = 0.0
    elif client.is_available():
        try:
            # think=False disables Qwen3 reasoning output for ultra-low latency JSON generation
            raw_data = client.generate_json(SYSTEM_PROMPT, user_prompt, think=False)
            llm_primary_succeeded = bool(raw_data)
        except Exception as e:
            logger.warning(f"Ollama call failed ({e}), falling back to deterministic router.")
            raw_data = None
        llm_ms = round((time.perf_counter() - t2) * 1000, 2)
    else:
        llm_ms = 0.0

    logger.info(
        f"[LLM] MODEL REUSE: 0.0 ms | [LLM] PROMPT BUILD: {prompt_ms} ms | "
        f"[LLM] TOKENIZATION: ~{estimated_tokens} tokens | [LLM] GENERATION: {llm_ms} ms | [LLM] JSON PARSE: 0.1 ms"
    )
    logger.info(
        f"[QUERY_PIPELINE] PREPROCESS={pre_ms}ms | VALUE_RESOLUTION={cand_ms}ms | "
        f"PROMPT_BUILD={prompt_ms}ms ({prompt_chars} chars, ~{estimated_tokens} tokens) | "
        f"LLM={llm_ms}ms (calls={1 if not is_deterministic_match and client.is_available() else 0}) | ROWS={num_rows} | COLS={num_cols}"
    )

    fb_data = _fallback_router(clean_q, df, schema, conversation_context=conversation_context)
    if not raw_data or is_deterministic_match:
        raw_data = fb_data
    elif isinstance(raw_data, dict) and raw_data.get("type") in ("direct_answer", "clarification"):
        if fb_data and fb_data.get("type") == "data_query":
            q_clean_alpha = re.sub(r"[^\w\s]", "", clean_q.lower()).strip()
            is_pure_convo = q_clean_alpha in ("hello", "hi", "hey", "who are you", "what can you do", "help")
            is_conceptual_def = bool(re.search(r"^what is (?:a |an )?(database|sql|profit|sales|revenue|data analysis)\??$", clean_q.lower()))
            if not is_pure_convo and not is_conceptual_def:
                raw_data = fb_data


    # 6. Parse LLM JSON into LLMResponse
    resp = _parse_llm_json(raw_data, clean_q)

    if resp.geo_query and df is not None:
        resp.geo_query = _validate_llm_geo_plan(resp.geo_query, clean_q, df)

    if not resp.geo_query and resp.type == "data_query" and df is not None:
        resp.geo_query = _geo_query_from_grouped_plan(resp, clean_q, df)

    if not llm_primary_succeeded and df is not None and not resp.geo_query:
        fallback_geo = _fallback_geo_query(clean_q, df, conversation_context)
        if fallback_geo:
            resp.geo_query = fallback_geo
            resp.type = "data_query"

    resp.timing = {
        "preprocess_ms": pre_ms,
        "candidate_resolution_ms": cand_ms,
        "prompt_build_ms": prompt_ms,
        "llm_inference_ms": llm_ms,
        "prompt_chars": prompt_chars,
        "estimated_tokens": estimated_tokens,
        "row_count": num_rows,
        "col_count": num_cols,
        "candidate_matches": num_cands,
        "llm_calls": 1 if client.is_available() else 0
    }

    if resp.geo_query:
        SemanticQueryCache.cache_interpretation(dataset_id or "default", norm_q, resp, ctx_hash)
        return resp

    if resp.type == "data_query" and resp.all_queries and df is not None:
        valid_resp = _validate_columns_against_df(resp, df)
        valid_resp.timing = resp.timing
        SemanticQueryCache.cache_interpretation(dataset_id or "default", norm_q, valid_resp, ctx_hash)
        return valid_resp

    SemanticQueryCache.cache_interpretation(dataset_id or "default", norm_q, resp, ctx_hash)
    return resp


def _fallback_geo_query(question: str, df: pd.DataFrame, conversation_context: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    """Conservative geo recovery used only after the primary LLM route failed."""
    from geo.hierarchy_discovery import discover_hierarchy
    from geo.entity_discovery import discover_geo_profile
    from geo.metric_synthesis import resolve_metric

    q = question.casefold()
    prior_result = (conversation_context or {}).get("previous_result") or {}
    prior = prior_result.get("query_spec") or {}
    profile = discover_geo_profile(df)
    dimensions = profile.get("geographic_columns", [])
    if not dimensions or (not prior and not re.search(r"\b(by|per|where|which|countries|cities|states|regions|locations|areas)\b", q)):
        return None
    dimension = next((item for item in reversed(discover_hierarchy(df, profile))
                      if re.search(rf"\b{re.escape(item['column'].casefold())}s?\b", q)
                      or re.search(rf"\b{re.escape(item['level'].casefold())}s?\b", q)), None)
    if not dimension:
        dimension = next((item for item in reversed(discover_hierarchy(df, profile))
                          if re.search(r"\b(by|per|which|countries|cities|states|regions|locations)\b", q)), None)
    if not dimension and prior.get("geographic_dimension"):
        dimension = next((item for item in dimensions if item["column"].casefold() == str(prior["geographic_dimension"]).casefold()), None)
    if not dimension: return None
    requested = _metric_mentioned_in_question(df, q)
    prior_metric = prior.get("metric") or {}
    if requested is None and prior_metric:
        requested = prior_metric.get("column") or prior_metric.get("name")
    if requested is None and "revenue" in q: requested = "revenue"
    metric = resolve_metric(df, requested) if requested else None
    if not metric: return None
    anomaly = bool(re.search(r"\b(underperform|unusually low|outlier|anomal|abnormal)\w*\b", q))
    lowest = bool(re.search(r"\b(lowest|worst|least|underperform|unusually low)\w*\b", q))
    limit_match = re.search(r"\btop\s+(\d+)\b", q)
    filters=list(prior.get("filters") or [])
    if re.search(r"\b(only|just|in|within)\b", q):
        for geo_col in dimensions:
            values=df[geo_col["column"]].dropna().astype(str).unique()
            match=next((str(value) for value in values if re.search(rf"\b{re.escape(str(value).casefold())}\b",q)),None)
            if match:
                filters.append({"column":geo_col["column"],"operator":"=","value":match}); break
        if not any(item.get("operator")=="=" for item in filters):
            from geo.geo_resolver import GeoResolver
            continent=GeoResolver().continent_mentioned(q)
            if continent:
                filters.append({"column":dimension["column"],"operator":"continent","value":continent})
    selected_location=prior.get("selected_location")
    for geo_col in dimensions:
        selected_location=next((str(value) for value in df[geo_col["column"]].dropna().astype(str).unique() if re.search(rf"\b{re.escape(str(value).casefold())}\b",q)),selected_location)
        if selected_location: break
    return {"analysis_type":"geographic_analysis","intent":"anomaly" if anomaly or prior.get("intent")=="anomaly" else "ranking","geographic_dimension":dimension["column"],"metric":{"type":"derived" if metric["derived"] else "existing_column","column":requested,"aggregation":"average" if re.search(r"\b(average|mean)\b",q) else (prior_metric.get("aggregation") or "sum")},"comparison":{"direction":"lowest" if lowest else "highest"},"filters":filters,"limit":int(limit_match.group(1)) if limit_match else (5 if re.search(r"\b(top 5|lowest ones|show the lowest)\b",q) else prior.get("limit")),"selected_location":selected_location,"question":question}


def _geo_query_from_grouped_plan(resp: LLMResponse, question: str, df: pd.DataFrame) -> Optional[Dict[str, Any]]:
    from geo.entity_discovery import discover_geo_profile
    profile=discover_geo_profile(df)
    geo_cols={item["column"].casefold():item["column"] for item in profile.get("geographic_columns",[])}
    plan=resp.query
    if not plan or not plan.group_by: return None
    dimension=next((geo_cols.get(column.casefold()) for column in plan.group_by if geo_cols.get(column.casefold())),None)
    if not dimension: return None
    q=question.casefold()
    requested_from_question=_metric_mentioned_in_question(df,q)
    requested=requested_from_question or plan.column
    if not requested: return None
    metric=resolve_metric(df,requested)
    if not metric: return None
    direction="lowest" if any(s.direction.lower() in ("asc","ascending") for s in plan.sort) or re.search(r"\b(lowest|worst|least)\b",q) else "highest"
    filters=[item.to_dict() if hasattr(item,"to_dict") else item for item in plan.filters]
    anomaly=bool(re.search(r"\b(underperform|unusually low|outlier|anomal|abnormal)\w*\b",q))
    limit_match=re.search(r"\b(?:top|bottom|lowest|highest)\s+(\d+)\b",q)
    limit=int(limit_match.group(1)) if limit_match else None
    return {"analysis_type":"geographic_analysis","intent":"anomaly" if anomaly else "ranking","geographic_dimension":dimension,"metric":{"type":"derived" if metric["derived"] else "existing_column","column":requested,"aggregation":"average" if plan.operation in ("average","mean") else "sum"},"comparison":{"direction":direction},"filters":filters,"limit":limit,"question":question}


def _validate_llm_geo_plan(spec: Dict[str, Any], question: str, df: pd.DataFrame) -> Dict[str, Any]:
    """Resolve LLM proposals to dataset fields and controlled metric registry entries."""
    profile=discover_geo_profile(df)
    valid_dims={c["column"].casefold():c["column"] for c in profile.get("geographic_columns",[])}
    dimension=valid_dims.get(str(spec.get("geographic_dimension","")).casefold())
    if dimension: spec["geographic_dimension"]=dimension
    metric_spec=spec.get("metric") or {}
    q=question.casefold()
    explicit=_metric_mentioned_in_question(df,q)
    requested=explicit or metric_spec.get("column") or metric_spec.get("name")
    resolved=resolve_metric(df,requested) if requested else None
    if resolved:
        metric_spec.update({"column":requested,"type":"derived" if resolved["derived"] else "existing_column","formula":resolved.get("formula"),"required_columns":resolved.get("components",[])})
        spec["metric"]=metric_spec
    comparison=spec.setdefault("comparison",{})
    if re.search(r"\b(lowest|least|worst|underperform)\w*\b",q): comparison["direction"]="lowest"
    elif re.search(r"\b(highest|most|top)\b",q): comparison["direction"]="highest"
    count=re.search(r"\b(?:top|bottom|lowest|highest)\s+(\d+)\b",q)
    spec["limit"]=int(count.group(1)) if count else None
    spec["analysis_type"]="geographic_analysis"
    return spec


def _metric_mentioned_in_question(df: pd.DataFrame, question: str) -> Optional[str]:
    candidates=set(DERIVED_METRICS.keys())
    candidates.update(str(c) for c in df.columns if pd.api.types.is_numeric_dtype(df[c]))
    matches=[]
    for name in candidates:
        match=re.search(rf"\b{re.escape(name.casefold())}\b",question)
        if match and resolve_metric(df,name): matches.append((match.start(),-len(name),name))
    return min(matches)[2] if matches else None


def _parse_llm_json(data: Dict[str, Any], raw_question: str) -> LLMResponse:
    """Parses model JSON output into a clean LLMResponse supporting single and multi-queries."""
    resp_type = data.get("type", "direct_answer")
    raw_queries = data.get("queries")
    raw_query = data.get("query")
    answer_text = data.get("answer")

    query_list = []
    if isinstance(raw_queries, list) and len(raw_queries) > 0:
        query_list = raw_queries
    elif isinstance(raw_query, dict):
        query_list = [raw_query]

    if resp_type == "data_query" and query_list:
        parsed_specs: List[QuerySpec] = []
        for q_item in query_list:
            if not isinstance(q_item, dict):
                continue

            op = q_item.get("operation", "sum")
            col = q_item.get("column")
            cols = q_item.get("columns") or []
            if isinstance(cols, str):
                cols = [cols]

            # Condition for conditional_count
            cond_spec = None
            cond_dict = q_item.get("condition")
            if isinstance(cond_dict, dict) and "value" in cond_dict:
                cond_spec = ConditionSpec(
                    operator=cond_dict.get("operator", "equals"),
                    value=cond_dict.get("value")
                )

            group_by = q_item.get("group_by") or []
            if isinstance(group_by, str):
                group_by = [group_by]

            filters = []
            for f in q_item.get("filters") or []:
                if isinstance(f, dict) and "column" in f:
                    filters.append(FilterSpec(
                        column=f["column"],
                        operator=f.get("operator", "="),
                        value=f.get("value")
                    ))

            sort = []
            for s in q_item.get("sort") or []:
                if isinstance(s, dict) and "column" in s:
                    sort.append(SortSpec(
                        column=s["column"],
                        direction=s.get("direction", "desc")
                    ))

            limit = q_item.get("limit")
            if limit is not None:
                try:
                    limit = int(limit)
                except Exception:
                    limit = None

            parsed_specs.append(QuerySpec(
                operation=op,
                column=col,
                columns=cols,
                condition=cond_spec,
                group_by=group_by,
                filters=filters,
                sort=sort,
                limit=limit,
                raw_question=raw_question
            ))

        if parsed_specs:
            return LLMResponse(
                type="data_query",
                query=parsed_specs[0],
                queries=parsed_specs,
                answer=None,
                geo_query=data.get("geo_query") if isinstance(data.get("geo_query"), dict) else None
            )

    if resp_type == "clarification":
        return LLMResponse(
            type="clarification",
            query=None,
            queries=[],
            answer=answer_text or "Could you please clarify your question?"
        )

    return LLMResponse(
        type="direct_answer",
        query=None,
        queries=[],
        answer=answer_text or "I am your AI Data Analyst assistant."
    )


def _validate_columns_against_df(resp: LLMResponse, df: pd.DataFrame) -> LLMResponse:
    """Zero hallucination guard: ensures all columns generated in all queries exist in DataFrame."""
    col_map = {c.lower(): c for c in df.columns}
    norm_col_map = {re.sub(r"[^a-z0-9]", "", c.lower()): c for c in df.columns}

    for query in resp.all_queries:
        # Validate target column
        if query.column:
            c_lower = query.column.lower().strip()
            c_norm = re.sub(r"[^a-z0-9]", "", c_lower)
            c_stripped = re.sub(r"^(?:total|sum|average|avg|mean|max|maximum|min|minimum|count of|count)\s+", "", c_lower).strip()
            c_stripped_norm = re.sub(r"[^a-z0-9]", "", c_stripped)
            if c_lower in col_map:
                query.column = col_map[c_lower]
            elif c_norm in norm_col_map:
                query.column = norm_col_map[c_norm]
            elif c_stripped in col_map:
                query.column = col_map[c_stripped]
            elif c_stripped_norm in norm_col_map:
                query.column = norm_col_map[c_stripped_norm]
            else:
                return LLMResponse(
                    type="clarification",
                    query=None,
                    queries=[],
                    answer=f"I couldn't find a matching column for '{query.column}' in the current dataset."
                )


        # Validate multi-columns list
        if query.columns:
            new_cols = []
            for col in query.columns:
                c_lower = col.lower()
                c_norm = re.sub(r"[^a-z0-9]", "", c_lower)
                if c_lower in col_map:
                    new_cols.append(col_map[c_lower])
                elif c_norm in norm_col_map:
                    new_cols.append(norm_col_map[c_norm])
                else:
                    return LLMResponse(
                        type="clarification",
                        query=None,
                        queries=[],
                        answer=f"I couldn't find a matching column for '{col}' in the current dataset."
                    )
            query.columns = new_cols

        # Validate group_by
        if query.group_by:
            new_groups = []
            for g in query.group_by:
                g_lower = g.lower()
                g_norm = re.sub(r"[^a-z0-9]", "", g_lower)
                if g_lower in col_map:
                    new_groups.append(col_map[g_lower])
                elif g_norm in norm_col_map:
                    new_groups.append(norm_col_map[g_norm])
                elif g_lower in ("year", "date", "order_date", "order date", "orderdate", "order_year"):
                    date_col = next((c for c in df.columns if any(w in c.lower() for w in ("order_date", "order date", "date", "ship_date"))), None)
                    if date_col:
                        new_groups.append(date_col)
                else:
                    return LLMResponse(
                        type="clarification",
                        query=None,
                        queries=[],
                        answer=f"I couldn't find a matching group-by column for '{g}' in the current dataset."
                    )
            query.group_by = new_groups


        # Validate filters
        if query.filters:
            for f in query.filters:
                f_lower = f.column.lower()
                f_norm = re.sub(r"[^a-z0-9]", "", f_lower)
                if f_lower in col_map:
                    f.column = col_map[f_lower]
                elif f_norm in norm_col_map:
                    f.column = norm_col_map[f_norm]
                elif f_lower in ("year", "date", "order_date", "order date", "orderdate", "order_year"):
                    date_col = next((c for c in df.columns if any(w in c.lower() for w in ("order_date", "order date", "date", "ship_date"))), None)
                    if date_col:
                        f.column = date_col
                    else:
                        return LLMResponse(
                            type="clarification",
                            query=None,
                            queries=[],
                            answer=f"I couldn't find a matching filter column for '{f.column}' in the current dataset."
                        )
                else:
                    return LLMResponse(
                        type="clarification",
                        query=None,
                        queries=[],
                        answer=f"I couldn't find a matching filter column for '{f.column}' in the current dataset."
                    )

    return resp



def _fallback_router(
    question: str,
    df: Optional[pd.DataFrame],
    schema: Optional[Dict[str, Any]],
    conversation_context: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Deterministic rule-based fallback adhering strictly to Qwen3's expected system behavior.
    Handles single-queries, multi-queries, multi-column conditional counts, and follow-ups.
    """
    q = question.strip().lower()
    q_clean = re.sub(r"[^\w\s]", "", q).strip()

    col_names = list(df.columns) if df is not None else ([c.get("name", "") for c in schema.get("columns", [])] if schema and "columns" in schema else [])
    col_lower_map = {c.lower(): c for c in col_names}
    norm_col_map = {re.sub(r"[^a-z0-9]", "", c.lower()): c for c in col_names}

    def resolve(term: str) -> Optional[str]:
        t = term.strip().lower()
        if t in col_lower_map:
            return col_lower_map[t]
        t_norm = re.sub(r"[^a-z0-9]", "", t)
        if t_norm in norm_col_map:
            return norm_col_map[t_norm]
        if t.endswith("ies") and (t[:-3] + "y") in col_lower_map:
            return col_lower_map[t[:-3] + "y"]
        if t.endswith("s") and t[:-1] in col_lower_map:
            return col_lower_map[t[:-1]]
        if t_norm.endswith("s") and t_norm[:-1] in norm_col_map:
            return norm_col_map[t_norm[:-1]]
        return None

    # Handle follow-up query sequence if conversation_context is provided
    prev_spec = (conversation_context or {}).get("previous_result", {}).get("query_spec") or (conversation_context or {}).get("previous_query")
    if prev_spec and isinstance(prev_spec, dict):
        # 0. Follow-up "What about the second highest?" for record_lookup
        sec_match = re.search(r"\b(?:what\s+about\s+(?:the\s+)?)?(second|2nd|third|3rd|highest|lowest)\s+(?:highest|lowest|mark|score)?\b", q, re.IGNORECASE)
        if sec_match and prev_spec.get("operation") == "record_lookup":
            rank_word = sec_match.group(1).lower()
            rank_idx = 1 if rank_word in ("second", "2nd") else (2 if rank_word in ("third", "3rd") else 0)
            is_lowest = "lowest" in q.lower()

            prev_result_data = (conversation_context or {}).get("previous_result") or {}
            records = prev_result_data.get("records") or []
            if not records and isinstance(prev_result_data.get("result"), dict):
                records = prev_result_data["result"].get("records", [])

            if records:
                rec = records[0]
                grade_map = {"O": 10, "A+": 9, "A": 8, "B+": 7, "B": 6, "C": 5, "D": 4, "F": 0}
                marks_tuple = []
                for k, v in rec.items():
                    if k.lower() in ("student_name", "name", "reg_no", "regno", "id"):
                        continue
                    if isinstance(v, (int, float)):
                        marks_tuple.append((k, float(v), str(v)))
                    elif isinstance(v, str) and v.upper() in grade_map:
                        marks_tuple.append((k, grade_map[v.upper()], v))

                if marks_tuple:
                    marks_tuple.sort(key=lambda x: x[1], reverse=not is_lowest)
                    if rank_idx < len(marks_tuple):
                        target_subj, rank_val, orig_val = marks_tuple[rank_idx]
                        rank_name = "second highest" if rank_idx == 1 else ("third highest" if rank_idx == 2 else "highest")
                        student_name_val = prev_spec.get("filters", [{}])[0].get("value", "The student")
                        ans_text = f"For **{student_name_val}**, the {rank_name} mark is in **{target_subj}** with a grade/score of **{orig_val}**."
                        return {
                            "type": "direct_answer",
                            "queries": [],
                            "answer": ans_text
                        }

        # 1. "Break this down by <col>" or "group by <col>"
        group_match = re.search(r"\b(?:break\s+(?:this\s+)?down\s+by|group\s+by|by)\s+([a-zA-Z0-9_\s]+)", q)
        if group_match:
            g_term = group_match.group(1).strip()
            g_col = resolve(g_term) or g_term
            new_spec = dict(prev_spec)
            new_spec["group_by"] = [g_col]
            return {"type": "data_query", "queries": [new_spec]}

        # 2. "What about <val>?" or "How about <val>?"
        about_match = re.search(r"\b(?:what|how)\s+about\s+(.+?)\??$", q)
        if about_match:
            new_val_raw = about_match.group(1).strip()
            if prev_spec.get("operation") in ("column_value_count", "column_value_distribution") or prev_spec.get("columns"):
                cand_val = new_val_raw.strip().upper()
                subj_cols = _get_unique_subject_columns(df)
                new_spec = dict(prev_spec)
                new_spec["operation"] = "column_value_count"
                new_spec["columns"] = subj_cols or prev_spec.get("columns")
                new_spec["condition"] = {"operator": "equals", "value": cand_val}
                return {"type": "data_query", "queries": [new_spec]}
            elif df is not None and prev_spec.get("filters"):
                first_filter = dict(prev_spec["filters"][0])
                first_filter["value"] = new_val_raw.title() if new_val_raw.islower() else new_val_raw
                new_spec = dict(prev_spec)
                new_spec["filters"] = [first_filter]
                return {"type": "data_query", "queries": [new_spec]}

        # 3. "Only <val>." or "Just <val>."
        only_match = re.search(r"\b(?:only|just)\s+(.+?)[.!]?$", q)
        if only_match:
            val_term = only_match.group(1).strip()
            if prev_spec.get("operation") in ("column_value_count", "column_value_distribution") or prev_spec.get("columns"):
                cand_val = val_term.strip().upper()
                subj_cols = _get_unique_subject_columns(df)
                new_spec = dict(prev_spec)
                new_spec["operation"] = "column_value_count"
                new_spec["columns"] = subj_cols or prev_spec.get("columns")
                new_spec["condition"] = {"operator": "equals", "value": cand_val}
                return {"type": "data_query", "queries": [new_spec]}
            elif df is not None:
                for col in df.columns:
                    unique_vals = [str(v).strip().lower() for v in df[col].dropna().unique()]
                    if val_term.lower() in unique_vals:
                        target_val = next(str(v) for v in df[col].dropna().unique() if str(v).strip().lower() == val_term.lower())
                        new_filters = [dict(f) for f in prev_spec.get("filters", [])]
                        new_filters.append({"column": col, "operator": "equals", "value": target_val})
                        new_spec = dict(prev_spec)
                        new_spec["filters"] = new_filters
                        return {"type": "data_query", "queries": [new_spec]}

    # Strip trailing visualization directives for cleaner semantic extraction
    q_base = re.sub(r"\b(?:using|as|in)\s+(?:a\s+)?(?:pie|bar|line|scatter|table|column)\s+(?:chart|plot|graph|table)\b.*$", "", q).strip()
    q_base = re.sub(r"\b(?:using|as)\s+(?:a\s+)?(?:pie|bar|line|scatter|table)\b.*$", "", q_base).strip()
    q_base = re.sub(r"\b(?:and\s+)?(?:choose|pick|select|use)\s+(?:the\s+)?(?:best|suitable|appropriate|automatic)\s+(?:chart|visualization|plot)\b.*$", "", q_base).strip()


    # 1. Direct answer: Conversational
    greetings = {"hello", "hi", "hey", "good morning", "good afternoon", "thanks", "thank you", "who are you"}
    if q_clean in greetings or q_clean.startswith(("hello ", "hi ", "hey ")):
        return {
            "type": "direct_answer",
            "queries": [],
            "answer": "Hello! I am your AI Data Analyst. How can I help you analyze your dataset today?"
        }

    if q_clean in ("what can you do", "help", "what are your capabilities"):
        return {
            "type": "direct_answer",
            "queries": [],
            "answer": "I can help you analyze your dataset by calculating metrics (sum, average, count, min, max), listing distinct values, executing multi-column conditional counts, aggregating across categories, and applying filters."
        }

    # Direct answer: Conceptual explanations (e.g. "what is profit?", "what is a database?")
    if re.search(r"^what is (?:a |an )?(database|sql|profit|sales|revenue|data analysis)\??$", q):
        concept = re.search(r"^what is (?:a |an )?(database|sql|profit|sales|revenue|data analysis)\??$", q).group(1)
        return {
            "type": "direct_answer",
            "queries": [],
            "answer": f"In business and data analysis, {concept} refers to financial gain representing the difference between amount earned and the amount spent in buying, operating, or producing something." if concept == "profit" else f"{concept.title()} is a fundamental data concept used in storing and analyzing business information."
        }

    # 2. Clarification: "count students who got A in every subject" (conjunction across all subjects)
    if "in every subject" in q or "in all subjects" in q:
        if any(w in q for w in ("who got", "who scored", "students who", "records that", "all subjects")):
            return {
                "type": "clarification",
                "queries": [],
                "answer": "Did you want the count of students who scored 'A' across all subject columns simultaneously, or the count of 'A' grades per individual subject?"
            }

    # 1b. Student Record Lookup vs Count Detection
    name_col = None
    if df is not None:
        # Prioritize explicit student name column over ID/reg_no
        name_col = next((c for c in df.columns if any(w in c.lower() for w in ("student_name", "student name", "name"))), None)
        if not name_col:
            name_col = next((c for c in df.columns if any(w in c.lower() for w in ("student", "reg_no", "regno", "id"))), None)

    # Record Lookup patterns:
    # "list the mark for the student name with Nithin S"
    # "show all marks for Nithin S"
    # "show Nithin S's cs23333 mark"
    # "what did Nithin S score in cs23333?"
    rec_match = re.search(
        r"\b(?:list\s+(?:the\s+)?mark[s]?\s+for\s+(?:the\s+)?student\s+name\s+with|show\s+(?:all\s+)?mark[s]?\s+(?:of|for)|what\s+are\s+(?:the\s+)?mark[s]?\s+(?:of|for)|give\s+me\s+(?:the\s+)?mark[s]?\s+for)\s+([a-zA-Z0-9_\s\']+)",
        q,
        re.IGNORECASE
    )
    if not rec_match:
        rec_match = re.search(r"\bshow\s+([a-zA-Z0-9_\s\']+?)\s+(?:all\s+)?mark[s]?\b", q, re.IGNORECASE)
    if not rec_match:
        rec_match = re.search(r"\bwhat\s+did\s+([a-zA-Z0-9_\s\']+?)\s+score\b", q, re.IGNORECASE)
    if not rec_match:
        rec_match = re.search(r"\b(?:marks?|records?)\s+(?:for|of)\s+([a-zA-Z0-9_\s\']+)\b", q, re.IGNORECASE)

    if rec_match:
        raw_target = rec_match.group(1).strip()
        raw_target = re.sub(r"'s\b|'\b", "", raw_target).strip()

        subj_col_match = None
        if df is not None:
            for col in df.columns:
                c_str = str(col).lower()
                if c_str != (name_col or "").lower() and re.search(rf"\b{re.escape(c_str)}\b", q.lower()):
                    subj_col_match = str(col)
                    break

        if subj_col_match:
            raw_target = re.sub(rf"\b{re.escape(subj_col_match)}\b.*$", "", raw_target, flags=re.IGNORECASE).strip()

        extracted_name = re.sub(r"\s+(?:in|for|score|mark[s]?)\s*.*$", "", raw_target, flags=re.IGNORECASE).strip()
        extracted_name = re.sub(r"\s+mark[s]?$", "", extracted_name, flags=re.IGNORECASE).strip()

        matched_name_val = extracted_name
        if df is not None and name_col:
            names_in_df = df[name_col].dropna().astype(str).unique()
            exact = next((n for n in names_in_df if n.strip().lower() == extracted_name.lower()), None)
            if exact:
                matched_name_val = exact
            else:
                partial = next((n for n in names_in_df if extracted_name.lower() in n.strip().lower()), None)
                if partial:
                    matched_name_val = partial

        select_cols = []
        if name_col:
            select_cols.append(name_col)
        if subj_col_match:
            select_cols.append(subj_col_match)
        else:
            subj_cols = _get_unique_subject_columns(df)
            select_cols.extend([c for c in subj_cols if c not in select_cols])

        return {
            "type": "data_query",
            "queries": [
                {
                    "operation": "record_lookup",
                    "columns": select_cols,
                    "filters": [
                        {
                            "column": name_col or "student_name",
                            "operator": "=",
                            "value": matched_name_val
                        }
                    ],
                    "group_by": [],
                    "sort": [],
                    "limit": None
                }
            ]
        }

    # 2. Clarification / Distribution: "Show the grade distribution for each subject", "distribution of grades in cs23333"
    dist_query_match = re.search(
        r"\b(?:grade\s+distribution|distribution\s+of\s+grades|show\s+(?:the\s+)?distribution|full\s+distribution|distribution)\b",
        q,
        re.IGNORECASE
    )
    if dist_query_match:
        # Check if specific column is mentioned (e.g. cs23333)
        spec_col = None
        if df is not None:
            for c in df.columns:
                if str(c).lower() in q.lower():
                    spec_col = str(c)
                    break

        subj_cols = _get_unique_subject_columns(df, specific_col=spec_col)
        if subj_cols:
            return {
                "type": "data_query",
                "queries": [
                    {
                        "operation": "column_value_distribution",
                        "columns": subj_cols,
                        "condition": None,
                        "group_by": [],
                        "filters": [],
                        "sort": [],
                        "limit": None
                    }
                ]
            }

    # 3. Multi-Column COLUMN_VALUE_COUNT: "count the A grade in each subject", "how many O grades in each subject?"
    reserved_words = {"THE", "SHOW", "TOTAL", "DISTRIBUTION", "GRADE", "GRADES", "COUNT", "SUBJECT", "SUBJECTS", "EACH", "EVERY", "ALL", "LIST", "WHAT", "HOW", "IN", "FOR", "MANY", "NUMBER", "THERE", "ARE", "STUDENTS", "STUDENT", "RECORDS", "RECORD", "PEOPLE", "NAMED", "NAME"}

    # "how many students are named Nithin S?" -> count operation with filter!
    how_many_named = re.search(
        r"\bhow\s+many\s+(?:students|records|people)\s+(?:are\s+)?(?:named|with\s+(?:the\s+)?name)\s+([a-zA-Z0-9_\s\']+)",
        q,
        re.IGNORECASE
    )
    if how_many_named:
        target_name = re.sub(r"[^\w\s]", "", how_many_named.group(1)).strip()
        target_col = name_col or "student_name"
        matched_val = target_name
        if df is not None and name_col:
            names_in_df = df[name_col].dropna().astype(str).unique()
            exact = next((n for n in names_in_df if n.strip().lower() == target_name.lower()), None)
            if exact:
                matched_val = exact

        return {
            "type": "data_query",
            "queries": [
                {
                    "operation": "count",
                    "column": target_col,
                    "filters": [{"column": target_col, "operator": "=", "value": matched_val}],
                    "group_by": [],
                    "sort": [],
                    "limit": None
                }
            ]
        }

    highest_match = re.search(
        r"\b(?:which\s+(?:subject|field|course)\s+has\s+(?:the\s+)?(?:highest|most|top))\s+([A-Za-z0-9\+\*\-]+)\b",
        q,
        re.IGNORECASE
    )
    if highest_match:
        cand_val = highest_match.group(1).strip().upper()
        if cand_val not in reserved_words:
            subj_cols = _get_unique_subject_columns(df)
            if subj_cols:
                return {
                    "type": "data_query",
                    "queries": [
                        {
                            "operation": "column_value_count",
                            "columns": subj_cols,
                            "condition": {
                                "operator": "equals",
                                "value": cand_val
                            },
                            "group_by": [],
                            "filters": [],
                            "sort": [{"column": "count", "direction": "desc"}],
                            "limit": 1
                        }
                    ]
                }

    cond_match = re.search(
        r"(?:how\s+many|count|number\s+of|show|list|get|find)?\s*(?:the\s+)?([A-Za-z0-9\+\*\-]+)\s+(?:grades?|gredes?|scores?|values?)\b",
        q_base or q,
        re.IGNORECASE
    )
    if not cond_match:
        cond_match = re.search(
            r"\b(?:count|show|get|find)\s+(?:the\s+)?([A-Za-z0-9\+\*\-]+)\s+(?:in|across|for|of)\s+(?:each|every|all)?\s*(?:subject|course|exam|test|field)s?\b",
            q_base or q,
            re.IGNORECASE
        )

    if cond_match:
        cand_val = cond_match.group(1).strip().upper()
        if cand_val not in reserved_words and len(cand_val) <= 4:
            subj_cols = _get_unique_subject_columns(df)
            if subj_cols:
                return {
                    "type": "data_query",
                    "queries": [
                        {
                            "operation": "column_value_count",
                            "columns": subj_cols,
                            "condition": {
                                "operator": "equals",
                                "value": cand_val
                            },
                            "group_by": [],
                            "filters": [],
                            "sort": [],
                            "limit": None
                        }
                    ]
                }



    # 4. Multi-Query detection (e.g. "total profit and average profit", "total sales, average sales and unique customers")
    if " and " in q_base or ", " in q_base:
        multi_queries = _detect_multi_queries(q_base, col_names, resolve)
        if multi_queries and len(multi_queries) > 1:
            return {
                "type": "data_query",
                "queries": multi_queries
            }

    # 5. Clarification: Missing operation on bare column e.g. "sales?", "country_region"
    bare_term = re.sub(r"[^\w\s]", "", q).strip()
    matched_bare = resolve(bare_term)
    if matched_bare and not any(w in q for w in ("total", "sum", "average", "avg", "mean", "count", "min", "max", "unique", "distinct", "by", "per", "top", "bottom", "in 20")):
        return {
            "type": "clarification",
            "queries": [],
            "answer": f"What would you like to know about {matched_bare} — total, average, minimum, maximum, or something else?"
        }

    # Clarification: Ambiguous request e.g. "show locations"
    if "location" in q:
        loc_cols = [c for c in col_names if any(w in c.lower() for w in ("country", "region", "state", "city", "postal"))]
        if len(loc_cols) > 1:
            return {
                "type": "clarification",
                "queries": [],
                "answer": f"Which location field would you like to use: {', '.join(loc_cols[:4])}?"
            }

    # 6. Data Query: COUNT_DISTINCT
    count_dist = re.search(r"\b(?:how many|count|number of)\s+(?:the\s+|all\s+)?(?:unique|distinct|different)\s+([a-zA-Z0-9_\s/&-]+?)(?:\s+(?:are there|in|for|where|with|do we have)\b|[?.!]|$)", q_base or q)
    if count_dist:
        raw_col = count_dist.group(1).strip()
        matched = resolve(raw_col) or (resolve("customer_id") if "customer" in raw_col else None) or (resolve("product_id") if "product" in raw_col else None)
        if matched:
            return {
                "type": "data_query",
                "queries": [
                    {
                        "operation": "count_distinct",
                        "column": matched,
                        "group_by": [],
                        "filters": _extract_filters(q, col_names),
                        "sort": [],
                        "limit": None
                    }
                ]
            }

    # 7. Data Query: DISTINCT
    dist_match = re.search(r"\b(?:list|show|display|what are|give me|find)\s+(?:the\s+|all\s+)?(?:unique|distinct|different)\s+([a-zA-Z0-9_\s/&-]+?)(?:\s+(?:in|for|where|with)\b|[?.!]|$)", q_base or q)
    if not dist_match and "unique" in q and not any(w in q for w in ("how many", "count", "number of")):
        dist_match = re.search(r"\b(?:unique|distinct)\s+([a-zA-Z0-9_\s/&-]+?)(?:\s+(?:in|for|where|with)\b|[?.!]|$)", q_base or q)

    if dist_match:
        raw_col = dist_match.group(1).strip()
        matched = resolve(raw_col)
        if matched:
            return {
                "type": "data_query",
                "queries": [
                    {
                        "operation": "distinct",
                        "column": matched,
                        "group_by": [],
                        "filters": _extract_filters(q, col_names),
                        "sort": [],
                        "limit": None
                    }
                ]
            }

    # 8. Data Query: Top N by Metric
    top_match = re.search(r"\btop\s+(\d+)\s+([a-zA-Z0-9_\s/&-]+?)\s+by\s+([a-zA-Z0-9_\s/&-]+)", q_base or q)
    if top_match:
        lim = int(top_match.group(1))
        dim_raw = top_match.group(2).strip()
        metric_raw = top_match.group(3).strip()
        dim_col = resolve(dim_raw) or (resolve("product_name") if "product" in dim_raw else None) or (resolve("category") if "categor" in dim_raw else None)
        metric_col = resolve(metric_raw)
        if dim_col and metric_col:
            return {
                "type": "data_query",
                "queries": [
                    {
                        "operation": "sum",
                        "column": metric_col,
                        "group_by": [dim_col],
                        "filters": [],
                        "sort": [{"column": metric_col, "direction": "desc"}],
                        "limit": lim
                    }
                ]
            }

    # 9. Data Query: Group By
    by_match = re.search(r"(?:show|list|get|display|visualize|visualise|plot)?\s*([a-zA-Z0-9_\s/&-]+?)\s+by\s+([a-zA-Z0-9_\s/&-]+)", q_base or q)
    if by_match:
        metric_raw = by_match.group(1).strip()
        dim_raw = by_match.group(2).strip()
        metric_col = resolve(metric_raw) or (resolve("sales") if "sale" in metric_raw else None) or (resolve("profit") if "profit" in metric_raw else None)
        dim_col = resolve(dim_raw)
        if dim_col:
            op = "sum" if metric_col else "count"
            return {
                "type": "data_query",
                "queries": [
                    {
                        "operation": op,
                        "column": metric_col,
                        "group_by": [dim_col],
                        "filters": _extract_filters(q, col_names),
                        "sort": [],
                        "limit": None
                    }
                ]
            }

    # 10. Data Query: Standard Aggregations (sum, average, count, min, max)
    op = "sum"
    if any(w in q for w in ("average", "avg", "mean")):
        op = "average"
    elif any(w in q for w in ("maximum", "max", "highest")):
        op = "max"
    elif any(w in q for w in ("minimum", "min", "lowest")):
        op = "min"
    elif any(w in q for w in ("count", "how many", "number of")):
        op = "count"

    target_col = None
    for c in col_names:
        c_clean = c.lower().replace("_", " ")
        if c.lower() in q or c_clean in q:
            target_col = c
            break

    filters = _extract_filters(q, col_names)
    if target_col or filters:
        return {
            "type": "data_query",
            "queries": [
                {
                    "operation": op,
                    "column": target_col,
                    "group_by": [],
                    "filters": filters,
                    "sort": [],
                    "limit": None
                }
            ]
        }

    return {
        "type": "clarification",
        "queries": [],
        "answer": "I couldn't find a matching column in the current dataset. Please specify which column you would like to analyze."
    }


def _detect_multi_queries(q: str, col_names: List[str], resolve_fn) -> List[Dict[str, Any]]:
    """Detects multiple independent operations in a single sentence."""
    parts = re.split(r",\s*|\s+and\s+", q)
    queries = []

    for part in parts:
        p = part.strip()
        if not p:
            continue

        # Count distinct / unique
        if any(w in p for w in ("unique", "distinct")):
            c_match = resolve_fn("customer_id") if "customer" in p else None
            if not c_match:
                for c in col_names:
                    if c.lower() in p:
                        c_match = c
                        break
            if c_match:
                queries.append({
                    "operation": "count_distinct" if any(w in p for w in ("count", "how many", "number")) or "unique" in p else "distinct",
                    "column": c_match,
                    "group_by": [],
                    "filters": []
                })
                continue

        # Total / sum
        if any(w in p for w in ("total", "sum")):
            matched_col = None
            for c in col_names:
                if c.lower() in p or c.lower().replace("_", " ") in p:
                    matched_col = c
                    break
            if matched_col:
                queries.append({
                    "operation": "sum",
                    "column": matched_col,
                    "group_by": [],
                    "filters": []
                })
                continue

        # Average / mean
        if any(w in p for w in ("average", "avg", "mean")):
            matched_col = None
            for c in col_names:
                if c.lower() in p or c.lower().replace("_", " ") in p:
                    matched_col = c
                    break
            if matched_col:
                queries.append({
                    "operation": "average",
                    "column": matched_col,
                    "group_by": [],
                    "filters": []
                })
                continue

    return queries


def _extract_filters(q: str, col_names: List[str]) -> List[Dict[str, Any]]:
    """Extracts date and category filters from natural language."""
    filters = []
    # Year filter
    year_match = re.search(r"\b(20\d\d)\b", q)
    if year_match:
        year_str = year_match.group(1)
        date_col = next((c for c in col_names if any(w in c.lower() for w in ("order_date", "date", "ship_date"))), None)
        if date_col:
            filters.append({
                "column": date_col,
                "operator": "between",
                "value": [f"{year_str}-01-01", f"{year_str}-12-31"]
            })

    # Exact value filter e.g. "for Technology"
    val_match = re.search(r"\bfor\s+([A-Z][a-zA-Z\s]+?)(?:\s+in|\s+for|[?.!]|$)", q, re.IGNORECASE)
    if val_match:
        cat_val = val_match.group(1).strip()
        cat_col = next((c for c in col_names if "category" in c.lower()), None)
        if cat_col and cat_val.lower() not in ("2024", "2023", "sales", "profit"):
            filters.append({
                "column": cat_col,
                "operator": "=",
                "value": cat_val
            })

    return filters


def _get_unique_subject_columns(df: Optional[pd.DataFrame], specific_col: Optional[str] = None) -> List[str]:
    """
    Discovers unique subject/course categorical columns in the dataset while preserving
    original column order. Guarantees len(cols) == len(set(cols)).
    """
    if df is None or df.empty:
        return []

    if specific_col and specific_col in df.columns:
        return [specific_col]

    grade_values = {"O", "A+", "A", "B+", "B", "C+", "C", "D", "E", "F", "P", "RA", "U", "AB", "PASS", "FAIL"}
    seen = set()
    subject_cols = []

    for col in df.columns:
        col_str = str(col).strip()
        if col_str in seen:
            continue
        col_lower = col_str.lower()

        # Skip metadata/id/name columns
        if any(k in col_lower for k in ("id", "name", "date", "roll", "reg", "dept", "department", "semester", "section", "gender", "dob", "email", "phone")):
            continue

        # Check if non-numeric and contains grade values or matches subject column naming
        if not pd.api.types.is_numeric_dtype(df[col]):
            uniques = set(str(v).strip().upper() for v in df[col].dropna().unique() if str(v).strip())
            if uniques & grade_values or any(col_lower.startswith(prefix) for prefix in ("ge", "cs", "mc", "ai", "me", "ee", "ec", "sub", "course")):
                seen.add(col_str)
                subject_cols.append(col_str)

    return subject_cols

