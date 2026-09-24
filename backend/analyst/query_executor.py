"""
Deterministic Pandas Query Executor module.
Executes structured QuerySpec instructions strictly using deterministic Pandas operations.
"""

from typing import Any, Dict, List, Optional
import re
import numpy as np
import pandas as pd

from .models import QuerySpec, QueryResult, ResponseType
from .validator import validate_query_spec


def execute_query(spec: QuerySpec, df: pd.DataFrame) -> QueryResult:
    """
    Executes a structured QuerySpec deterministically against a Pandas DataFrame.
    """
    # 1. Validate QuerySpec
    is_valid, error_msg = validate_query_spec(spec, df)
    if not is_valid:
        return QueryResult(
            success=False,
            type=ResponseType.ERROR.value,
            error=error_msg,
            text=f"Validation failed: {error_msg}"
        )

    # 2. Case-insensitive Column Mapping
    df_copy = df.copy()
    col_map = {c.lower(): c for c in df_copy.columns}

    def _resolve_col(name: Optional[str]) -> Optional[str]:
        if not name:
            return None
        return col_map.get(name.lower(), name)

    target_col = _resolve_col(spec.column)
    group_cols = [_resolve_col(g) for g in spec.group_by if _resolve_col(g) in df_copy.columns]

    # 3. Apply Filters First
    total_rows = len(df_copy)
    if spec.filters:
        try:
            df_copy = _apply_filters(df_copy, spec.filters, _resolve_col)
        except Exception as e:
            return QueryResult(
                success=False,
                type=ResponseType.ERROR.value,
                error=f"Filter execution failed: {str(e)}",
                text=f"Filter execution failed: {str(e)}"
            )

    filtered_rows = len(df_copy)
    op = (spec.operation or "count").lower().strip()

    # 4. Group-By Execution
    if group_cols:
        records, table_payload, summary_text = _execute_groupby(df_copy, op, target_col, group_cols, spec)
        return QueryResult(
            success=True,
            type=ResponseType.DATA_RESULT.value,
            query={"operation": op, "column": target_col, "group_by": group_cols},
            result=records,
            table=table_payload,
            text=summary_text,
            metadata={"rows_analyzed": total_rows, "filtered_rows": filtered_rows, "groups_count": len(records)}
        )

    # 5. Non-Grouped Operations
    if op == "distinct":
        if not target_col or target_col not in df_copy.columns:
            return QueryResult(
                success=False,
                type=ResponseType.ERROR.value,
                error="Target column required for distinct operation."
            )
        unique_vals = [_sanitize_scalar(v) for v in df_copy[target_col].dropna().unique().tolist()]
        count_val = len(unique_vals)
        summary_text = f"Found **{count_val}** unique values for **{target_col}**:"
        list_payload = {
            "column": target_col,
            "values": unique_vals,
            "count": count_val
        }
        table_payload = {
            "headers": [target_col],
            "rows": [[v] for v in unique_vals]
        }
        return QueryResult(
            success=True,
            type=ResponseType.DATA_RESULT.value,
            query={"operation": op, "column": target_col},
            result=unique_vals,
            list=list_payload,
            table=table_payload,
            text=summary_text,
            metadata={"rows_analyzed": total_rows, "filtered_rows": filtered_rows, "count": count_val}
        )

    if op == "count_distinct":
        val = int(df_copy[target_col].nunique()) if target_col and target_col in df_copy.columns else 0
        summary_text = f"The count of unique values in **{target_col}** is **{val:,}**."
        scalar_payload = {
            "metric": target_col,
            "aggregation": "count_distinct",
            "value": val
        }
        return QueryResult(
            success=True,
            type=ResponseType.DATA_RESULT.value,
            query={"operation": op, "column": target_col},
            result=val,
            scalar=scalar_payload,
            text=summary_text,
            metadata={"rows_analyzed": total_rows, "filtered_rows": filtered_rows}
        )

    if op in ("sum", "average", "mean", "min", "max", "count"):
        val = _compute_scalar(df_copy, op, target_col)
        formatted_val = f"{val:,.2f}" if isinstance(val, float) else f"{val:,}" if isinstance(val, int) else str(val)
        metric_name = target_col or "records"
        summary_text = f"The **{op}** of **{metric_name}** is **{formatted_val}**."
        scalar_payload = {
            "metric": metric_name,
            "aggregation": op,
            "value": val
        }
        return QueryResult(
            success=True,
            type=ResponseType.DATA_RESULT.value,
            query={"operation": op, "column": target_col},
            result=val,
            scalar=scalar_payload,
            text=summary_text,
            metadata={"rows_analyzed": total_rows, "filtered_rows": filtered_rows}
        )

    return QueryResult(
        success=False,
        type=ResponseType.ERROR.value,
        error=f"Unrecognized operation '{op}'."
    )


