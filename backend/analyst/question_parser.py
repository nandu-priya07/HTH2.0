"""
Dataset-Agnostic Question Parser module.
Translates natural-language user queries into structured QuerySpec representations
based dynamically on the active dataset schema without hardcoded domain assumptions.
"""

import re
from typing import Any, Dict, List, Optional, Tuple, Union

from .query_types import (
    QuerySpec,
    QueryStatus,
    QueryOperation,
    AggregationType,
    FilterSpec,
    SortSpec,
    TimeGranularity
)
from .schema_mapper import (
    normalize_schema,
    resolve_column,
    find_candidate_columns,
    ColumnMetadata,
    _tokenize,
    _singularize
)
from .query_validator import validate_query
from .query_planner import build_query_spec

# Conversational expressions
GREETINGS = {
    "hello", "hi", "hey", "greetings", "good morning", "good afternoon",
    "good evening", "thanks", "thank you", "bye", "goodbye", "help"
}

# Patterns for non-data questions
IRRELEVANT_PATTERNS = [
    r"\bcapital of\b",
    r"\bweather\b",
    r"\btell me a joke\b",
    r"\ba joke\b",
    r"\bwho is (?:the )?president\b",
    r"\bwho is (?:the )?prime minister\b",
    r"\bmeaning of life\b",
    r"\bwho won\b",
    r"\brecipe for\b",
    r"\bwrite a (?:poem|song|essay)\b",
    r"\bsing a song\b",
    r"\bhow are you\b"
]

DATA_OPERATION_KEYWORDS = {
    "show", "list", "view", "count", "average", "avg", "mean", "total", "sum",
    "min", "minimum", "max", "maximum", "median", "by", "per", "top", "bottom",
    "highest", "lowest", "filter", "where", "compare", "trend", "breakdown",
    "unique", "distinct", "different", "how", "many", "much"
}


