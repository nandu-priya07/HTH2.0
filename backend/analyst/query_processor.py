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
from .semantics import apply_semantic_layer, fallback_spec_for_concept, resolve_concept
from .follow_up import resolve_analytical_follow_up

logger = logging.getLogger(__name__)

DISTRIBUTION_PATTERNS = [
    r"\beach\s+grade['s]*\s+count\b",
    r"\beach\s+grade\b",
    r"\ball\s+grades\b",
    r"\ball\s+grade\b",
    r"\bgrade[- ]wise\s+count\b",
    r"\bcount\s+of\s+each\s+grade\b",
    r"\bgrade\s+distribution\b",
    r"\bdistribution\s+of\s+grades?\b",
    r"\ball\s+grade\s+counts?\b",
    r"\beach\s+grade\s+counts?\b",
    r"\bhow\s+many\s+students\s+got\s+each\s+grade\b",
    r"\bcount\s+each\s+grade\b",
    r"\bcount\s+every\s+grade\b",
    r"\bevery\s+grade\b",
]

NON_GRADE_QUANTIFIERS = {
    "EACH", "ALL", "EVERY", "ANY", "TOTAL", "THE", "THIS", "THAT",
    "SOME", "ONE", "WHOLE", "ENTIRE", "DISTINCT", "DIFFERENT", "UNIQUE",
    "FULL", "COMPLETE", "DISTRIBUTION", "SUMMARY", "OVERALL", "A", "AN"
}


def _detect_subject_columns(
    df: Optional[pd.DataFrame] = None,
    schema: Optional[Dict[str, Any]] = None
) -> List[str]:
    """
    Dynamically identifies columns representing subjects/courses containing categorical grades.
    Uses schema metadata and DataFrame content inspection without hardcoding dataset-specific column names.
    """
    candidate_cols = []
    if df is not None:
        candidate_cols = list(df.columns)
    elif schema and "columns" in schema:
        candidate_cols = [c.get("name", "") for c in schema.get("columns", [])]
    elif schema and "categorical_columns" in schema:
        candidate_cols = list(schema.get("categorical_columns", []))

    if not candidate_cols:
        return []

    excluded_keywords = {
        "id", "name", "roll", "reg", "registration", "date", "time", "gender",
        "sex", "email", "phone", "address", "dept", "department", "branch",
        "section", "sem", "semester", "year", "batch", "gpa", "cgpa", "sgpa",
        "rank", "total", "percentage", "percent", "average", "avg", "status"
    }

    detected = []
    for col in candidate_cols:
        col_str = str(col).strip()
        col_lower = col_str.lower()
        col_clean = re.sub(r"[^a-z0-9]", "", col_lower)

        if any(kw == col_lower or kw in col_lower.split("_") or kw == col_clean for kw in excluded_keywords):
            continue

        if df is not None and col in df.columns:
            series = df[col]
            if (
                pd.api.types.is_numeric_dtype(series)
                or pd.api.types.is_datetime64_any_dtype(series)
                or pd.api.types.is_bool_dtype(series)
            ):
                continue

            non_null = series.dropna()
            if len(non_null) == 0:
                continue

            unique_vals = [str(v).strip() for v in non_null.unique() if str(v).strip()]
            n_unique = len(unique_vals)

            if not (1 <= n_unique <= 30):
                continue

            avg_len = sum(len(s) for s in unique_vals) / n_unique if n_unique > 0 else 0
            max_len = max(len(s) for s in unique_vals) if n_unique > 0 else 0

            if max_len <= 10 and avg_len <= 6:
                detected.append(col)

        elif schema and "columns" in schema:
            col_meta = next((c for c in schema["columns"] if c.get("name") == col), None)
            if col_meta:
                sem_type = col_meta.get("semantic_type")
                u_cnt = col_meta.get("unique_count", 0)
                if sem_type in ("categorical", "unknown") and 1 <= u_cnt <= 30:
                    detected.append(col)

    return detected


