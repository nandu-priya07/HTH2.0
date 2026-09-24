"""
Query Planner module.
Constructs structured QuerySpec objects representing dataset-agnostic query plans.
"""

from typing import Any, Dict, List, Optional, Union
from .query_types import (
    QuerySpec,
    QueryStatus,
    QueryOperation,
    AggregationType,
    FilterSpec,
    SortSpec
)

SUPPORTED_OPERATIONS = {
    "aggregation",
    "group_by",
    "filter",
    "comparison",
    "trend",
    "count",
    "distinct",
    "count_distinct",
    "detail",
    # Legacy operation aliases
    "sum",
    "average",
    "mean",
    "min",
    "max",
    "median"
}

SUPPORTED_AGGREGATIONS = {
    "sum",
    "average",
    "mean",
    "min",
    "max",
    "count",
    "count_distinct",
    "median"
}


def build_query_spec(
    operation: str,
    column: Optional[str] = None,
    metric: Optional[str] = None,
    aggregation: Optional[str] = None,
    group_by: Optional[List[str]] = None,
    filters: Optional[List[Union[FilterSpec, Dict[str, Any]]]] = None,
    sort: Optional[Union[List[Union[SortSpec, Dict[str, Any]]], str, Dict[str, Any]]] = None,
    limit: Optional[int] = None,
    time_dimension: Optional[str] = None,
    time_granularity: Optional[str] = None,
    time_range: Optional[Dict[str, Any]] = None,
    status: Union[QueryStatus, str] = QueryStatus.VALID,
    reason: Optional[str] = None,
    detected_column: Optional[str] = None,
    options: Optional[List[str]] = None,
    message: Optional[str] = None,
    error: Optional[Any] = None,
    confidence: Optional[float] = None,
    raw_question: Optional[str] = None
) -> QuerySpec:
    """Builds a standardized QuerySpec instance."""
    op_clean = operation.lower().strip() if operation else "aggregation"

    # Normalize sort if passed as a string or single dict
    sort_list: List[Union[SortSpec, Dict[str, Any]]] = []
    if isinstance(sort, str):
        sort_list = [SortSpec(column=column or metric or "value", direction=sort.lower())]
    elif isinstance(sort, dict):
        sort_list = [sort]
    elif isinstance(sort, list):
        sort_list = sort

    # Normalize group_by
    group_list: List[str] = []
    if isinstance(group_by, str):
        group_list = [group_by]
    elif isinstance(group_by, list):
        group_list = group_by

    return QuerySpec(
        status=status,
        operation=op_clean,
        column=column,
        metric=metric,
        aggregation=aggregation,
        group_by=group_list,
        filters=filters or [],
        sort=sort_list,
        limit=limit,
        time_dimension=time_dimension,
        time_granularity=time_granularity,
        time_range=time_range,
        reason=reason,
        detected_column=detected_column,
        options=options,
        message=message,
        error=error,
        confidence=confidence,
        raw_question=raw_question
    )


def create_query_plan(
    operation: str,
    column: Optional[str] = None,
    metric: Optional[str] = None,
    group_by: Optional[Union[str, List[str]]] = None,
    filters: Optional[List[Dict[str, Any]]] = None,
    sort: Optional[Union[str, List[Dict[str, Any]]]] = None,
    limit: Optional[int] = None,
    aggregation: Optional[str] = None,
    time_dimension: Optional[str] = None,
    time_granularity: Optional[str] = None
) -> QuerySpec:
    """
    Backward-compatible factory that returns a QuerySpec (which supports dict-like access).
    """
    op = operation.lower().strip() if operation else "aggregation"

    # Map legacy direct operation names to operation + aggregation if needed
    agg = aggregation
    if op in ("sum", "average", "mean", "min", "max", "count_distinct", "median"):
        agg = op if agg is None else agg
        op = "group_by" if group_by else "aggregation"
    elif op == "count":
        agg = "count"
        op = "group_by" if group_by else "count"

    return build_query_spec(
        operation=op,
        column=column,
        metric=metric,
        aggregation=agg,
        group_by=[group_by] if isinstance(group_by, str) else group_by,
        filters=filters,
        sort=sort,
        limit=limit,
        time_dimension=time_dimension,
        time_granularity=time_granularity
    )
