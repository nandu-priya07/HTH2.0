"""
Query Validator module.
Validates single and multi-query QuerySpecs against active DataFrame schema, column types, and operations.
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
    "max",
    "conditional_count",
    "column_value_count",
    "column_value_distribution",
    "multi_column_value_distribution",
    "value_distribution",
    "record_lookup"
}


NUMERIC_OPERATIONS = {
    "sum",
    "average",
    "mean"
}

VALID_CONDITION_OPERATORS = {
    "eq", "neq", "gt", "gte", "lt", "lte", "in", "not_in", "contains",
    "starts_with", "ends_with", "between", "equals", "=", "==", "!=",
    "<>", ">", ">=", "<", "<="
}


def validate_query_spec(
    spec: QuerySpec,
    df: pd.DataFrame,
    schema: Optional[Dict[str, Any]] = None
) -> Tuple[bool, Optional[str]]:
    """
    Validates a single QuerySpec against the DataFrame.
    Returns (is_valid, error_message).
    """
    if not spec:
        return False, "QuerySpec cannot be None."

    if not spec.operation:
        return False, "QuerySpec is missing a required 'operation'."

    op = spec.operation.lower().strip()
    if op not in SUPPORTED_OPERATIONS:
        return False, f"Unsupported operation '{spec.operation}'. Supported operations are: {', '.join(sorted(SUPPORTED_OPERATIONS))}."

    df_col_lower_map = {c.lower(): c for c in df.columns}

    # 0. Validate record_lookup
    if op == "record_lookup":
        if spec.columns:
            for col in spec.columns:
                if col.lower() not in df_col_lower_map:
                    return False, f"Column '{col}' does not exist in dataset."
        if spec.filters:
            for f in spec.filters:
                col_name = f.get("column") if isinstance(f, dict) else f.column
                if not col_name or col_name.lower() not in df_col_lower_map:
                    return False, f"Filter column '{col_name}' does not exist in dataset."
        return True, None

    # 1. Validate conditional_count / column_value_count
    if op in ("conditional_count", "column_value_count"):
        target_cols = spec.columns or ([spec.column] if spec.column else [])
        if not target_cols:
            return False, f"Operation '{op}' requires at least one target column in 'columns' or 'column'."

        for col in target_cols:
            if col.lower() not in df_col_lower_map:
                return False, f"Column '{col}' does not exist in dataset."

        if not spec.condition:
            return False, f"Operation '{op}' requires a 'condition' specifying operator and value."

        cond_op = str(spec.condition.get("operator", "equals") if isinstance(spec.condition, dict) else spec.condition.operator).lower()
        if cond_op not in VALID_CONDITION_OPERATORS:
            return False, f"Unsupported condition operator '{cond_op}'."

        cond_val = spec.condition.get("value") if isinstance(spec.condition, dict) else spec.condition.value
        if cond_val is None:
            return False, "Condition 'value' cannot be None."

        return True, None

    # 2. Validate multi_column_value_distribution, value_distribution, and column_value_distribution
    if op in ("multi_column_value_distribution", "value_distribution", "column_value_distribution"):
        target_cols = spec.columns or ([spec.column] if spec.column else [])
        if not target_cols:
            return False, f"Operation '{op}' requires at least one target column in 'columns' or 'column'."

        for col in target_cols:
            if col.lower() not in df_col_lower_map:
                return False, f"Column '{col}' does not exist in dataset."

        # Condition is optional for distribution (null for full distribution)
        if spec.condition:
            cond_op = str(spec.condition.get("operator", "equals") if isinstance(spec.condition, dict) else spec.condition.operator).lower()
            if cond_op not in VALID_CONDITION_OPERATORS:
                return False, f"Unsupported condition operator '{cond_op}'."

        return True, None


    # 3. Validate single column / columns for standard operations
    if spec.column:
        col_actual = df_col_lower_map.get(spec.column.lower())
        if not col_actual:
            return False, f"The dataset does not contain a field corresponding to '{spec.column}'."

        if op in NUMERIC_OPERATIONS:
            col_series = df[col_actual]
            is_num_dtype = pd.api.types.is_numeric_dtype(col_series)
            if not is_num_dtype:
                converted = pd.to_numeric(col_series.dropna().head(100), errors="coerce")
                if converted.isna().all():
                    return False, f"Operation '{op}' requires a numeric column, but '{spec.column}' is not numeric."

    elif spec.columns:
        for col in spec.columns:
            if col.lower() not in df_col_lower_map:
                return False, f"The dataset does not contain a field corresponding to '{col}'."

    elif op != "count":
        return False, f"Operation '{op}' requires a target column."

    # 3. Validate group_by columns
    if spec.group_by:
        for g_col in spec.group_by:
            if g_col.lower() not in df_col_lower_map:
                return False, f"The dataset does not contain a field corresponding to '{g_col}'."

    # 4. Validate filter columns
    if spec.filters:
        for f in spec.filters:
            col_name = f.get("column") if isinstance(f, dict) else f.column
            if not col_name or col_name.lower() not in df_col_lower_map:
                return False, f"The dataset does not contain a field corresponding to '{col_name}'."

    # 5. Validate sort columns
    if spec.sort:
        for s in spec.sort:
            s_col = s.get("column") if isinstance(s, dict) else s.column
            if s_col and s_col.lower() not in df_col_lower_map and s_col.lower() not in ("value", "count"):
                if spec.column and s_col.lower() == spec.column.lower():
                    continue
                return False, f"The dataset does not contain a field corresponding to '{s_col}'."

    # 6. Validate limit
    if spec.limit is not None:
        if not isinstance(spec.limit, int) or spec.limit <= 0:
            return False, f"Limit must be a positive integer, got '{spec.limit}'."

    return True, None


def validate_queries(
    queries: List[QuerySpec],
    df: pd.DataFrame,
    schema: Optional[Dict[str, Any]] = None
) -> Tuple[bool, Optional[str]]:
    """
    Validates a list of QuerySpecs. Returns (is_valid, error_message).
    """
    if not queries:
        return False, "No queries provided for execution."

    for idx, q in enumerate(queries):
        is_valid, err = validate_query_spec(q, df, schema)
        if not is_valid:
            return False, f"Query #{idx + 1} validation error: {err}"

    return True, None
