"""
Deterministic follow-up resolution for aggregate questions.

Given the previous QuerySpec, rewrites short follow-ups into a complete plan:

    "What about Canada?"          -> same metric/aggregation, filter country = Canada
    "What about Germany?"         -> replaces Canada (never keeps both)
    "Break that down by region"   -> keeps metric + filters, adds group_by
    "What is the average instead" -> keeps metric + filters + grouping, changes aggregation
    "What about 2023?"            -> replaces the temporal filter
    "What about revenue?"         -> keeps filters/grouping, changes the metric

Returns None when the question isn't a recognizable follow-up, so the LLM planner
(which also receives the previous plan) handles it instead.
"""

import re
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from .models import QuerySpec, FilterSpec, SortSpec, DerivedMetricSpec
from .semantics import (
    column_tokens, extract_years, fuzzy_resolve_column, match_concept_term, temporal_columns,
    _is_numeric_like,
)

AGGREGATE_OPS = {"sum", "average", "mean", "min", "max", "count", "count_distinct"}

_AGG_WORDS = {
    "average": "average", "avg": "average", "mean": "average",
    "total": "sum", "sum": "sum",
    "maximum": "max", "max": "max", "highest": "max",
    "minimum": "min", "min": "min", "lowest": "min",
    "count": "count",
}
_AGG_RE = r"(average|avg|mean|total|sum|maximum|max|highest|minimum|min|lowest|count)"
_LEAD = r"^(?:ok(?:ay)?[, ]+|and\s+|now\s+|then\s+|so\s+|also\s+|can you\s+|could you\s+|please\s+)*"

_BREAKDOWN_PATTERNS = [
    _LEAD + r"(?:break|split)\s+(?:this|that|it|these|those|them|the\s+results?)?\s*(?:down|up)?\s*(?:by|per|into|across)\s+(?P<dim>.+?)(?P<instead>\s+instead)?$",
    _LEAD + r"(?:group|show|display|see)\s+(?:this|that|it|these|those|them)\s+(?:by|per|for\s+each|across)\s+(?P<dim>.+?)(?P<instead>\s+instead)?$",
    _LEAD + r"(?:what\s+about|how\s+about)\s+(?:by|per|for\s+each|across)\s+(?P<dim>.+?)(?P<instead>\s+instead)?$",
    _LEAD + r"(?:by|per|for\s+each|for\s+every|across)\s+(?P<dim>.+?)(?P<instead>\s+instead)?$",
]
_AGG_PATTERNS = [
    _LEAD + r"(?:what\s+(?:is|was|'s)\s+|show\s+(?:me\s+)?|give\s+me\s+|use\s+|try\s+)?(?:the\s+)?" + _AGG_RE + r"(?:\s+value)?\s+instead$",
    _LEAD + r"(?:what|how)\s+about\s+(?:the\s+)?" + _AGG_RE + r"(?:\s+value)?$",
    _LEAD + r"(?:show|give|use)\s+(?:me\s+)?(?:the\s+)?" + _AGG_RE + r"$",
]
_VALUE_PATTERNS = [
    (_LEAD + r"(?:what|how)\s+about\s+(?:for\s+|in\s+)?(?P<val>.+?)(?:\s+instead)?$", "replace"),
    (_LEAD + r"(?:same|similarly|do\s+the\s+same|same\s+thing)\s+(?:for|in)\s+(?P<val>.+?)$", "replace"),
    (_LEAD + r"(?:for|in)\s+(?P<val>.+?)(?:\s+instead)?$", "replace"),
    (_LEAD + r"(?:only|just)\s+(?:for\s+|in\s+)?(?P<val>.+?)$", "narrow"),
]


