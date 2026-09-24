"""
LLM Query Processor using local Ollama (qwen3:8b).
Translates user queries into structured LLMResponse supporting single-query,
multi-query, and multi-column conditional counts.
"""

import logging
import re
from typing import Any, Dict, List, Optional
import pandas as pd

from llm import OllamaClient, SYSTEM_PROMPT, build_dataset_context, build_user_prompt
from .models import LLMResponse, QuerySpec, FilterSpec, SortSpec, ConditionSpec
from geo.entity_discovery import discover_geo_profile
from geo.metric_synthesis import resolve_metric, DERIVED_METRICS

logger = logging.getLogger(__name__)


def process_query_with_llm(
    question: str,
    schema: Optional[Dict[str, Any]] = None,
    profile: Optional[Dict[str, Any]] = None,
    df: Optional[pd.DataFrame] = None,
    dataset_id: Optional[str] = None,
    conversation_context: Optional[Dict[str, Any]] = None
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

    # 1. Build Dataset Context & User Prompt
    dataset_context = build_dataset_context(schema, profile, df, dataset_id)
    user_prompt = build_user_prompt(clean_q, dataset_context, conversation_context)

    # 2. Call Ollama Qwen3:8b
    client = OllamaClient()
    raw_data: Optional[Dict[str, Any]] = None

    llm_primary_succeeded = False
    if client.is_available():
        try:
            raw_data = client.generate_json(SYSTEM_PROMPT, user_prompt)
            llm_primary_succeeded = bool(raw_data)
        except Exception as e:
            logger.warning(f"Ollama call failed ({e}), falling back to deterministic router.")
            raw_data = None

    if not raw_data or (isinstance(raw_data, dict) and raw_data.get("type") == "clarification" and "couldn't find a matching column" in str(raw_data.get("answer", "")).lower()):
        fb_data = _fallback_router(clean_q, df, schema)
        if not raw_data or fb_data.get("type") == "data_query":
            raw_data = fb_data


    # 3. Parse LLM JSON into LLMResponse
    resp = _parse_llm_json(raw_data, clean_q)

    if resp.geo_query and df is not None:
        resp.geo_query = _validate_llm_geo_plan(resp.geo_query, clean_q, df)

    # Some model responses express a geo plan as a normal grouped QuerySpec.
    # Normalize that structured LLM plan into the geo contract before legacy
    # validation (which cannot validate a registered derived measure).
    if not resp.geo_query and resp.type == "data_query" and df is not None:
        resp.geo_query = _geo_query_from_grouped_plan(resp, clean_q, df)

    # Emergency only: when Ollama is genuinely unavailable, adapt the existing
    # deterministic fallback result into the validated geo contract.
    if not llm_primary_succeeded and df is not None and not resp.geo_query:
        fallback_geo = _fallback_geo_query(clean_q, df, conversation_context)
        if fallback_geo:
            resp.geo_query = fallback_geo
            resp.type = "data_query"

    # Geographic plans have their own strict schema/data validator. The legacy
    # QuerySpec validator would incorrectly reject safe derived metrics.
    if resp.geo_query:
        return resp

    # 4. Zero Hallucination & Column Validation Guard
    if resp.type == "data_query" and resp.all_queries and df is not None:
        valid_resp = _validate_columns_against_df(resp, df)
        return valid_resp

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
    schema: Optional[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Deterministic rule-based fallback adhering strictly to Qwen3's expected system behavior.
    Handles single-queries, multi-queries, and multi-column conditional counts.
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

    # 3. Multi-Column CONDITIONAL_COUNT: "list the A grade count in each subject code"
    cond_match = re.search(
        r"(?:list|show|count|get|find|give me|visualize|visualise|plot|display)?\s*(?:the\s+)?([A-Za-z0-9\+\*\-]+)\s+(?:grade|score|status|value)?\s*count\s+(?:in|for|across|of)\s+(?:each|every|all)\s+([a-zA-Z0-9_\s]+)",
        q_base or q
    )
    if not cond_match:
        cond_match = re.search(
            r"(?:count|number of)\s+(?:students\s+with\s+|records\s+with\s+)?([A-Za-z0-9\+\*\-]+)\s+(?:in|for|across)\s+(?:each|every|all)\s+([a-zA-Z0-9_\s]+)",
            q_base or q
        )

    if cond_match:
        target_val = cond_match.group(1).strip().upper()
        target_category_desc = cond_match.group(2).strip().lower()

        # Find all relevant columns where sample values contain this value or match the description
        matched_columns = []
        if df is not None:
            for col in df.columns:
                # Check unique values in column
                unique_vals = [str(v).strip().upper() for v in df[col].dropna().unique()]
                if target_val in unique_vals:
                    matched_columns.append(col)
                elif any(kw in target_category_desc for kw in ("subject", "course", "exam", "grade", "test")) and any(c.isalpha() for c in str(col)):
                    if not pd.api.types.is_numeric_dtype(df[col]) and not any(k in str(col).lower() for k in ("id", "name", "date", "roll", "reg")):
                        matched_columns.append(col)

        if matched_columns:
            return {
                "type": "data_query",
                "queries": [
                    {
                        "operation": "conditional_count",
                        "columns": matched_columns,
                        "condition": {
                            "operator": "equals",
                            "value": target_val
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