def parse_query(
    question: str,
    schema: Optional[Union[Dict[str, Any], List[Any]]],
    profile: Optional[Dict[str, Any]] = None
) -> QuerySpec:
    """
    Parses a natural-language question against a dataset schema into a validated QuerySpec.
    """
    # -------------------------------------------------------------
    # 1. No Dataset Check
    # -------------------------------------------------------------
    if schema is None:
        return build_query_spec(
            operation="aggregation",
            status=QueryStatus.NO_DATASET,
            message="Please upload a dataset before asking data-analysis questions.",
            raw_question=question
        )

    schema_map = normalize_schema(schema, profile)
    if not schema_map:
        return build_query_spec(
            operation="aggregation",
            status=QueryStatus.NO_DATASET,
            message="Please upload a dataset before asking data-analysis questions.",
            raw_question=question
        )

    text = question.strip()
    clean_lower = text.lower()
    clean_no_punct = re.sub(r"[^\w\s]", "", clean_lower).strip()

    # -------------------------------------------------------------
    # 2. Conversational Queries
    # -------------------------------------------------------------
    if clean_no_punct in GREETINGS or clean_no_punct.startswith(("hello ", "hi ", "hey ")):
        return build_query_spec(
            operation="detail",
            status=QueryStatus.CONVERSATIONAL,
            message="Hello! I am your AI Data Analyst. Ask me a question about your uploaded dataset.",
            raw_question=question
        )

    # -------------------------------------------------------------
    # 3. Irrelevant Queries
    # -------------------------------------------------------------
    for pattern in IRRELEVANT_PATTERNS:
        if re.search(pattern, clean_lower):
            return build_query_spec(
                operation="detail",
                status=QueryStatus.IRRELEVANT,
                reason="IRRELEVANT_QUERY",
                message="This question is not related to the uploaded dataset.",
                raw_question=question
            )

    # Check if question completely lacks both column references and data operations
    matched_any_col = False
    tokens = set(_tokenize(clean_lower))
    sing_tokens = {_singularize(t) for t in tokens}
    for col_meta in schema_map.values():
        col_sing_tokens = {_singularize(t) for t in col_meta.tokens}
        if (
            col_meta.tokens.intersection(tokens)
            or col_sing_tokens.intersection(sing_tokens)
            or clean_no_punct in col_meta.normalized_name
            or _singularize(clean_no_punct) in col_meta.normalized_name
        ):
            matched_any_col = True
            break

    matched_op_kw = any(kw in tokens for kw in DATA_OPERATION_KEYWORDS)
    if not matched_any_col and not matched_op_kw and len(tokens) > 3:
        return build_query_spec(
            operation="detail",
            status=QueryStatus.IRRELEVANT,
            reason="IRRELEVANT_QUERY",
            message="This question is not related to the uploaded dataset.",
            raw_question=question
        )

    # -------------------------------------------------------------
    # 4. Extract Date Columns and Time Filters / Granularity
    # -------------------------------------------------------------
    date_cols = [c.name for c in schema_map.values() if c.semantic_type == "date" or "date" in c.dtype.lower()]
    extracted_time_filter, extracted_year = _extract_time_range(clean_lower, date_cols)
    time_granularity = _extract_time_granularity(clean_lower)
    time_dimension = date_cols[0] if date_cols else None

    # -------------------------------------------------------------
    # 5. Short / Incomplete Queries
    # -------------------------------------------------------------
    short_query_spec = _check_short_queries(
        clean_lower=clean_lower,
        clean_no_punct=clean_no_punct,
        schema_map=schema_map,
        extracted_year=extracted_year,
        raw_question=question
    )
    if short_query_spec:
        return short_query_spec

    # -------------------------------------------------------------
    # 5.5 Detect DISTINCT or COUNT_DISTINCT Queries
    # -------------------------------------------------------------
    distinct_res = _detect_distinct_or_count_distinct(
        clean_lower=clean_lower,
        schema_map=schema_map,
        raw_question=question
    )
    if isinstance(distinct_res, QuerySpec):
        return distinct_res
    elif distinct_res is not None:
        op, target_col, agg = distinct_res
        filters: List[FilterSpec] = []
        if extracted_time_filter and time_dimension:
            matched_date_col = _find_mentioned_date_col(clean_lower, date_cols)
            target_date_col = matched_date_col or time_dimension
            filters.append(FilterSpec(
                column=target_date_col,
                operator=extracted_time_filter["operator"],
                value=extracted_time_filter["value"]
            ))
        detected_filters = _detect_condition_filters(clean_lower, schema_map, profile)
        if isinstance(detected_filters, QuerySpec):
            return detected_filters
        filters.extend(detected_filters)
        boolean_filters = _detect_boolean_filters(clean_lower, schema_map)
        filters.extend(boolean_filters)

        sort_specs, limit_val = _extract_sort_and_limit(clean_lower, target_col)

        spec = build_query_spec(
            operation=op,
            column=target_col,
            metric=target_col if op == "count_distinct" else None,
            aggregation=agg,
            group_by=[],
            filters=filters,
            sort=sort_specs,
            limit=limit_val,
            status=QueryStatus.VALID,
            raw_question=question
        )
        is_valid, error = validate_query(spec, schema_map)
        if not is_valid and error:
            spec.status = QueryStatus.INVALID
            spec.error = error
        return spec

    # -------------------------------------------------------------
    # 6. Detect Operation & Aggregation
    # -------------------------------------------------------------
    operation, aggregation = _detect_operation_and_aggregation(clean_lower)

    # -------------------------------------------------------------
    # 7. Group By Detection
    # -------------------------------------------------------------
    group_by_cols, is_trend = _detect_group_by(
        clean_lower=clean_lower,
        schema_map=schema_map,
        date_cols=date_cols
    )

    # Check if ambiguity arose in group by
    if isinstance(group_by_cols, QuerySpec):
        return group_by_cols

    if is_trend:
        operation = "trend"
        if not time_granularity:
            time_granularity = "month"

    # If group by found and operation was default aggregation, promote to group_by
    if group_by_cols and operation != "trend":
        operation = "group_by"

    # -------------------------------------------------------------
    # 8. Detect Metric
    # -------------------------------------------------------------
    metric_col = _detect_metric(
        clean_lower=clean_lower,
        schema_map=schema_map,
        operation=operation or "aggregation",
        aggregation=aggregation,
        group_by_cols=group_by_cols if isinstance(group_by_cols, list) else []
    )

    if isinstance(metric_col, QuerySpec):
        return metric_col

    # If no operation detected and no grouping
    if operation is None and not group_by_cols:
        if metric_col:
            has_metric_intent = any(
                kw in clean_lower
                for kw in (
                    "total", "sum", "average", "avg", "mean", "min", "max", "median",
                    "amount", "revenue", "sales", "salary", "hours", "profit", "how much", "how many"
                )
            )
            if has_metric_intent:
                operation = "aggregation"
                aggregation = aggregation or "sum"
            else:
                return build_query_spec(
                    operation="aggregation",
                    status=QueryStatus.NEEDS_CLARIFICATION,
                    reason="MISSING_OPERATION",
                    detected_column=metric_col,
                    message=f"What would you like to know about {metric_col}?",
                    raw_question=question
                )
        else:
            mentioned_col = None
            for col_meta in schema_map.values():
                if col_meta.name.lower() in clean_lower or col_meta.normalized_name in clean_lower:
                    mentioned_col = col_meta.name
                    break
            if mentioned_col:
                return build_query_spec(
                    operation="aggregation",
                    status=QueryStatus.NEEDS_CLARIFICATION,
                    reason="MISSING_OPERATION",
                    detected_column=mentioned_col,
                    message=f"What would you like to know about {mentioned_col}?",
                    raw_question=question
                )
            return build_query_spec(
                operation="detail",
                status=QueryStatus.NEEDS_CLARIFICATION,
                reason="UNKNOWN_QUERY",
                message="Could you please specify what analysis or operation you would like to run?",
                raw_question=question
            )

    # Default aggregation for group_by
    if operation == "group_by":
        if not aggregation:
            aggregation = "sum" if metric_col else "count"
    elif operation == "aggregation" and not aggregation:
        aggregation = "sum"

    # -------------------------------------------------------------
    # 9. Extract Filters (explicit filters + boolean tags + date)
    # -------------------------------------------------------------
    filters: List[FilterSpec] = []
    if extracted_time_filter and time_dimension:
        matched_date_col = _find_mentioned_date_col(clean_lower, date_cols)
        target_date_col = matched_date_col or time_dimension
        filters.append(FilterSpec(
            column=target_date_col,
            operator=extracted_time_filter["operator"],
            value=extracted_time_filter["value"]
        ))

    # Condition filters like: salary > 50000, priority is high, category = Electronics
    detected_filters = _detect_condition_filters(clean_lower, schema_map, profile)
    if isinstance(detected_filters, QuerySpec):
        return detected_filters
    filters.extend(detected_filters)

    # Boolean flag filters e.g. "active employees", "resolved tickets"
    boolean_filters = _detect_boolean_filters(clean_lower, schema_map)
    filters.extend(boolean_filters)

    # -------------------------------------------------------------
    # 10. Extract Sorting and Limits
    # -------------------------------------------------------------
    sort_specs, limit_val = _extract_sort_and_limit(clean_lower, metric_col)

    # -------------------------------------------------------------
    # 11. Final Assembly & Validation
    # -------------------------------------------------------------
    spec = build_query_spec(
        operation=operation or "aggregation",
        metric=metric_col,
        aggregation=aggregation,
        group_by=group_by_cols if isinstance(group_by_cols, list) else [],
        filters=filters,
        sort=sort_specs,
        limit=limit_val,
        time_dimension=time_dimension if (operation == "trend" or extracted_time_filter) else None,
        time_granularity=time_granularity if operation == "trend" else None,
        status=QueryStatus.VALID,
        raw_question=question
    )

    is_valid, error = validate_query(spec, schema_map)
    if not is_valid and error:
        spec.status = QueryStatus.INVALID
        spec.error = error

    return spec