def _compute_scalar(df: pd.DataFrame, op: str, col: Optional[str]) -> Any:
    """Computes a single scalar metric."""
    if len(df) == 0:
        return 0

    if op == "count":
        if col and col in df.columns:
            return int(df[col].count())
        return int(len(df))

    if not col or col not in df.columns:
        return 0

    num_series = pd.to_numeric(df[col], errors="coerce").dropna()
    if len(num_series) == 0:
        return 0

    if op == "sum":
        return round(float(num_series.sum()), 4)
    elif op in ("average", "mean"):
        return round(float(num_series.mean()), 4)
    elif op == "min":
        return _sanitize_scalar(num_series.min())
    elif op == "max":
        return _sanitize_scalar(num_series.max())

    return 0


def _execute_groupby(
    df: pd.DataFrame,
    op: str,
    target_col: Optional[str],
    group_cols: List[str],
    spec: QuerySpec
) -> Tuple[List[Dict[str, Any]], Dict[str, Any], str]:
    """Executes group by aggregation and formatting."""
    if len(df) == 0:
        return [], {"headers": group_cols + [target_col or "value"], "rows": []}, "No matching records found."

    if op == "count" and not target_col:
        grouped = df.groupby(group_cols, as_index=False).size()
        grouped.rename(columns={"size": "count"}, inplace=True)
        val_col = "count"
    elif op == "count_distinct" and target_col:
        grouped = df.groupby(group_cols, as_index=False)[target_col].nunique()
        grouped.rename(columns={target_col: "unique_count"}, inplace=True)
        val_col = "unique_count"
    elif target_col and target_col in df.columns:
        if op in ("sum", "average", "mean"):
            df[target_col] = pd.to_numeric(df[target_col], errors="coerce")
            agg_fn = "mean" if op in ("average", "mean") else "sum"
            grouped = df.groupby(group_cols, as_index=False)[target_col].agg(agg_fn)
            val_col = target_col
        elif op == "min":
            grouped = df.groupby(group_cols, as_index=False)[target_col].min()
            val_col = target_col
        elif op == "max":
            grouped = df.groupby(group_cols, as_index=False)[target_col].max()
            val_col = target_col
        elif op == "count":
            grouped = df.groupby(group_cols, as_index=False)[target_col].count()
            val_col = target_col
        else:
            grouped = df.groupby(group_cols, as_index=False)[target_col].sum()
            val_col = target_col
    else:
        grouped = df.groupby(group_cols, as_index=False).size()
        grouped.rename(columns={"size": "count"}, inplace=True)
        val_col = "count"

    # Sorting
    if spec.sort:
        for s in spec.sort:
            s_col = s.get("column") if isinstance(s, dict) else s.column
            s_dir = (s.get("direction") if isinstance(s, dict) else s.direction) or "desc"
            sort_target = val_col
            if s_col in grouped.columns:
                sort_target = s_col
            grouped = grouped.sort_values(by=sort_target, ascending=(s_dir.lower() == "asc")).reset_index(drop=True)
    else:
        if val_col in grouped.columns:
            grouped = grouped.sort_values(by=val_col, ascending=False).reset_index(drop=True)

    # Limit
    if spec.limit and spec.limit > 0:
        grouped = grouped.head(spec.limit)

    headers = list(grouped.columns)
    rows = []
    records = []
    for _, record in grouped.iterrows():
        clean_row = [_sanitize_scalar(v) for v in record]
        rows.append(clean_row)
        records.append({headers[i]: clean_row[i] for i in range(len(headers))})

    group_str = ", ".join(group_cols)
    metric_desc = f"**{target_col}**" if target_col else "records"
    limit_desc = f" (top {spec.limit})" if spec.limit else ""
    summary_text = f"Breakdown of {metric_desc} grouped by **{group_str}**{limit_desc} ({len(records)} groups found):"

    return records, {"headers": headers, "rows": rows}, summary_text


