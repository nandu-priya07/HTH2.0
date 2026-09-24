"""
Query Validator module.
Validates QuerySpec against the active dataset schema and data types.
Rejects incompatible operations and produces structured errors.
"""

from typing import Any, Dict, List, Optional, Tuple, Union
from .query_types import (
    QuerySpec,
    QueryStatus,
    QueryErrorDetails,
    FilterOperator,
    TimeGranularity
)
from .query_errors import ErrorCode
from .schema_mapper import normalize_schema, ColumnMetadata

ALLOWED_OPERATORS = {op.value for op in FilterOperator}
ALLOWED_TIME_GRANULARITIES = {tg.value for tg in TimeGranularity}
NUMERIC_AGGREGATIONS = {"sum", "average", "mean", "median"}
NUMERIC_DTYPES = {"int64", "float64", "int32", "float32", "int", "float", "number"}


def validate_query(
    query_spec: QuerySpec,
    schema: Optional[Union[Dict[str, Any], List[Any]]] = None
) -> Tuple[bool, Optional[QueryErrorDetails]]:
    """
    Validates a QuerySpec against a normalized schema.
    Returns (is_valid, error_details).
    """
    if query_spec.status == QueryStatus.NO_DATASET:
        return False, QueryErrorDetails(
            code=ErrorCode.NO_DATASET,
            message=query_spec.message or "No active dataset uploaded."
        )

    if query_spec.status in (QueryStatus.NEEDS_CLARIFICATION, QueryStatus.IRRELEVANT, QueryStatus.CONVERSATIONAL):
        return True, None

    schema_map = normalize_schema(schema)

    # 1. Validate Target Column for Distinct / Count_Distinct Operations
    if query_spec.operation in ("distinct", "count_distinct"):
        target_col = query_spec.column or query_spec.metric
        if not target_col:
            return False, QueryErrorDetails(
                code=ErrorCode.COLUMN_NOT_FOUND,
                message=f"Operation '{query_spec.operation}' requires a target column."
            )
        col_meta = _find_column_in_schema(target_col, schema_map)
        if not col_meta:
            return False, QueryErrorDetails(
                code=ErrorCode.COLUMN_NOT_FOUND,
                message=f"Column '{target_col}' was not found in the dataset schema."
            )
        # Distinct operations do not require numeric validation

    # 2. Validate Metric (for aggregations/groupings)
    elif query_spec.metric is not None:
        col_meta = _find_column_in_schema(query_spec.metric, schema_map)
        if not col_meta:
            return False, QueryErrorDetails(
                code=ErrorCode.COLUMN_NOT_FOUND,
                message=f"Metric column '{query_spec.metric}' was not found in the dataset schema."
            )

        # Check aggregation type compatibility
        agg = (query_spec.aggregation or "").lower().strip()
        if agg in NUMERIC_AGGREGATIONS:
            is_numeric = (
                col_meta.semantic_type == "numeric"
                or any(t in col_meta.dtype.lower() for t in NUMERIC_DTYPES)
            )
            if not is_numeric:
                return False, QueryErrorDetails(
                    code=ErrorCode.INVALID_AGGREGATION,
                    message=(
                        f"Cannot perform numeric aggregation '{agg}' on column '{col_meta.name}' "
                        f"of semantic type '{col_meta.semantic_type}' (dtype: {col_meta.dtype})."
                    )
                )

    # 2. Validate Group By Columns
    for col_name in query_spec.group_by:
        col_meta = _find_column_in_schema(col_name, schema_map)
        if not col_meta:
            return False, QueryErrorDetails(
                code=ErrorCode.COLUMN_NOT_FOUND,
                message=f"Group-by column '{col_name}' was not found in the dataset schema."
            )

    # 3. Validate Filters
    for filter_item in query_spec.filters:
        if isinstance(filter_item, dict):
            f_col = filter_item.get("column")
            f_op = filter_item.get("operator")
            f_val = filter_item.get("value")
        else:
            f_col = filter_item.column
            f_op = filter_item.operator
            f_val = filter_item.value

        if not f_col:
            return False, QueryErrorDetails(
                code=ErrorCode.INVALID_FILTER,
                message="Filter is missing target column."
            )

        col_meta = _find_column_in_schema(f_col, schema_map)
        if not col_meta:
            return False, QueryErrorDetails(
                code=ErrorCode.COLUMN_NOT_FOUND,
                message=f"Filter column '{f_col}' was not found in the dataset schema."
            )

        if f_op not in ALLOWED_OPERATORS:
            return False, QueryErrorDetails(
                code=ErrorCode.INVALID_FILTER,
                message=f"Unsupported filter operator '{f_op}'. Allowed operators: {sorted(list(ALLOWED_OPERATORS))}"
            )

        # Incompatible relational operators on non-numeric/non-date columns
        if f_op in (">", ">=", "<", "<=") and col_meta.semantic_type in ("text", "categorical", "identifier", "boolean"):
            return False, QueryErrorDetails(
                code=ErrorCode.INVALID_FILTER,
                message=f"Relational operator '{f_op}' cannot be applied to {col_meta.semantic_type} column '{col_meta.name}'."
            )

        # Incompatible string operators on numeric/date columns
        if f_op in ("contains", "starts_with", "ends_with") and col_meta.semantic_type in ("numeric", "date"):
            return False, QueryErrorDetails(
                code=ErrorCode.INVALID_FILTER,
                message=f"String operator '{f_op}' cannot be applied to {col_meta.semantic_type} column '{col_meta.name}'."
            )

    # 4. Validate Limit
    if query_spec.limit is not None:
        if not isinstance(query_spec.limit, int) or query_spec.limit <= 0:
            return False, QueryErrorDetails(
                code=ErrorCode.INVALID_LIMIT,
                message=f"Limit must be a positive integer, got: {query_spec.limit}."
            )

    # 5. Validate Sort
    for sort_item in query_spec.sort:
        if isinstance(sort_item, dict):
            s_col = sort_item.get("column")
            s_dir = sort_item.get("direction", "desc")
        else:
            s_col = sort_item.column
            s_dir = sort_item.direction

        if s_dir not in ("asc", "desc"):
            return False, QueryErrorDetails(
                code=ErrorCode.QUERY_VALIDATION_ERROR,
                message=f"Sort direction must be 'asc' or 'desc', got '{s_dir}'."
            )

        if s_col and s_col not in ("value", "count") and query_spec.metric != s_col:
            col_meta = _find_column_in_schema(s_col, schema_map)
            if not col_meta and s_col not in query_spec.group_by:
                return False, QueryErrorDetails(
                    code=ErrorCode.COLUMN_NOT_FOUND,
                    message=f"Sort column '{s_col}' was not found in the dataset schema."
                )

    # 6. Validate Time Operations
    if query_spec.time_dimension is not None:
        col_meta = _find_column_in_schema(query_spec.time_dimension, schema_map)
        if not col_meta:
            return False, QueryErrorDetails(
                code=ErrorCode.COLUMN_NOT_FOUND,
                message=f"Time dimension column '{query_spec.time_dimension}' was not found in schema."
            )
        if col_meta.semantic_type not in ("date", "unknown") and "datetime" not in col_meta.dtype.lower():
            return False, QueryErrorDetails(
                code=ErrorCode.INVALID_TIME_OPERATION,
                message=f"Column '{query_spec.time_dimension}' is not a date or datetime column (semantic type: {col_meta.semantic_type})."
            )

    if query_spec.time_granularity is not None:
        if query_spec.time_granularity.lower() not in ALLOWED_TIME_GRANULARITIES:
            return False, QueryErrorDetails(
                code=ErrorCode.INVALID_TIME_OPERATION,
                message=f"Unsupported time granularity '{query_spec.time_granularity}'. Allowed: {sorted(list(ALLOWED_TIME_GRANULARITIES))}"
            )

    return True, None


def _find_column_in_schema(name: str, schema_map: Dict[str, ColumnMetadata]) -> Optional[ColumnMetadata]:
    """Helper to locate column in schema map by exact or case-insensitive match."""
    if not name:
        return None
    if name in schema_map:
        return schema_map[name]
    name_lower = name.strip().lower()
    for col_key, meta in schema_map.items():
        if col_key.lower() == name_lower or meta.original_name.lower() == name_lower:
            return meta
    return None


def validate_query_plan(
    query_plan: Union[QuerySpec, Dict[str, Any]],
    df: Optional[Any] = None,
    semantic_model: Optional[Any] = None,
    semantic_embeddings: Optional[Any] = None
) -> Dict[str, Any]:
    """
    Backward-compatible validation function returning {'valid': bool, 'errors': list}.
    """
    if isinstance(query_plan, dict):
        spec = QuerySpec(**query_plan)
    else:
        spec = query_plan

    is_valid, error = validate_query(spec, schema=df)
    if is_valid:
        return {"valid": True, "errors": []}
    return {"valid": False, "errors": [error.message if error else "Validation failed"]}