def parse_question(question: str, schema: Optional[Any] = None, *args, **kwargs) -> QuerySpec:
    """Backward compatibility alias for parse_query."""
    return parse_query(question=question, schema=schema)


# =====================================================================
# Internal Parsing Helpers
# =====================================================================

def _check_short_queries(
    clean_lower: str,
    clean_no_punct: str,
    schema_map: Dict[str, ColumnMetadata],
    extracted_year: Optional[int],
    raw_question: str
) -> Optional[QuerySpec]:
    """Handles short, ambiguous, or incomplete queries like 'sales?', 'sales 2024', 'sales by'."""
    tokens = clean_no_punct.split()

    # Case: "sales by" or "<column> by" (user didn't specify grouping dimension)
    by_incomplete = re.search(r"^([a-zA-Z0-9_\s]+?)\s+by\s*$", clean_no_punct)
    if by_incomplete:
        term = by_incomplete.group(1).strip()
        res = resolve_column(term, schema_map, is_metric=True)
        col_name = res.resolved or term
        return build_query_spec(
            operation="aggregation",
            status=QueryStatus.NEEDS_CLARIFICATION,
            reason="INCOMPLETE_QUERY",
            detected_column=col_name,
            message=f"Which dimension would you like to group {col_name} by?",
            raw_question=raw_question
        )

    # Case: Short query with year, e.g. "sales 2024" or "sales in 2024"
    if extracted_year and len(tokens) <= 3:
        metric_term = re.sub(r"\b(in|for|of|during)?\s*\d{4}\b", "", clean_no_punct).strip()
        if metric_term:
            res = resolve_column(metric_term, schema_map, is_metric=True)
            if res.is_ambiguous:
                return build_query_spec(
                    operation="aggregation",
                    status=QueryStatus.NEEDS_CLARIFICATION,
                    reason="AMBIGUOUS_COLUMN",
                    options=res.options,
                    message=f"I found multiple columns related to '{metric_term}'. Which one do you mean?",
                    raw_question=raw_question
                )
            if res.resolved:
                # If metric_term is a non-numeric column (e.g. "country_region 2024"), it needs clarification
                if schema_map[res.resolved].semantic_type != "numeric":
                    return build_query_spec(
                        operation="aggregation",
                        status=QueryStatus.NEEDS_CLARIFICATION,
                        reason="MISSING_OPERATION",
                        detected_column=res.resolved,
                        message=f"What would you like to know about {res.resolved} in {extracted_year}?",
                        raw_question=raw_question
                    )

    # Case: Single term or single term + question mark, e.g. "sales?" or "country_region"
    has_op = any(
        kw in clean_lower
        for kw in (
            "total", "sum", "average", "avg", "mean", "count", "how many", "number of",
            "min", "minimum", "max", "maximum", "median", "top", "bottom", "highest",
            "lowest", "by", "per", "where", "with", "greater", "less", "more than",
            "fewer than", "at least", "at most", "unique", "distinct", "different"
        )
    )
    if not has_op and (len(tokens) <= 2 or clean_lower.endswith("?")):
        target_term = re.sub(r"\b(show|view|get|list|display)\b", "", clean_no_punct).strip()
        if target_term:
            res = resolve_column(target_term, schema_map)
            if res.is_ambiguous:
                return build_query_spec(
                    operation="aggregation",
                    status=QueryStatus.NEEDS_CLARIFICATION,
                    reason="AMBIGUOUS_COLUMN",
                    options=res.options,
                    message=f"I found multiple columns related to '{target_term}'. Which one do you mean?",
                    raw_question=raw_question
                )
            if res.resolved:
                return build_query_spec(
                    status=QueryStatus.NEEDS_CLARIFICATION,
                    reason="MISSING_OPERATION",
                    detected_column=res.resolved,
                    message=f"What would you like to know about {res.resolved}?",
                    raw_question=raw_question
                )

    return None