def _clean(q: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[?!.]+$", "", q.strip().lower())).strip()


def _spec_from_dict(prev: Dict[str, Any], question: str) -> QuerySpec:
    filters = [FilterSpec(column=f["column"], operator=f.get("operator", "equals"), value=f.get("value"))
               for f in (prev.get("filters") or []) if isinstance(f, dict) and f.get("column")]
    sort = [SortSpec(column=s["column"], direction=s.get("direction", "desc"))
            for s in (prev.get("sort") or []) if isinstance(s, dict) and s.get("column")]
    derived = prev.get("derived_metric")
    return QuerySpec(
        operation=prev.get("operation") or "sum",
        column=prev.get("column"),
        columns=list(prev.get("columns") or []),
        group_by=list(prev.get("group_by") or []),
        filters=filters,
        sort=sort,
        limit=prev.get("limit"),
        requested_metric=prev.get("requested_metric"),
        derived_metric=DerivedMetricSpec(**derived) if isinstance(derived, dict) else None,
        metric_mapping=prev.get("metric_mapping"),
        file_id=prev.get("file_id"),
        raw_question=question,
    )


def _find_value_column(value: str, df: pd.DataFrame, prefer: List[str]) -> Optional[Tuple[str, Any]]:
    """Locates a categorical column containing `value` (case-insensitive exact match)."""
    target = value.strip().lower()
    if not target:
        return None
    ordered = prefer + [c for c in df.columns if c not in prefer]
    for col in ordered:
        if col not in df.columns:
            continue
        series = df[col]
        if pd.api.types.is_numeric_dtype(series) or pd.api.types.is_datetime64_any_dtype(series):
            continue
        uniques = series.dropna().astype(str).str.strip().unique()
        for u in uniques:
            if u.lower() == target:
                return col, u
    return None


def _resolve_values(term: str, df: pd.DataFrame, prefer: List[str]) -> Optional[Tuple[str, List[Any]]]:
    term = re.sub(r"^(?:the)\s+", "", term.strip())
    parts = [p.strip() for p in re.split(r"\s*,\s*|\s+and\s+|\s+or\s+", term) if p.strip()]
    if not parts:
        return None
    found = []
    for part in parts:
        hit = _find_value_column(part, df, prefer)
        if not hit:
            # "the West region" -> value "West" in column "region"
            words = part.split()
            for k in range(len(words) - 1, 0, -1):
                col = fuzzy_resolve_column(" ".join(words[k:]), df)
                if col:
                    hit = _find_value_column(" ".join(words[:k]), df, [col])
                    if hit and hit[0] == col:
                        break
                    hit = None
        if not hit:
            return None
        found.append(hit)
    cols = {c for c, _ in found}
    if len(cols) != 1:
        return None
    return found[0][0], [v for _, v in found]


def _year_filter(df: pd.DataFrame, years: List[int]) -> Optional[FilterSpec]:
    year_cols, date_cols = temporal_columns(df)
    if year_cols:
        col = year_cols[0]
        if len(years) == 1:
            return FilterSpec(column=col, operator="equals", value=years[0])
        return FilterSpec(column=col, operator="in", value=years)
    if date_cols:
        return FilterSpec(column=date_cols[0], operator="between",
                          value=[f"{min(years)}-01-01", f"{max(years)}-12-31"])
    return None


def resolve_analytical_follow_up(question: str, previous: Optional[Dict[str, Any]],
                                 df: Optional[pd.DataFrame]) -> Optional[QuerySpec]:
    if not previous or df is None:
        return None
    prev_op = str(previous.get("operation") or "").lower()
    if prev_op not in AGGREGATE_OPS:
        return None
    q = _clean(question)
    if not q or len(q.split()) > 12:
        return None

    # 1. Aggregation change: "what is the average instead"
    for pat in _AGG_PATTERNS:
        m = re.match(pat, q)
        if m:
            new_op = _AGG_WORDS[m.group(1)]
            derived = previous.get("derived_metric") or {}
            if derived.get("kind") == "count_distinct" or (prev_op == "count_distinct" and new_op != "count"):
                return None
            if new_op != "count" and not previous.get("column") and not derived:
                return None
            spec = _spec_from_dict(previous, question)
            spec.operation = new_op
            return spec

    # 2. Breakdown: "break this down by region"
    for pat in _BREAKDOWN_PATTERNS:
        m = re.match(pat, q)
        if m:
            col = fuzzy_resolve_column(m.group("dim"), df)
            if not col:
                return None
            spec = _spec_from_dict(previous, question)
            if m.group("instead"):
                spec.group_by = [col]
            elif col not in spec.group_by:
                spec.group_by = spec.group_by + [col]
            # A single-value filter on the new dimension would collapse the breakdown to one group.
            return spec

    # 3. Filter / metric swap: "what about Canada", "only First Class", "what about 2023"
    for pat, mode in _VALUE_PATTERNS:
        m = re.match(pat, q)
        if not m:
            continue
        term = m.group("val").strip()
        spec = _spec_from_dict(previous, question)
        year_cols, date_cols = temporal_columns(df)
        temporal = set(year_cols + date_cols)

        years = extract_years(term)
        rest = re.sub(r"\b(?:19|20)\d{2}\b", " ", term)
        rest = re.sub(r"\b(?:in|for|during|of|the\s+year|year|and|,)\b", " ", rest)
        rest = re.sub(r"\s+", " ", rest).strip(" ,")

        changed = False
        if years:
            yf = _year_filter(df, years)
            if yf is None:
                return None
            spec.filters = [f for f in spec.filters if f.column not in temporal] + [yf]
            changed = True

        if rest:
            prefer = [f.column for f in spec.filters if f.column not in temporal]
            hit = _resolve_values(rest, df, prefer)
            if hit:
                col, values = hit
                new_filter = FilterSpec(column=col, operator="equals", value=values[0]) if len(values) == 1 else \
                    FilterSpec(column=col, operator="in", value=values)
                spec.filters = [f for f in spec.filters if f.column != col] + [new_filter]
                # Drop grouping on the filtered dimension: "profit by country" -> "what about Canada".
                if len(values) == 1:
                    spec.group_by = [g for g in spec.group_by if g != col]
                changed = True
            elif mode == "replace" and not years:
                metric_col = _resolve_metric(rest, df)
                if metric_col is None:
                    return None
                spec.derived_metric = None
                spec.metric_mapping = None
                if metric_col == "__concept__":
                    spec.column = None
                    spec.requested_metric = rest
                else:
                    spec.column = metric_col
                    spec.requested_metric = None
                changed = True
            else:
                return None

        return spec if changed else None

    return None


def _resolve_metric(term: str, df: pd.DataFrame) -> Optional[str]:
    """Column for a metric follow-up ('what about sales?'); '__concept__' defers to the semantic layer."""
    col = fuzzy_resolve_column(term, df)
    if col and _is_numeric_like(df[col]) and "id" not in column_tokens(col):
        return col
    if match_concept_term(term):
        return "__concept__"
    return None
