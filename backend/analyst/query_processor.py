"""
LLM Query Processor using local Ollama (qwen3:8b).
Translates user queries into structured LLMResponse containing either a data_query, direct_answer, or clarification.
"""

import logging
import re
from typing import Any, Dict, List, Optional
import pandas as pd

from llm import OllamaClient, SYSTEM_PROMPT, build_dataset_context, build_user_prompt
from .models import LLMResponse, QuerySpec, FilterSpec, SortSpec

logger = logging.getLogger(__name__)


def process_query_with_llm(
    question: str,
    schema: Optional[Dict[str, Any]] = None,
    profile: Optional[Dict[str, Any]] = None,
    df: Optional[pd.DataFrame] = None,
    dataset_id: Optional[str] = None
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

    # If no dataset uploaded
    if df is None and schema is None:
        return LLMResponse(
            type="direct_answer",
            answer="Please upload a CSV or Excel dataset first before asking data-analysis questions."
        )

    # 1. Build Dataset Context & User Prompt
    dataset_context = build_dataset_context(schema, profile, df, dataset_id)
    user_prompt = build_user_prompt(clean_q, dataset_context)

    # 2. Call Ollama Qwen3:8b
    client = OllamaClient()
    raw_data: Optional[Dict[str, Any]] = None

    if client.is_available():
        try:
            raw_data = client.generate_json(SYSTEM_PROMPT, user_prompt)
        except Exception as e:
            logger.warning(f"Ollama call failed ({e}), falling back to deterministic router.")
            raw_data = None

    if not raw_data:
        raw_data = _fallback_router(clean_q, df, schema)

    # 3. Parse LLM JSON into LLMResponse
    resp = _parse_llm_json(raw_data, clean_q)

    # 4. Zero Hallucination & Column Validation Guard
    if resp.type == "data_query" and resp.query and df is not None:
        valid_resp = _validate_columns_against_df(resp, df)
        return valid_resp

    return resp


def _parse_llm_json(data: Dict[str, Any], raw_question: str) -> LLMResponse:
    """Parses model JSON output into a clean LLMResponse."""
    resp_type = data.get("type", "direct_answer")
    query_dict = data.get("query")
    answer_text = data.get("answer")

    if resp_type == "data_query" and isinstance(query_dict, dict):
        op = query_dict.get("operation", "sum")
        col = query_dict.get("column")
        group_by = query_dict.get("group_by") or []
        if isinstance(group_by, str):
            group_by = [group_by]

        filters = []
        for f in query_dict.get("filters") or []:
            if isinstance(f, dict) and "column" in f:
                filters.append(FilterSpec(
                    column=f["column"],
                    operator=f.get("operator", "="),
                    value=f.get("value")
                ))

        sort = []
        for s in query_dict.get("sort") or []:
            if isinstance(s, dict) and "column" in s:
                sort.append(SortSpec(
                    column=s["column"],
                    direction=s.get("direction", "desc")
                ))

        limit = query_dict.get("limit")
        if limit is not None:
            try:
                limit = int(limit)
            except Exception:
                limit = None

        query_spec = QuerySpec(
            operation=op,
            column=col,
            group_by=group_by,
            filters=filters,
            sort=sort,
            limit=limit
        )
        return LLMResponse(
            type="data_query",
            query=query_spec,
            answer=None
        )

    if resp_type == "clarification":
        return LLMResponse(
            type="clarification",
            query=None,
            answer=answer_text or "Could you please clarify your question?"
        )

    return LLMResponse(
        type="direct_answer",
        query=None,
        answer=answer_text or "I am your AI Data Analyst assistant."
    )


def _validate_columns_against_df(resp: LLMResponse, df: pd.DataFrame) -> LLMResponse:
    """Zero hallucination guard: ensures all columns generated exist in DataFrame."""
    col_map = {c.lower(): c for c in df.columns}
    norm_col_map = {re.sub(r"[^a-z0-9]", "", c.lower()): c for c in df.columns}

    query = resp.query
    if not query:
        return resp

    # Validate target column
    if query.column:
        c_lower = query.column.lower()
        c_norm = re.sub(r"[^a-z0-9]", "", c_lower)
        if c_lower in col_map:
            query.column = col_map[c_lower]
        elif c_norm in norm_col_map:
            query.column = norm_col_map[c_norm]
        else:
            return LLMResponse(
                type="clarification",
                query=None,
                answer=f"I couldn't find a matching column for '{query.column}' in the current dataset."
            )

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
            else:
                return LLMResponse(
                    type="clarification",
                    query=None,
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
            else:
                return LLMResponse(
                    type="clarification",
                    query=None,
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

    # 1. Direct answer: Conversational
    greetings = {"hello", "hi", "hey", "good morning", "good afternoon", "thanks", "thank you", "who are you"}
    if q_clean in greetings or q_clean.startswith(("hello ", "hi ", "hey ")):
        return {
            "type": "direct_answer",
            "query": None,
            "answer": "Hello! I am your AI Data Analyst. How can I help you analyze your dataset today?"
        }

    if q_clean in ("what can you do", "help", "what are your capabilities"):
        return {
            "type": "direct_answer",
            "query": None,
            "answer": "I can help you analyze your dataset by calculating metrics (sum, average, count, min, max), listing distinct values, aggregating across categories, and applying filters."
        }

    # Direct answer: Conceptual explanations (e.g. "what is profit?", "what is a database?")
    if re.search(r"^what is (?:a |an )?(database|sql|profit|sales|revenue|data analysis)\??$", q):
        concept = re.search(r"^what is (?:a |an )?(database|sql|profit|sales|revenue|data analysis)\??$", q).group(1)
        return {
            "type": "direct_answer",
            "query": None,
            "answer": f"In business and data analysis, {concept} refers to financial gain representing the difference between amount earned and the amount spent in buying, operating, or producing something." if concept == "profit" else f"{concept.title()} is a fundamental data concept used in storing and analyzing business information."
        }

    # 2. Clarification: Missing operation on bare column e.g. "sales?", "country_region"
    bare_term = re.sub(r"[^\w\s]", "", q).strip()
    matched_bare = resolve(bare_term)
    if matched_bare and not any(w in q for w in ("total", "sum", "average", "avg", "mean", "count", "min", "max", "unique", "distinct", "by", "per", "top", "bottom", "in 20")):
        return {
            "type": "clarification",
            "query": None,
            "answer": f"What would you like to know about {matched_bare} — total, average, minimum, maximum, or something else?"
        }

    # Clarification: Ambiguous request e.g. "show locations"
    if "location" in q:
        loc_cols = [c for c in col_names if any(w in c.lower() for w in ("country", "region", "state", "city", "postal"))]
        if len(loc_cols) > 1:
            return {
                "type": "clarification",
                "query": None,
                "answer": f"Which location field would you like to use: {', '.join(loc_cols[:4])}?"
            }

    # 3. Data Query: COUNT_DISTINCT
    count_dist = re.search(r"\b(?:how many|count|number of)\s+(?:the\s+|all\s+)?(?:unique|distinct|different)\s+([a-zA-Z0-9_\s/&-]+?)(?:\s+(?:are there|in|for|where|with|do we have)\b|[?.!]|$)", q)
    if count_dist:
        raw_col = count_dist.group(1).strip()
        matched = resolve(raw_col) or (resolve("customer_id") if "customer" in raw_col else None) or (resolve("product_id") if "product" in raw_col else None)
        if matched:
            return {
                "type": "data_query",
                "query": {
                    "operation": "count_distinct",
                    "column": matched,
                    "group_by": [],
                    "filters": _extract_filters(q, col_names),
                    "sort": [],
                    "limit": None
                }
            }

    # 4. Data Query: DISTINCT
    dist_match = re.search(r"\b(?:list|show|display|what are|give me|find)\s+(?:the\s+|all\s+)?(?:unique|distinct|different)\s+([a-zA-Z0-9_\s/&-]+?)(?:\s+(?:in|for|where|with)\b|[?.!]|$)", q)
    if not dist_match and "unique" in q and not any(w in q for w in ("how many", "count", "number of")):
        dist_match = re.search(r"\b(?:unique|distinct)\s+([a-zA-Z0-9_\s/&-]+?)(?:\s+(?:in|for|where|with)\b|[?.!]|$)", q)

    if dist_match:
        raw_col = dist_match.group(1).strip()
        matched = resolve(raw_col)
        if matched:
            return {
                "type": "data_query",
                "query": {
                    "operation": "distinct",
                    "column": matched,
                    "group_by": [],
                    "filters": _extract_filters(q, col_names),
                    "sort": [],
                    "limit": None
                }
            }

    # 5. Data Query: Top N by Metric
    top_match = re.search(r"\btop\s+(\d+)\s+([a-zA-Z0-9_\s/&-]+?)\s+by\s+([a-zA-Z0-9_\s/&-]+)", q)
    if top_match:
        lim = int(top_match.group(1))
        dim_raw = top_match.group(2).strip()
        metric_raw = top_match.group(3).strip()
        dim_col = resolve(dim_raw) or (resolve("product_name") if "product" in dim_raw else None) or (resolve("category") if "categor" in dim_raw else None)
        metric_col = resolve(metric_raw)
        if dim_col and metric_col:
            return {
                "type": "data_query",
                "query": {
                    "operation": "sum",
                    "column": metric_col,
                    "group_by": [dim_col],
                    "filters": [],
                    "sort": [{"column": metric_col, "direction": "desc"}],
                    "limit": lim
                }
            }

    # 6. Data Query: Group By
    by_match = re.search(r"(?:show|list|get|display)?\s*([a-zA-Z0-9_\s/&-]+?)\s+by\s+([a-zA-Z0-9_\s/&-]+)", q)
    if by_match:
        metric_raw = by_match.group(1).strip()
        dim_raw = by_match.group(2).strip()
        metric_col = resolve(metric_raw) or (resolve("sales") if "sale" in metric_raw else None) or (resolve("profit") if "profit" in metric_raw else None)
        dim_col = resolve(dim_raw)
        if dim_col:
            op = "sum" if metric_col else "count"
            return {
                "type": "data_query",
                "query": {
                    "operation": op,
                    "column": metric_col,
                    "group_by": [dim_col],
                    "filters": _extract_filters(q, col_names),
                    "sort": [],
                    "limit": None
                }
            }

    # 7. Data Query: Standard Aggregations (sum, average, count, min, max)
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
            "query": {
                "operation": op,
                "column": target_col,
                "group_by": [],
                "filters": filters,
                "sort": [],
                "limit": None
            }
        }

    return {
        "type": "clarification",
        "query": None,
        "answer": "I couldn't find a matching column in the current dataset. Please specify which column you would like to analyze."
    }


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