def _detect_distinct_or_count_distinct(
    clean_lower: str,
    schema_map: Dict[str, ColumnMetadata],
    raw_question: str
) -> Optional[Union[QuerySpec, Tuple[str, str, Optional[str]]]]:
    """
    Detects if the query expresses a DISTINCT (list unique values) or COUNT_DISTINCT (count unique values) intent.
    Returns:
        - (operation, column_name, aggregation) where operation is 'distinct' or 'count_distinct'
        - Or QuerySpec (if column is ambiguous or needs clarification)
        - Or None (if not a distinct query)
    """
    # 1. First check for COUNT_DISTINCT patterns (e.g. "how many unique countries", "count unique country regions")
    count_distinct_regexes = [
        r"\b(?:how many|number of)\s+(?:unique|distinct|different)\s+([a-zA-Z0-9_\s/&-]+?)(?:\s+(?:are there|in|for|where|with|during|after|before)\b|[?.!]|$)",
        r"\b(?:count|count of)\s+(?:the\s+|all\s+)?(?:unique|distinct|different)\s+([a-zA-Z0-9_\s/&-]+?)(?:\s+(?:in|for|where|with|during|after|before)\b|[?.!]|$)",
        r"\b(?:how many|number of)\s+([a-zA-Z0-9_\s/&-]+?)\s+(?:are there\s+)?(?:uniquely|distinctly)(?:\s+(?:in|for|where|with)\b|[?.!]|$)"
    ]
    for pattern in count_distinct_regexes:
        m = re.search(pattern, clean_lower)
        if m:
            raw_col = m.group(1).strip()
            raw_col = re.sub(r"\b(are there|in|for|during|where|with)\b.*$", "", raw_col).strip()
            raw_col = re.sub(r"\b\d{4}\b", "", raw_col).strip()
            if raw_col:
                res = resolve_column(raw_col, schema_map)
                if res.is_ambiguous:
                    id_cands = [opt for opt in res.options if "_id" in opt.lower() or opt.lower().endswith("id")]
                    if id_cands:
                        return ("count_distinct", id_cands[0], "count_distinct")
                    return build_query_spec(
                        operation="count_distinct",
                        status=QueryStatus.NEEDS_CLARIFICATION,
                        reason="AMBIGUOUS_COLUMN",
                        options=res.options,
                        message=f"I found multiple columns related to '{raw_col}'. Which one do you mean?",
                        raw_question=raw_question
                    )
                if res.resolved:
                    return ("count_distinct", res.resolved, "count_distinct")

    # 2. Check for DISTINCT (list unique values) patterns
    distinct_regexes = [
        r"\b(?:list|show|display|get|give me|find|view|what are|tell me)\s+(?:the\s+|all\s+)?(?:unique|distinct|different)\s+([a-zA-Z0-9_\s/&-]+?)(?:\s+(?:in|for|where|with|during|after|before)\b|[?.!]|$)",
        r"\b(?:unique|distinct|different)\s+([a-zA-Z0-9_\s/&-]+?)(?:\s+(?:in|for|where|with|during|after|before)\b|[?.!]|$)",
        r"\b(?:list|show|display|get|view)\s+(?:all\s+)?(?:unique|distinct)\b\s*([a-zA-Z0-9_\s/&-]+?)(?:\s+(?:in|for|where|with)\b|[?.!]|$)"
    ]
    for pattern in distinct_regexes:
        m = re.search(pattern, clean_lower)
        if m:
            raw_col = m.group(1).strip()
            raw_col = re.sub(r"\b(in|for|during|where|with)\b.*$", "", raw_col).strip()
            raw_col = re.sub(r"\b\d{4}\b", "", raw_col).strip()
            if raw_col:
                res = resolve_column(raw_col, schema_map)
                if res.is_ambiguous:
                    name_cands = [opt for opt in res.options if "_name" in opt.lower() or opt.lower().endswith("name")]
                    if name_cands:
                        return ("distinct", name_cands[0], None)
                    return build_query_spec(
                        operation="distinct",
                        status=QueryStatus.NEEDS_CLARIFICATION,
                        reason="AMBIGUOUS_COLUMN",
                        options=res.options,
                        message=f"I found multiple columns related to '{raw_col}'. Which one do you mean?",
                        raw_question=raw_question
                    )
                if res.resolved:
                    return ("distinct", res.resolved, None)

    # General catch-all: If words "unique" or "distinct" are present in the query
    if re.search(r"\b(?:unique|distinct)\b", clean_lower):
        is_count = bool(re.search(r"\b(?:how many|number of|count)\b", clean_lower))
        words = [
            w for w in _tokenize(clean_lower)
            if w not in ("list", "the", "all", "show", "display", "what", "are", "unique", "distinct", "different", "how", "many", "count", "number", "of", "is", "in", "for", "during", "there")
        ]
        candidate_term = " ".join(words).strip()
        if candidate_term:
            res = resolve_column(candidate_term, schema_map)
            if res.is_ambiguous:
                id_cands = [opt for opt in res.options if "_id" in opt.lower() or opt.lower().endswith("id")]
                name_cands = [opt for opt in res.options if "_name" in opt.lower() or opt.lower().endswith("name")]
                if is_count and id_cands:
                    return ("count_distinct", id_cands[0], "count_distinct")
                elif not is_count and name_cands:
                    return ("distinct", name_cands[0], None)
                return build_query_spec(
                    operation="count_distinct" if is_count else "distinct",
                    status=QueryStatus.NEEDS_CLARIFICATION,
                    reason="AMBIGUOUS_COLUMN",
                    options=res.options,
                    message=f"I found multiple columns related to '{candidate_term}'. Which one do you mean?",
                    raw_question=raw_question
                )
            if res.resolved:
                if is_count:
                    return ("count_distinct", res.resolved, "count_distinct")
                return ("distinct", res.resolved, None)

    return None


