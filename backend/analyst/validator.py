"""
Query Validator module.
Validates QuerySpec against the active DataFrame schema, column data types, and supported operations.
"""

from typing import Any, Dict, List, Optional, Tuple
import pandas as pd
from .models import QuerySpec, QueryOperation

SUPPORTED_OPERATIONS = {
    "sum",
    "average",
    "mean",
    "count",
    "count_distinct",
    "distinct",
    "min",
    "max"
}

NUMERIC_OPERATIONS = {
    "sum",
    "average",
    "mean"
}


def validate_query_spec(
    spec: QuerySpec,
    df: pd.DataFrame,
    schema: Optional[Dict[str, Any]] = None
) -> Tuple[bool, Optional[str]]:
    """
    Validates a QuerySpec against the DataFrame.
    Returns (is_valid, error_message).
    """
    if not spec:
        return False, "QuerySpec cannot be None."

    if not spec.operation:
        return False, "QuerySpec is missing a required 'operation'."

    op = spec.operation.lower().strip()
    if op not in SUPPORTED_OPERATIONS:
        return False, f"Unsupported operation '{spec.operation}'. Supported operations are: {', '.join(sorted(SUPPORTED_OPERATIONS))}."

    df_columns = set(df.columns)
    df_col_lower_map = {c.lower(): c for c in df.columns}

    # Validate target column
    if spec.column:
        col_actual = df_col_lower_map.get(spec.column.lower())
        if not col_actual:
            return False, f"Target column '{spec.column}' does not exist in dataset."

        # Numeric operation check
        if op in NUMERIC_OPERATIONS:
            col_series = df[col_actual]
            # Check if column is numeric or can be converted to numeric
            is_num_dtype = pd.api.types.is_numeric_dtype(col_series)
            if not is_num_dtype:
                # Check sample non-null values
                converted = pd.to_numeric(col_series.dropna().head(100), errors="coerce")
                if converted.isna().all():
                    return False, f"Operation '{op}' requires a numeric column, but '{spec.column}' is not numeric."
    elif op != "count":
        # Operations other than general count require a target column
        return False, f"Operation '{op}' requires a target column."

    # Validate group_by columns
    if spec.group_by:
        for g_col in spec.group_by:
            if g_col.lower() not in df_col_lower_map:
                return False, f"Group by column '{g_col}' does not exist in dataset."

    # Validate filter columns
    if spec.filters:
        for f in spec.filters:
            col_name = f.get("column") if isinstance(f, dict) else f.column
            if not col_name or col_name.lower() not in df_col_lower_map:
                return False, f"Filter column '{col_name}' does not exist in dataset."

    # Validate sort columns
    if spec.sort:
        for s in spec.sort:
            s_col = s.get("column") if isinstance(s, dict) else s.column
            if s_col and s_col.lower() not in df_col_lower_map and s_col.lower() not in ("value", "count"):
                # If target metric is specified, sort can refer to the metric or group_by
                if spec.column and s_col.lower() == spec.column.lower():
                    continue
                return False, f"Sort column '{s_col}' does not exist in dataset."

    # Validate limit
    if spec.limit is not None:
        if not isinstance(spec.limit, int) or spec.limit <= 0:
            return False, f"Limit must be a positive integer, got '{spec.limit}'."

    return True, None