def _normalize_distribution_query_spec(
    spec: QuerySpec,
    raw_question: str,
    df: Optional[pd.DataFrame] = None,
    schema: Optional[Dict[str, Any]] = None
) -> None:
    """
    Ensures user questions asking for grade distributions or 'each grade' counts
    never incorrectly assume a default single grade (e.g. 'A') or put subject columns into group_by.
    """
    q_lower = raw_question.lower()
    is_dist = any(re.search(pat, q_lower) for pat in DISTRIBUTION_PATTERNS)

    # Check if user explicitly asked for specific grades (e.g., "only B", "how many A grades", "A and B")
    named_grades = set()
    # Check multi-grade pair: "A and B counts", "A and B grades", "compare A and B"
    pair_m = re.search(r"\b([A-Fa-f0-9\+\*\-]|RA|PASS|FAIL)\s+and\s+([A-Fa-f0-9\+\*\-]|RA|PASS|FAIL)\b", q_lower)
    if pair_m:
        v1, v2 = pair_m.group(1).strip().upper(), pair_m.group(2).strip().upper()
        # In explicit pairs like "A and B", A is a grade symbol, not an English article
        named_grades.add(v1)
        named_grades.add(v2)

    # Check "how many X grades", "X grade count", "only X"
    for m in re.finditer(r"\b([A-Fa-f0-9\+\*\-]|RA|PASS|FAIL)\s+grades?\b|\bgrades?\s+([A-Fa-f0-9\+\*\-]|RA)\b|\bonly\s+([A-Za-z0-9\+\*\-]+)\b", q_lower):
        for g in m.groups():
            if g:
                val = g.strip().upper()
                if val not in NON_GRADE_QUANTIFIERS:
                    named_grades.add(val)

    if is_dist and not named_grades:
        # General distribution requested: condition MUST be None
        spec.condition = None
        # Subject columns must NOT be in group_by
        if spec.group_by and not spec.columns:
            spec.columns = list(spec.group_by)
        spec.group_by = []

        is_multi_subject = any(w in q_lower for w in ("each subject", "all subjects", "every subject", "across subjects", "subjects", "subject-wise"))
        if is_multi_subject or len(spec.columns) > 1 or not spec.column:
            spec.operation = "multi_column_value_distribution"
            if not spec.columns:
                spec.columns = _detect_subject_columns(df, schema)
            spec.column = None
        else:
            spec.operation = "value_distribution"
            if not spec.columns and spec.column:
                spec.columns = [spec.column]

        spec.measure = "count"
        spec.value_distribution = True

    elif (is_dist or len(named_grades) > 1) and len(named_grades) > 1:
        # Multi-grade subset requested
        spec.operation = "multi_column_value_distribution"
        spec.condition = ConditionSpec(operator="in", value=sorted(list(named_grades)))
        spec.group_by = []
        if not spec.columns:
            spec.columns = _detect_subject_columns(df, schema)
        spec.measure = "count"
        spec.value_distribution = True

    # "how many A grades in each subject": a single planner column must expand to every subject column.
    if spec.operation == "conditional_count" and len(spec.columns) <= 1 and re.search(
            r"\b(?:each|every|all|across)\s+(?:the\s+)?subjects?\b|\bsubject[- ]wise\b|\beach\s+subject\s+codes?\b", q_lower):
        detected = _detect_subject_columns(df, schema)
        if len(detected) > 1:
            spec.columns = detected
            spec.column = None

    if spec.operation in ("conditional_count", "multi_column_value_distribution") and spec.columns:
        if spec.group_by and set(spec.group_by).issubset(set(spec.columns)):
            spec.group_by = []