def _detect_operation_and_aggregation(clean_lower: str) -> Tuple[Optional[str], Optional[str]]:
    """Detects high-level operation and aggregation function."""
    if re.search(r"\b(?:compare|comparison|versus|vs)\b", clean_lower):
        return "comparison", "sum"

    if re.search(r"\b(?:average|avg|mean)\b", clean_lower):
        return "aggregation", "mean"

    if re.search(r"\b(?:minimum|min|lowest|smallest|least)\b", clean_lower):
        return "aggregation", "min"

    if re.search(r"\b(?:maximum|max|highest|largest|greatest|peak)\b", clean_lower):
        return "aggregation", "max"

    if re.search(r"\b(?:median|middle)\b", clean_lower):
        return "aggregation", "median"

    if re.search(r"\b(?:how many|number of|count of|count)\b", clean_lower):
        return "count", "count"

    if re.search(r"\b(?:total|sum of|sum|overall|how much did we sell|how much)\b", clean_lower):
        return "aggregation", "sum"

    if re.search(r"\b(?:where|with|greater than|less than|more than|fewer than|at least|at most)\b", clean_lower):
        return "filter", None

    if re.search(r"\b(?:show|list|view|display)\b", clean_lower) and not re.search(r"\bby\b", clean_lower):
        return "detail", None

    return None, None


def _detect_group_by(
    clean_lower: str,
    schema_map: Dict[str, ColumnMetadata],
    date_cols: List[str]
) -> Tuple[Union[List[str], QuerySpec], bool]:
    """Extracts group by dimensions or flags time trend."""
    # Pattern: top/bottom N <dim> by <metric>
    # e.g. "top 5 regions by sales amount", "10 highest products by revenue"
    top_dim_match = re.search(
        r"\b(?:top|bottom|lowest|highest|first)\s+(?:\d+\s+)?([a-zA-Z0-9_\s/&-]+?)\s+by\s+([a-zA-Z0-9_\s/&-]+?)(?:\s+(?:where|with|in|for|after|before)\b|[?.!]|$)",
        clean_lower
    )
    if top_dim_match:
        raw_dim = top_dim_match.group(1).strip()
        res = resolve_column(raw_dim, schema_map, is_group_by=True)
        if res.resolved:
            return [res.resolved], False
        if res.is_ambiguous:
            return build_query_spec(
                operation="group_by",
                status=QueryStatus.NEEDS_CLARIFICATION,
                reason="AMBIGUOUS_COLUMN",
                options=res.options,
                message=f"I found multiple columns related to '{raw_dim}'. Which one do you mean?",
                raw_question=clean_lower
            ), False

    pattern = r"\b(?:by|per|across|for each|breakdown by|grouped by)\s+([a-zA-Z0-9_\s/&-]+?)(?:\s+(?:where|with|in|for|having|order by|sorted by|limit|top|after|before)\b|[?.!]|$|\s+in\s+\d{4})"
    match = re.search(pattern, clean_lower)
    if not match:
        return [], False

    raw_dim = match.group(1).strip()
    dim_tokens = raw_dim.split()
    if not dim_tokens:
        return [], False

    # Check for time granularity words
    if any(t in {"month", "year", "day", "week", "quarter", "date", "time"} for t in dim_tokens):
        return [], True

    # Resolve column
    res = resolve_column(raw_dim, schema_map, is_group_by=True)
    if res.is_ambiguous:
        return build_query_spec(
            operation="group_by",
            status=QueryStatus.NEEDS_CLARIFICATION,
            reason="AMBIGUOUS_COLUMN",
            options=res.options,
            message=f"I found multiple columns related to '{raw_dim}'. Which one do you mean?",
            raw_question=clean_lower
        ), False

    if res.resolved:
        return [res.resolved], False

    # Try matching first word or token of dimension
    for t in dim_tokens:
        sub_res = resolve_column(t, schema_map, is_group_by=True)
        if sub_res.resolved:
            return [sub_res.resolved], False

    return [], False