def _apply_filters(df: pd.DataFrame, filters: List[Any], resolve_col_fn) -> pd.DataFrame:
    """Applies filter criteria to DataFrame safely."""
    for f in filters:
        if isinstance(f, dict):
            col_raw = f.get("column")
            op = f.get("operator", "=")
            val = f.get("value")
        else:
            col_raw = f.column
            op = f.operator
            val = f.value

        col = resolve_col_fn(col_raw)
        if not col or col not in df.columns:
            continue

        series = df[col]
        is_date = _is_date_filter(series, val)

        if op == "=":
            if series.dtype == object or isinstance(val, str):
                df = df[series.astype(str).str.lower() == str(val).lower()]
            else:
                df = df[series == val]
        elif op == "!=":
            if series.dtype == object or isinstance(val, str):
                df = df[series.astype(str).str.lower() != str(val).lower()]
            else:
                df = df[series != val]
        elif op == ">":
            if is_date:
                df = df[pd.to_datetime(series, errors="coerce") > pd.to_datetime(val)]
            else:
                try:
                    df = df[pd.to_numeric(series, errors="coerce") > float(val)]
                except Exception:
                    df = df[series > val]
        elif op == ">=":
            if is_date:
                df = df[pd.to_datetime(series, errors="coerce") >= pd.to_datetime(val)]
            else:
                try:
                    df = df[pd.to_numeric(series, errors="coerce") >= float(val)]
                except Exception:
                    df = df[series >= val]
        elif op == "<":
            if is_date:
                df = df[pd.to_datetime(series, errors="coerce") < pd.to_datetime(val)]
            else:
                try:
                    df = df[pd.to_numeric(series, errors="coerce") < float(val)]
                except Exception:
                    df = df[series < val]
        elif op == "<=":
            if is_date:
                df = df[pd.to_datetime(series, errors="coerce") <= pd.to_datetime(val)]
            else:
                try:
                    df = df[pd.to_numeric(series, errors="coerce") <= float(val)]
                except Exception:
                    df = df[series <= val]
        elif op == "between":
            if isinstance(val, (list, tuple)) and len(val) == 2:
                v1, v2 = val[0], val[1]
                if is_date:
                    dt_s = pd.to_datetime(series, errors="coerce")
                    df = df[(dt_s >= pd.to_datetime(v1)) & (dt_s <= pd.to_datetime(v2))]
                else:
                    try:
                        num_s = pd.to_numeric(series, errors="coerce")
                        df = df[(num_s >= float(v1)) & (num_s <= float(v2))]
                    except Exception:
                        df = df[(series >= v1) & (series <= v2)]
        elif op == "in":
            if isinstance(val, (list, tuple, set)):
                val_set = {str(v).lower() for v in val}
                df = df[series.astype(str).str.lower().isin(val_set)]
            else:
                df = df[series == val]
        elif op == "contains":
            df = df[series.astype(str).str.contains(str(val), case=False, na=False)]

    return df


def _is_date_filter(series: pd.Series, val: Any = None) -> bool:
    """Checks if series or value represents date values."""
    if pd.api.types.is_datetime64_any_dtype(series):
        return True
    if any(kw in str(series.name).lower() for kw in ["date", "time", "year", "timestamp"]):
        return True
    check_val = val
    if isinstance(val, (list, tuple)) and len(val) > 0:
        check_val = val[0]
    if isinstance(check_val, str) and re.match(r"^\d{4}(-\d{2}(-\d{2})?)?", check_val.strip()):
        return True
    return False


def _sanitize_scalar(val: Any) -> Any:
    """Converts Pandas/Numpy types into JSON-serializable Python native types."""
    if pd.isna(val):
        return None
    if isinstance(val, (np.floating, float)):
        return round(float(val), 4)
    if isinstance(val, (np.integer, int)):
        return int(val)
    if isinstance(val, (pd.Timestamp, np.datetime64)):
        return str(val)
    return val