def process_query_with_llm(
    question: str,
    schema: Optional[Dict[str, Any]] = None,
    profile: Optional[Dict[str, Any]] = None,
    df: Optional[pd.DataFrame] = None,
    dataset_id: Optional[str] = None,
    previous_query: Optional[Dict[str, Any]] = None
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
    if re.search(r"\b(?:in\s+every\s+subject|across\s+all\s+subjects\s+simultaneously)\b", q_lower) and "got" in q_lower:
        return LLMResponse(
            type="clarification",
            answer="Would you like to count how many students received an 'A' grade across all subjects simultaneously, or view the count of 'A' grades for each individual subject?"
        )
    if q_clean_alpha in ("show locations", "locations", "list locations"):
        loc_cols = [c for c in (df.columns if df is not None else []) if any(w in c.lower() for w in ("country", "region", "state", "city", "postal"))]
        return LLMResponse(
            type="clarification",
            answer=f"Which location field would you like to use: {', '.join(loc_cols[:4])}?" if loc_cols else "Which location column would you like to view?"
        )

    # Bare column name ("sales?") names a field but no operation: ask instead of guessing one.
    if df is not None:
        bare_norm = re.sub(r"[^a-z0-9]", "", q_clean_alpha)
        bare_col = next((c for c in df.columns if re.sub(r"[^a-z0-9]", "", str(c).lower()) == bare_norm), None)
        if bare_col and not previous_query:
            return LLMResponse(
                type="clarification",
                answer=f"What would you like to know about {bare_col} — total, average, minimum, maximum, or something else?"
            )

    # Short aggregate follow-ups ("what about Germany?", "only First Class", "break this down by
    # region", "average instead") are resolved deterministically against the previous plan.
    if previous_query and df is not None:
        follow_spec = resolve_analytical_follow_up(clean_q, previous_query, df)
        if follow_spec is not None:
            return apply_semantic_layer(
                LLMResponse(type="data_query", query=follow_spec, queries=[follow_spec]), clean_q, df)

    # 1. Build Dataset Context & User Prompt
    dataset_context = build_dataset_context(schema, profile, df, dataset_id)
    user_prompt = build_user_prompt(clean_q, dataset_context, previous_query=previous_query)

    # 2. Call Ollama Qwen3:8b
    client = OllamaClient()
    raw_data: Optional[Dict[str, Any]] = None

    if client.is_available():
        try:
            raw_data = client.generate_json(SYSTEM_PROMPT, user_prompt)
        except Exception as e:
            logger.warning(f"Ollama call failed ({e}), falling back to deterministic router.")
            raw_data = None

    if not raw_data or (isinstance(raw_data, dict) and raw_data.get("type") == "clarification" and "couldn't find a matching column" in str(raw_data.get("answer", "")).lower()):
        fb_data = _fallback_router(clean_q, df, schema)
        if not raw_data or fb_data.get("type") == "data_query":
            raw_data = fb_data


    # 3. Parse LLM JSON into LLMResponse
    resp = _parse_llm_json(raw_data, clean_q)

    # 3.1 Drop categorical filters the user never asked for (the planner sometimes copies
    #     values from the sample rows). Follow-ups may legitimately inherit filters.
    if resp.type == "data_query":
        inherited = {(str(f.get("column")).lower(), str(f.get("value")).lower())
                     for f in ((previous_query or {}).get("filters") or []) if isinstance(f, dict)}
        for q_item in resp.all_queries:
            q_item.filters = [f for f in q_item.filters
                              if (str(f.column).lower(), str(f.value).lower()) in inherited
                              or _filter_is_grounded(f, clean_q)]

    # 3a. The planner sometimes splits "A count in each subject" into one query per column;
    #     merge same-condition conditional counts into a single multi-column query.
    qs = resp.all_queries
    if resp.type == "data_query" and len(qs) > 1 and all(q.operation == "conditional_count" for q in qs):
        conds = {(str(q.condition.operator), str(q.condition.value)) if q.condition else None for q in qs}
        merged_cols = list(dict.fromkeys(c for q in qs for c in (q.columns or ([q.column] if q.column else []))))
        # group_by on the subject columns themselves is a planner artifact, not a real grouping.
        spurious_groups = all(set(q.group_by) <= set(merged_cols) for q in qs)
        if len(conds) == 1 and spurious_groups and not any(q.filters for q in qs):
            merged = qs[0].model_copy(update={"column": None, "columns": merged_cols, "group_by": []})
            resp = LLMResponse(type="data_query", query=merged, queries=[merged])

    # 3b. Normalize grade distribution specs
    if resp.type == "data_query" and resp.all_queries:
        for q_item in resp.all_queries:
            _normalize_distribution_query_spec(q_item, clean_q, df, schema)

    # 3c. A clarification like "there is no revenue column" must not skip the derivation check:
    #     if the question names a registry metric that is derivable or definitively unavailable,
    #     plan it deterministically so the semantic layer can answer or explain precisely.
    if resp.type == "clarification" and df is not None:
        fb_spec = fallback_spec_for_concept(clean_q, df)
        if fb_spec is not None:
            status = resolve_concept(fb_spec.requested_metric, df).status
            missing_column = re.search(r"couldn't find|could not find|does not contain|doesn't contain|no .*column",
                                       str(resp.answer or ""), re.IGNORECASE)
            if status != "direct" or missing_column:
                col_names = list(df.columns)
                fb_spec.filters = [FilterSpec(**f) for f in _extract_filters(clean_q.lower(), col_names, df)]
                resp = LLMResponse(type="data_query", query=fb_spec, queries=[fb_spec])

    # 3d. Schema-aware metric resolution (direct / derived / ambiguous / not available)
    #     and year/date filter normalization. This layer overrides unsafe LLM column choices.
    if resp.type == "data_query" and resp.all_queries and df is not None:
        resp = apply_semantic_layer(resp, clean_q, df)
        if resp.type != "data_query":
            return resp

    # 4. Zero Hallucination & Column Validation Guard
    if resp.type == "data_query" and resp.all_queries and df is not None:
        valid_resp = _validate_columns_against_df(resp, df)
        return valid_resp

    return resp


def _filter_is_grounded(f: FilterSpec, question: str) -> bool:
    """True unless an equals/in filter's values appear nowhere in the question."""
    if str(f.operator).lower() not in ("=", "==", "equals", "eq", "is", "in", "is_in"):
        return True
    values = f.value if isinstance(f.value, (list, tuple)) else [f.value]
    q = question.lower()
    q_words = set(re.findall(r"[a-z0-9]+", q))
    for v in values:
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            if str(int(v) if float(v).is_integer() else v) in q:
                return True
            continue
        s = str(v).strip().lower()
        if not s:
            continue
        if s in q:
            return True
        words = re.findall(r"[a-z0-9]+", s)
        if any(len(w) >= 3 and w in q_words for w in words):
            return True
        if len(words) > 1 and "".join(w[0] for w in words) in q_words:
            return True  # "US" for "United States"
        if re.match(r"^\d{4}", s):
            return True  # dates / years are handled by the temporal layer
    return False


def _parse_llm_json(data: Dict[str, Any], raw_question: str) -> LLMResponse:
    """Parses model JSON output into a clean LLMResponse supporting single, multi-queries, and direct plans."""
    resp_type = data.get("type", "direct_answer")
    raw_queries = data.get("queries")
    raw_query = data.get("query")
    answer_text = data.get("answer")

    query_list = []
    if isinstance(raw_queries, list) and len(raw_queries) > 0:
        query_list = raw_queries
    elif isinstance(raw_query, dict):
        query_list = [raw_query]
    elif any(k in data for k in ("operation", "metric", "aggregation", "column", "filters")):
        # Model returned a flat/canonical query plan directly
        query_list = [data]
        resp_type = "data_query"

    if resp_type == "data_query" and query_list:
        parsed_specs: List[QuerySpec] = []
        for q_item in query_list:
            if not isinstance(q_item, dict):
                continue

            raw_op = str(q_item.get("operation") or "sum").lower().strip()
            raw_agg = str(q_item.get("aggregation") or "").lower().strip()
            if raw_op in ("aggregate", "") and raw_agg:
                op = raw_agg
            elif raw_op == "aggregate":
                op = "sum"
            elif raw_op in ("top", "bottom"):
                op = raw_agg or "sum"
            else:
                op = raw_op

            if op in ("avg", "mean"):
                op = "average"
            elif op in ("total", "summation"):
                op = "sum"

            col = q_item.get("column") or q_item.get("metric")
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
            group_by = [str(g).strip() for g in group_by if str(g).strip()]

            filters = []
            for f in q_item.get("filters") or []:
                if isinstance(f, dict) and "column" in f:
                    f_op = f.get("operator", "=")
                    if str(f_op).lower().strip() in ("==", "equals", "eq", "is"):
                        f_op = "equals"
                    filters.append(FilterSpec(
                        column=str(f["column"]).strip(),
                        operator=f_op,
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

            measure = q_item.get("measure", "count")
            val_dist = bool(q_item.get("value_distribution", op in ("multi_column_value_distribution", "value_distribution")))

            requested_metric = q_item.get("requested_metric")
            if requested_metric is not None and not isinstance(requested_metric, str):
                requested_metric = None

            parsed_specs.append(QuerySpec(
                operation=op,
                requested_metric=requested_metric,
                column=col,
                columns=cols,
                condition=cond_spec,
                group_by=group_by,
                filters=filters,
                sort=sort,
                limit=limit,
                measure=measure,
                value_distribution=val_dist,
                raw_question=raw_question
            ))

        if parsed_specs:
            return LLMResponse(
                type="data_query",
                query=parsed_specs[0],
                queries=parsed_specs,
                answer=None
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

    # 2b. Multi-Grade Subset Request e.g. "show A and B counts for each subject", "compare O and A+ across subjects"
    multi_subset_match = re.search(
        r"(?:show|compare|list|display|find|get)?\s*(?:only\s+)?([A-Za-z0-9\+\*\-]+)\s+and\s+([A-Za-z0-9\+\*\-]+)\s+(?:grade|score|status|value)?\s*(?:counts?|distribution)?\s*(?:in|for|across|of)?\s*(?:each|every|all)?\s*([a-zA-Z0-9_\s]*)",
        q_base or q
    )
    if multi_subset_match:
        v1 = multi_subset_match.group(1).strip().upper()
        v2 = multi_subset_match.group(2).strip().upper()
        if v1 not in NON_GRADE_QUANTIFIERS and v2 not in NON_GRADE_QUANTIFIERS:
            subj_cols = _detect_subject_columns(df, schema)
            if subj_cols:
                return {
                    "type": "data_query",
                    "queries": [
                        {
                            "operation": "multi_column_value_distribution",
                            "columns": subj_cols,
                            "condition": {
                                "operator": "in",
                                "value": [v1, v2]
                            },
                            "group_by": [],
                            "filters": [],
                            "sort": [],
                            "limit": None,
                            "measure": "count",
                            "value_distribution": True
                        }
                    ]
                }

    # 2c. Distinct-Value Distribution (Multi-Column or Single-Column)
    # e.g. "each grade count for each subjects", "grade distribution for each subject", "count every grade across subjects"
    is_dist_query = any(re.search(pat, q) for pat in DISTRIBUTION_PATTERNS)
    if is_dist_query:
        target_col = None
        for c in col_names:
            c_clean = c.lower().replace("_", " ")
            if c.lower() in q or c_clean in q:
                target_col = c
                break

        is_multi_subject = any(w in q for w in ("each subject", "all subjects", "every subject", "across subjects", "subjects", "subject-wise", "each code", "all codes", "across all subjects"))
        if target_col and not is_multi_subject:
            return {
                "type": "data_query",
                "queries": [
                    {
                        "operation": "value_distribution",
                        "column": target_col,
                        "columns": [target_col],
                        "condition": None,
                        "group_by": [],
                        "filters": [],
                        "sort": [],
                        "limit": None,
                        "measure": "count",
                        "value_distribution": True
                    }
                ]
            }
        else:
            subj_cols = _detect_subject_columns(df, schema)
            if subj_cols:
                return {
                    "type": "data_query",
                    "queries": [
                        {
                            "operation": "multi_column_value_distribution",
                            "columns": subj_cols,
                            "condition": None,
                            "group_by": [],
                            "filters": [],
                            "sort": [],
                            "limit": None,
                            "measure": "count",
                            "value_distribution": True
                        }
                    ]
                }

    # 3. Multi-Column CONDITIONAL_COUNT: "list the A grade count in each subject code", "how many O grades in each subject", "only B grade for each subject"
    cond_match = re.search(
        r"(?:list|show|count|get|find|give me|visualize|visualise|plot|display)?\s*(?:the\s+)?([A-Za-z0-9\+\*\-]+)\s+(?:grade|score|status|value)?\s*counts?\s+(?:in|for|across|of)\s+(?:each|every|all)\s+([a-zA-Z0-9_\s]+)",
        q_base or q
    )
    if not cond_match:
        cond_match = re.search(
            r"(?:how\s+many|count|number\s+of)\s+(?:students\s+with\s+|records\s+with\s+)?([A-Za-z0-9\+\*\-]+)\s+(?:grades?|scores?|marks?)\s+(?:in|for|across|of)\s+(?:each|every|all)\s+([a-zA-Z0-9_\s]+)",
            q_base or q
        )
    if not cond_match:
        cond_match = re.search(
            r"(?:only\s+)?([A-Za-z0-9\+\*\-]+)\s+grades?\s+(?:for|in|across)\s+(?:each|every|all)\s+([a-zA-Z0-9_\s]+)",
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

        if target_val not in NON_GRADE_QUANTIFIERS:
            matched_columns = []
            if df is not None:
                for col in df.columns:
                    unique_vals = [str(v).strip().upper() for v in df[col].dropna().unique()]
                    if target_val in unique_vals:
                        matched_columns.append(col)
                    elif any(kw in target_category_desc for kw in ("subject", "course", "exam", "grade", "test")) and any(c.isalpha() for c in str(col)):
                        if not pd.api.types.is_numeric_dtype(df[col]) and not any(k in str(col).lower() for k in ("id", "name", "date", "roll", "reg")):
                            matched_columns.append(col)
            if not matched_columns:
                matched_columns = _detect_subject_columns(df, schema)

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
                        "filters": _extract_filters(q, col_names, df),
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
                        "filters": _extract_filters(q, col_names, df),
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
                        "filters": _extract_filters(q, col_names, df),
                        "sort": [],
                        "limit": None
                    }
                ]
            }

    # 9b. Data Query: "profit for each country", "average sales per region"
    each_match = re.search(r"^(.*?)\b(?:for\s+each|for\s+every|per|across\s+each|across\s+all)\s+([a-z0-9_\s/&-]+?)(?:\s+(?:in|for|during)\b|[?.!]|$)", q_base or q)
    if each_match and df is not None:
        from .semantics import fuzzy_resolve_column
        dim_col = resolve(each_match.group(2)) or fuzzy_resolve_column(each_match.group(2), df)
        metric_col = None
        for c in col_names:
            if c != dim_col and (c.lower() in each_match.group(1) or c.lower().replace("_", " ") in each_match.group(1)):
                metric_col = c
                break
        if dim_col:
            each_op = "sum"
            if any(w in q for w in ("average", "avg", "mean")):
                each_op = "average"
            elif any(w in q for w in ("maximum", "max", "highest")):
                each_op = "max"
            elif any(w in q for w in ("minimum", "min", "lowest")):
                each_op = "min"
            elif not metric_col:
                each_op = "count"
            return {
                "type": "data_query",
                "queries": [
                    {
                        "operation": each_op,
                        "column": metric_col,
                        "group_by": [dim_col],
                        "filters": _extract_filters(q, col_names, df),
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

    filters = _extract_filters(q, col_names, df)
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


def _extract_filters(q: str, col_names: List[str], df: Optional[pd.DataFrame] = None) -> List[Dict[str, Any]]:
    """Extracts date and value filters from natural language in a schema-agnostic manner."""
    filters = []
    # 1. Year filter
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

    # 2. Check for explicit column mention: "for [the] [column] <col> <val>" or "<col> = <val>"
    # E.g. "for the country region Canada", "for country_region Canada", "where country_region = Canada"
    matched_explicit = False
    for c in col_names:
        c_clean = c.lower().replace("_", " ")
        pattern = rf"(?:for|in|where)?\s*(?:the\s+)?(?:column\s+|field\s+)?(?:{re.escape(c)}|{re.escape(c_clean)})\s*(?:is|=|equals|of)?\s*['\"]?([A-Za-z0-9_\s&-]+?)['\"]?(?:\s+in|\s+for|[?.!]|$)"
        m = re.search(pattern, q, re.IGNORECASE)
        if m:
            val = m.group(1).strip()
            # "profit for Canada" names the metric, not a filter value: skip values that start with a
            # preposition, and non-numeric values on numeric columns.
            if re.match(r"^(?:for|in|by|per|during|of|from|across|with|where|each|every|and)\b", val, re.IGNORECASE):
                continue
            if df is not None and c in df.columns and pd.api.types.is_numeric_dtype(df[c]) \
                    and pd.to_numeric(pd.Series([val]), errors="coerce").isna().all():
                continue
            if val and val.lower() not in ("sum", "total", "average", "avg", "profit", "sales", "revenue"):
                filters.append({
                    "column": c,
                    "operator": "equals",
                    "value": val
                })
                matched_explicit = True
                break

    # 3. Dynamic search across DataFrame columns for values like "for Canada", "in Germany", "only First Class"
    if not matched_explicit:
        # Case-insensitive: callers pass the lowercased question. Only values that actually occur
        # in a categorical column become filters, so ordinary words are ignored.
        cand_matches = re.findall(r"\b(?:for|in|only)\s+([a-zA-Z][a-zA-Z0-9\s&-]+?)(?=\s+in\b|\s+for\b|\s+and\b|\s+during\b|[?.!,]|$)", q, re.IGNORECASE)
        for cand_val in cand_matches:
            val_clean = re.sub(r"^the\s+", "", cand_val.strip(), flags=re.IGNORECASE)
            if not val_clean or val_clean.lower() in ("sales", "profit", "revenue", "2023", "2024", "2025", "total", "average", "count", "each"):
                continue

            matched_col, matched_val = None, None
            if df is not None:
                for c in col_names:
                    if c in df.columns:
                        series = df[c]
                        if not pd.api.types.is_numeric_dtype(series):
                            stripped = series.dropna().astype(str).str.strip()
                            hits = stripped[stripped.str.lower() == val_clean.lower()]
                            if len(hits):
                                matched_col, matched_val = c, hits.iloc[0]
                                break

            if matched_col and not any(f["column"] == matched_col for f in filters):
                filters.append({
                    "column": matched_col,
                    "operator": "equals",
                    "value": matched_val
                })

    return filters