def _detect_metric(
    clean_lower: str,
    schema_map: Dict[str, ColumnMetadata],
    operation: str,
    aggregation: Optional[str],
    group_by_cols: List[str]
) -> Union[Optional[str], QuerySpec]:
    """Detects metric column from question text."""
    # If filter or detail without aggregation, metric is not required
    if operation in ("filter", "detail") and aggregation is None:
        return None

    # Check if question has "by <metric>" in top N pattern, e.g. "top 5 products by sales"
    top_match = re.search(
        r"\b(?:top|bottom|lowest|highest)\s+(?:\d+\s+)?(?:[a-zA-Z0-9_\s/&-]+?)\s+by\s+([a-zA-Z0-9_\s/&-]+?)(?:\s+(?:where|with|in|for|after|before)\b|[?.!]|$)",
        clean_lower
    )
    if top_match:
        cand_metric = top_match.group(1).strip()
        res_m = resolve_column(cand_metric, schema_map, is_metric=True)
        if res_m.resolved and schema_map[res_m.resolved].semantic_type == "numeric":
            return res_m.resolved

    # If operation is count without specific metric requested
    if operation == "count" and aggregation == "count":
        for c in schema_map.values():
            if c.semantic_type == "identifier" and c.name.lower() in clean_lower:
                return c.name
        return None

    numeric_cols = [c for c in schema_map.values() if c.semantic_type == "numeric" or any(n in c.dtype for n in ("int", "float"))]

    question_tokens = _tokenize(clean_lower)

    clause_stop_words = {
        "show", "what", "is", "the", "by", "per", "in", "of", "how", "many",
        "there", "are", "we", "did", "to", "for", "with", "where", "top", "bottom"
    }
    # 1. Check multi-word phrases first (e.g. "sales amount", "resolution hours", "total sales")
    for i in range(len(question_tokens)):
        for j in range(i + 2, min(i + 4, len(question_tokens) + 1)):
            sub_tokens = question_tokens[i:j]
            if any(t in clause_stop_words for t in sub_tokens):
                continue
            phrase = " ".join(sub_tokens)
            res = resolve_column(phrase, schema_map, is_metric=True)
            if res.is_ambiguous:
                return build_query_spec(
                    operation=operation,
                    status=QueryStatus.NEEDS_CLARIFICATION,
                    reason="AMBIGUOUS_COLUMN",
                    options=res.options,
                    message=f"I found multiple columns related to '{phrase}'. Which one do you mean?",
                    raw_question=clean_lower
                )
            if res.resolved and res.resolved not in group_by_cols and schema_map[res.resolved].semantic_type == "numeric":
                return res.resolved

    # 2. Check individual tokens and singularized tokens
    stop_words = {
        "show", "what", "is", "the", "total", "sum", "average", "avg", "mean",
        "min", "max", "count", "by", "per", "in", "of", "how", "many", "there",
        "are", "we", "did", "to", "for", "with", "where", "top", "bottom", "highest", "lowest"
    }
    for token in question_tokens:
        if token in stop_words or len(token) <= 2:
            continue
        res = resolve_column(token, schema_map, is_metric=True)
        if res.is_ambiguous:
            return build_query_spec(
                operation=operation,
                status=QueryStatus.NEEDS_CLARIFICATION,
                reason="AMBIGUOUS_COLUMN",
                options=res.options,
                message=f"I found multiple columns related to '{token}'. Which one do you mean?",
                raw_question=clean_lower
            )
        if res.resolved and res.resolved not in group_by_cols and schema_map[res.resolved].semantic_type == "numeric":
            return res.resolved

        # Check singularized token
        sing_token = _singularize(token)
        if sing_token != token and sing_token not in stop_words:
            res_sing = resolve_column(sing_token, schema_map, is_metric=True)
            if res_sing.is_ambiguous:
                return build_query_spec(
                    operation=operation,
                    status=QueryStatus.NEEDS_CLARIFICATION,
                    reason="AMBIGUOUS_COLUMN",
                    options=res_sing.options,
                    message=f"I found multiple columns related to '{token}'. Which one do you mean?",
                    raw_question=clean_lower
                )
            if res_sing.resolved and res_sing.resolved not in group_by_cols and schema_map[res_sing.resolved].semantic_type == "numeric":
                return res_sing.resolved

    # 3. Only default to single numeric column if query contains metric or aggregation intent
    has_metric_intent = any(
        kw in clean_lower
        for kw in (
            "total", "sum", "average", "avg", "mean", "min", "max", "median",
            "amount", "revenue", "sales", "salary", "hours", "price", "rate", "cost", "fee", "income"
        )
    )
    if len(numeric_cols) == 1 and has_metric_intent:
        return numeric_cols[0].name

    return None


def _detect_entity_column(
    clean_lower: str,
    schema_map: Dict[str, ColumnMetadata]
) -> Union[Optional[str], QuerySpec]:
    """Detects entity column for count distinct queries."""
    for col_name, col in schema_map.items():
        for token in col.tokens:
            if token in clean_lower and len(token) > 2:
                res = resolve_column(token, schema_map, is_group_by=True)
                if res.is_ambiguous:
                    return build_query_spec(
                        operation="count",
                        status=QueryStatus.NEEDS_CLARIFICATION,
                        reason="AMBIGUOUS_COLUMN",
                        options=res.options,
                        message=f"I found multiple columns related to '{token}'. Which one do you mean?",
                        raw_question=clean_lower
                    )
                if res.resolved:
                    return res.resolved
    return None


def _extract_time_range(clean_lower: str, date_cols: List[str]) -> Tuple[Optional[Dict[str, Any]], Optional[int]]:
    """Extracts year, month, or range constraints from query text."""
    # Pattern: "in 2024", "for 2024", "of 2024", "2024"
    year_match = re.search(r"\b(after|before|since|in|for|of|during)?\s*(19\d\d|20\d\d)\b", clean_lower)
    if year_match:
        prep = year_match.group(1) or "in"
        year = int(year_match.group(2))

        if prep in ("after", "since"):
            op = ">" if prep == "after" else ">="
            return {"operator": op, "value": f"{year}-12-31" if prep == "after" else f"{year}-01-01"}, year
        elif prep == "before":
            return {"operator": "<", "value": f"{year}-01-01"}, year
        else:
            return {"operator": "between", "value": [f"{year}-01-01", f"{year}-12-31"]}, year

    # Month + Year pattern, e.g. "after January 2026", "since March 2025"
    months = {
        "january": "01", "february": "02", "march": "03", "april": "04",
        "may": "05", "june": "06", "july": "07", "august": "08",
        "september": "09", "october": "10", "november": "11", "december": "12"
    }
    month_match = re.search(
        r"\b(after|before|since|in)?\s*(january|february|march|april|may|june|july|august|september|october|november|december)\s*(\d{4})?\b",
        clean_lower
    )
    if month_match:
        prep = month_match.group(1) or "in"
        m_name = month_match.group(2)
        m_num = months[m_name]
        year_str = month_match.group(3) or "2026"
        year = int(year_str)

        if prep in ("after", "since"):
            op = ">" if prep == "after" else ">="
            # End of month or start of month
            return {"operator": op, "value": f"{year_str}-{m_num}-31"}, year
        elif prep == "before":
            return {"operator": "<", "value": f"{year_str}-{m_num}-01"}, year
        else:
            return {"operator": "between", "value": [f"{year_str}-{m_num}-01", f"{year_str}-{m_num}-28"]}, year

    return None, None


def _extract_time_granularity(clean_lower: str) -> Optional[str]:
    """Extracts day, week, month, quarter, year."""
    if re.search(r"\b(?:monthly|by month|per month)\b", clean_lower):
        return TimeGranularity.MONTH.value
    if re.search(r"\b(?:yearly|annually|annual|by year|per year)\b", clean_lower):
        return TimeGranularity.YEAR.value
    if re.search(r"\b(?:quarterly|by quarter|per quarter)\b", clean_lower):
        return TimeGranularity.QUARTER.value
    if re.search(r"\b(?:weekly|by week|per week)\b", clean_lower):
        return TimeGranularity.WEEK.value
    if re.search(r"\b(?:daily|by day|per day)\b", clean_lower):
        return TimeGranularity.DAY.value
    return None


def _find_mentioned_date_col(clean_lower: str, date_cols: List[str]) -> Optional[str]:
    for col in date_cols:
        col_norm = re.sub(r"[-_.]+", " ", col.lower())
        if col_norm in clean_lower or col.lower() in clean_lower:
            return col
    return None


def _detect_condition_filters(
    clean_lower: str,
    schema_map: Dict[str, ColumnMetadata],
    profile: Optional[Dict[str, Any]]
) -> Union[List[FilterSpec], QuerySpec]:
    """Detects relational, equality, or substring filters."""
    filters: List[FilterSpec] = []

    # 1. Look for explicit where / with conditions
    cond_patterns = [
        # where col > 1000 or with col >= 18
        r"\b(?:where|with)\s+([a-zA-Z0-9_\s]+?)\s*(=|!=|>=|<=|>|<|contains|is|equals?)\s*([a-zA-Z0-9_.\-'\"]+)",
        # col greater than 1000
        r"([a-zA-Z0-9_\s]+?)\s+(greater than or equal to|at least|more than or equal to)\s+([0-9.]+)",
        r"([a-zA-Z0-9_\s]+?)\s+(greater than|more than|higher than|above)\s+([0-9.]+)",
        r"([a-zA-Z0-9_\s]+?)\s+(less than or equal to|at most|fewer than or equal to)\s+([0-9.]+)",
        r"([a-zA-Z0-9_\s]+?)\s+(less than|fewer than|lower than|below)\s+([0-9.]+)",
        r"([a-zA-Z0-9_\s]+?)\s+(equals|is)\s+([a-zA-Z0-9_.\-'\"]+)"
    ]

    for pat in cond_patterns:
        matches = re.finditer(pat, clean_lower)
        for m in matches:
            raw_col = m.group(1).strip()
            raw_op = m.group(2).strip()
            raw_val = m.group(3).strip().strip("'\"")

            # Ignore common prepositions or non-column words
            if raw_col in ("employees", "tickets", "products", "customers", "there", "we", "the"):
                continue

            res = resolve_column(raw_col, schema_map)
            if res.is_ambiguous:
                return build_query_spec(
                    operation="filter",
                    status=QueryStatus.NEEDS_CLARIFICATION,
                    reason="AMBIGUOUS_COLUMN",
                    options=res.options,
                    message=f"I found multiple columns related to '{raw_col}'. Which one do you mean?",
                    raw_question=clean_lower
                )
            if not res.resolved:
                continue

            # Standardize operator
            op = "="
            if raw_op in (">", "greater than", "more than", "higher than", "above"):
                op = ">"
            elif raw_op in (">=", "greater than or equal to", "at least", "more than or equal to"):
                op = ">="
            elif raw_op in ("<", "less than", "fewer than", "lower than", "below"):
                op = "<"
            elif raw_op in ("<=", "less than or equal to", "at most", "fewer than or equal to"):
                op = "<="
            elif raw_op in ("!=", "is not", "not equal"):
                op = "!="
            elif raw_op in ("contains", "has"):
                op = "contains"

            # Parse value
            try:
                if "." in raw_val:
                    parsed_val = float(raw_val)
                else:
                    parsed_val = int(raw_val)
            except ValueError:
                if raw_val.lower() == "true":
                    parsed_val = True
                elif raw_val.lower() == "false":
                    parsed_val = False
                else:
                    parsed_val = raw_val

            filters.append(FilterSpec(column=res.resolved, operator=op, value=parsed_val))

    # 2. Look for "in <category>" or "in <region>" value matches from profile or column values
    in_match = re.search(r"\bin\s+(?:the\s+)?([a-zA-Z0-9_\s]+?)(?:\s+(?:region|department|category|area|status)\b|[?.!]|$)", clean_lower)
    if in_match:
        cand_val = in_match.group(1).strip()
        if cand_val not in ("month", "year", "2024", "2025", "2026", "data", "dataset", "table"):
            # Try to match cand_val against known categorical columns in profile or column names
            for col_name, meta in schema_map.items():
                if meta.sample_values and any(cand_val.lower() == v.lower() for v in meta.sample_values):
                    filters.append(FilterSpec(column=col_name, operator="=", value=cand_val))
                    break

    return filters


def _detect_boolean_filters(clean_lower: str, schema_map: Dict[str, ColumnMetadata]) -> List[FilterSpec]:
    """Detects boolean flag columns mentioned as adjectives e.g. 'active employees', 'resolved tickets'."""
    filters = []
    bool_cols = [c for c in schema_map.values() if c.semantic_type == "boolean" or "bool" in c.dtype.lower()]
    for b_col in bool_cols:
        col_norm = b_col.normalized_name
        if col_norm in clean_lower or b_col.name.lower() in clean_lower:
            filters.append(FilterSpec(column=b_col.name, operator="=", value=True))
    return filters


def _extract_sort_and_limit(clean_lower: str, metric_col: Optional[str]) -> Tuple[List[SortSpec], Optional[int]]:
    """Extracts top N, bottom N, highest N, lowest N limits and sort directions."""
    # Top N
    top_match = re.search(r"\btop\s+(\d+)\b", clean_lower)
    if top_match:
        lim = int(top_match.group(1))
        return [SortSpec(column=metric_col or "value", direction="desc")], lim

    # N highest / largest / biggest
    highest_match = re.search(r"\b(\d+)\s+(?:highest|largest|top|biggest)\b", clean_lower)
    if highest_match:
        lim = int(highest_match.group(1))
        return [SortSpec(column=metric_col or "value", direction="desc")], lim

    # Bottom N / lowest N
    bottom_match = re.search(r"\b(?:bottom|lowest|smallest)\s+(\d+)\b", clean_lower)
    if bottom_match:
        lim = int(bottom_match.group(1))
        return [SortSpec(column=metric_col or "value", direction="asc")], lim

    # N lowest
    lowest_match = re.search(r"\b(\d+)\s+(?:lowest|smallest|bottom)\b", clean_lower)
    if lowest_match:
        lim = int(lowest_match.group(1))
        return [SortSpec(column=metric_col or "value", direction="asc")], lim

    return [], None
