"""
Deterministic Pandas Query Executor module.
Executes single-query, multi-query, and multi-column conditional count instructions
strictly using deterministic Pandas operations.
"""

from typing import Any, Dict, List, Optional, Tuple, Union
import re
import numpy as np
import pandas as pd
import duckdb

from .models import QuerySpec, QueryResult, ResponseType
from .validator import validate_query_spec, validate_queries


class ZeroMatchError(Exception):
    """Raised when a filter matches zero rows in the DataFrame."""

    def __init__(self, message: str, filter_spec: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.filter_spec = filter_spec


class ColumnNotFoundError(Exception):
    """Raised when a requested filter or aggregation column does not exist in the dataset."""
    pass


def execute_queries(queries: List[QuerySpec], df: pd.DataFrame) -> QueryResult:
    """
    Executes one or multiple QuerySpecs against a Pandas DataFrame.
    """
    if not queries:
        return QueryResult(
            success=False,
            type=ResponseType.ERROR.value,
            error="No queries provided for execution."
        )

    if len(queries) == 1:
        return execute_query(queries[0], df)

    # Multi-query execution
    sub_results: List[QueryResult] = []
    for idx, q in enumerate(queries):
        sub_res = execute_query(q, df)
        if not sub_res.success:
            if sub_res.status == "no_data":
                # Keep the zero-match details so the caller can explain which filter found nothing.
                return sub_res
            return QueryResult(
                success=False,
                type=ResponseType.ERROR.value,
                status="error",
                error=f"Query #{idx + 1} failed: {sub_res.error}",
                text=f"Query #{idx + 1} execution failed: {sub_res.error}"
            )
        sub_results.append(sub_res)

    # Combine results
    queries_dict_list = [q.to_dict() for q in queries]
    results_list = [r.result for r in sub_results]
    scalars = [r.scalar for r in sub_results if r.scalar is not None]
    tables = [r.table for r in sub_results if r.table is not None]

    # Combine text summaries
    summary_lines = ["Calculated multi-operation analysis:"]
    for idx, r in enumerate(sub_results):
        if r.text:
            summary_lines.append(f"- {r.text}")

    combined_text = "\n".join(summary_lines)

    # If all queries are scalar metrics, build a unified summary table
    combined_table = None
    if len(scalars) == len(sub_results) and len(scalars) > 1:
        combined_table = {
            "headers": ["metric", "aggregation", "value"],
            "rows": [
                [
                    s.get("metric", "metric"),
                    s.get("aggregation", "agg"),
                    _sanitize_scalar(s.get("value"))
                ]
                for s in scalars
            ]
        }
    elif tables:
        combined_table = tables[0]

    return QueryResult(
        success=True,
        type=ResponseType.DATA_RESULT.value,
        query=queries_dict_list[0] if queries_dict_list else None,
        queries=queries_dict_list,
        result=results_list,
        results=results_list,
        scalar=scalars[0] if scalars else None,
        scalars=scalars if scalars else None,
        table=combined_table,
        tables=tables if tables else None,
        text=combined_text,
        metadata={
            "queries_executed": len(queries),
            "rows_analyzed": len(df),
            "sub_results": [
                {
                    "scalar": r.scalar,
                    "rows_before_filter": r.rows_before_filter,
                    "rows_after_filter": r.rows_after_filter,
                    "derived_metric": r.derived_metric,
                }
                for r in sub_results
            ]
        },
        rows_before_filter=len(df),
        fields_used=list(dict.fromkeys(f for r in sub_results for f in (r.fields_used or []))),
        calculation_steps=[s for r in sub_results for s in (r.calculation_steps or [])]
    )


def _gather_fields_used(spec: QuerySpec, target_col: Optional[str], group_cols: List[str]) -> List[str]:
    used = []
    if target_col and target_col not in used:
        used.append(target_col)
    for c in (spec.columns or []):
        if c and c not in used:
            used.append(c)
    for g in (group_cols or []):
        if g and g not in used:
            used.append(g)
    for f in (spec.filters or []):
        col = f.column if hasattr(f, "column") else (f.get("column") if isinstance(f, dict) else None)
        if col and col not in used:
            used.append(col)
    for s in (spec.sort or []):
        col = s.column if hasattr(s, "column") else (s.get("column") if isinstance(s, dict) else None)
        if col and col not in used:
            used.append(col)
    return used


_OP_SYMBOLS = {"+": "+", "-": "-", "*": "×"}
_FILTER_OP_TEXT = {"equals": "=", "=": "=", "==": "=", "eq": "=", "is": "=", "!=": "≠", "<>": "≠",
                   ">": ">", ">=": "≥", "<": "<", "<=": "≤", "between": "between", "in": "in", "contains": "contains"}


def _materialize_derived_metric(df: pd.DataFrame, spec: QuerySpec) -> Tuple[pd.DataFrame, QuerySpec]:
    """Adds the derived metric as a row-level column so filters, grouping and aggregation apply unchanged."""
    derived = spec.derived_metric
    operands = list(derived.operands or [])
    missing = [c for c in operands if c not in df.columns]
    if len(operands) != 2 or missing or derived.operator not in _OP_SYMBOLS:
        raise ValueError(
            f"Cannot derive '{derived.name}': required columns {', '.join(missing or operands)} are not available."
        )
    a = pd.to_numeric(df[operands[0]], errors="coerce")
    b = pd.to_numeric(df[operands[1]], errors="coerce")
    values = a + b if derived.operator == "+" else a - b if derived.operator == "-" else a * b

    name = derived.name
    while name in df.columns:
        name = f"{name}_derived"
    work = df.copy()
    work[name] = values
    return work, spec.model_copy(update={"column": name})


def _rows(n: Any) -> str:
    n = int(n)
    return f"{n:,} row" if n == 1 else f"{n:,} rows"


def _format_filter_step(f: Dict[str, Any]) -> str:
    op = _FILTER_OP_TEXT.get(str(f.get("operator", "=")).lower(), f.get("operator"))
    val = f.get("value")
    if isinstance(val, (list, tuple)):
        val = " and ".join(str(v) for v in val) if op == "between" else ", ".join(str(v) for v in val)
    return f"{f.get('column')} {op} {val}"


def _build_calculation_steps(result: QueryResult, spec: QuerySpec, exec_spec: QuerySpec,
                             trace: List[Dict[str, Any]]) -> List[str]:
    meta = result.metadata or {}
    before = meta.get("rows_before_filter", meta.get("rows_analyzed"))
    steps: List[str] = []
    if before is not None:
        steps.append(f"Started with {_rows(before)}.")
    for t in trace:
        steps.append(f"Filtered {_format_filter_step(t['filter'])} → {_rows(t['rows_after'])}.")
    derived = spec.derived_metric
    if derived is not None and derived.kind == "expression":
        steps.append(f"Calculated {derived.name} = {derived.formula} for each row.")
    elif derived is not None and derived.kind == "count_distinct":
        steps.append(f"Counted distinct {derived.source_column} values as {derived.name.replace('_', ' ')}.")
    if exec_spec.group_by:
        groups = meta.get("groups_total", meta.get("groups_count"))
        steps.append(f"Grouped by {', '.join(exec_spec.group_by)}" + (f" ({groups} groups)." if groups is not None else "."))
    op = (exec_spec.operation or "").lower()
    if op in ("sum", "average", "mean", "min", "max", "count", "count_distinct"):
        agg = {"average": "AVG", "mean": "AVG", "count_distinct": "COUNT DISTINCT"}.get(op, op.upper())
        steps.append(f"Applied {agg}({exec_spec.column or '*'})" + (" within each group." if exec_spec.group_by else "."))
    return steps


def _finalize_result(result: QueryResult, spec: QuerySpec, exec_spec: QuerySpec,
                     trace: List[Dict[str, Any]]) -> QueryResult:
    """Copies execution metadata into the canonical QueryResult fields."""
    meta = result.metadata if result.metadata is not None else {}
    if not result.success and result.status == "success":
        result.status = "error"

    fields = list(meta.get("fields_used") or [])
    derived = spec.derived_metric
    if derived is not None:
        derived_dict = derived.to_dict()
        # The materialized helper column is not a dataset field; report its real inputs instead.
        if derived.kind == "expression":
            fields = [f for f in fields if f != exec_spec.column]
        fields = list(dict.fromkeys(list(derived.required_columns) + fields))
        meta["derived_metric"] = derived_dict
        result.derived_metric = derived_dict
        if result.scalar and derived.kind == "expression":
            result.scalar["metric"] = derived.name
    if fields:
        meta["fields_used"] = fields
    result.fields_used = fields or None

    result.filters_applied = meta.get("filters_applied") or [
        f.to_dict() if hasattr(f, "to_dict") else f for f in (spec.filters or [])
    ]
    result.rows_before_filter = meta.get("rows_before_filter", meta.get("rows_analyzed"))
    result.rows_after_filter = meta.get("rows_after_filter", meta.get("filtered_rows"))
    result.aggregation = meta.get("aggregation") or (exec_spec.operation or "").upper() or None
    result.group_by = meta.get("group_by") or list(exec_spec.group_by or [])
    if result.success:
        result.calculation_steps = _build_calculation_steps(result, spec, exec_spec, trace)
        meta["calculation_steps"] = result.calculation_steps
    if spec.requested_metric:
        meta["requested_metric"] = spec.requested_metric
    if spec.metric_mapping:
        meta["metric_mapping"] = spec.metric_mapping
    result.metadata = meta
    return result


def execute_query(spec: QuerySpec, df: pd.DataFrame) -> QueryResult:
    """
    Executes a structured QuerySpec deterministically against a Pandas DataFrame.
    Filters are always applied before aggregation; derived metrics are computed per row first.
    """
    exec_spec, work_df = spec, df
    if spec.derived_metric is not None and spec.derived_metric.kind == "expression":
        try:
            work_df, exec_spec = _materialize_derived_metric(df, spec)
        except ValueError as e:
            return QueryResult(success=False, type=ResponseType.ERROR.value, status="error",
                               error=str(e), text=str(e))
    trace: List[Dict[str, Any]] = []
    result = _execute_query_core(exec_spec, work_df, trace)
    return _finalize_result(result, spec, exec_spec, trace)


def _execute_query_core(spec: QuerySpec, df: pd.DataFrame, filter_trace: Optional[List[Dict[str, Any]]] = None) -> QueryResult:
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

    # Validate target column if specified
    if spec.column:
        resolved_target = _resolve_col(spec.column)
        if not resolved_target or resolved_target not in df_copy.columns:
            err = f"The dataset does not contain a field corresponding to '{spec.column}'."
            return QueryResult(
                success=False,
                type=ResponseType.ERROR.value,
                error=err,
                text=err
            )

    # Validate group_by columns if specified
    for g in (spec.group_by or []):
        resolved_g = _resolve_col(g)
        if not resolved_g or resolved_g not in df_copy.columns:
            err = f"The dataset does not contain a field corresponding to '{g}'."
            return QueryResult(
                success=False,
                type=ResponseType.ERROR.value,
                error=err,
                text=err
            )

    target_col = _resolve_col(spec.column)
    target_cols = [_resolve_col(c) for c in (spec.columns or []) if _resolve_col(c) in df_copy.columns]
    group_cols = [_resolve_col(g) for g in (spec.group_by or []) if _resolve_col(g) in df_copy.columns]

    # 3. Apply Filters First
    total_rows = len(df_copy)
    if spec.filters:
        try:
            df_copy = _apply_filters(df_copy, spec.filters, _resolve_col, trace=filter_trace)
        except ZeroMatchError as zme:
            return QueryResult(
                success=False,
                type=ResponseType.NO_DATA.value,
                status="no_data",
                error=str(zme),
                text=str(zme),
                metadata={
                    "rows_analyzed": total_rows,
                    "filtered_rows": 0,
                    "rows_before_filter": total_rows,
                    "rows_after_filter": 0,
                    "fields_used": _gather_fields_used(spec, target_col, group_cols),
                    "filters_applied": [f.to_dict() if hasattr(f, 'to_dict') else f for f in (spec.filters or [])],
                    "empty_filter": zme.filter_spec
                }
            )
        except ColumnNotFoundError as cnfe:
            return QueryResult(
                success=False,
                type=ResponseType.ERROR.value,
                error=str(cnfe),
                text=str(cnfe),
                metadata={"rows_analyzed": total_rows}
            )
        except Exception as e:
            return QueryResult(
                success=False,
                type=ResponseType.ERROR.value,
                error=f"Filter execution failed: {str(e)}",
                text=f"Filter execution failed: {str(e)}"
            )

    filtered_rows = len(df_copy)
    fields_used = _gather_fields_used(spec, target_col, group_cols)
    filters_applied = [f.to_dict() if hasattr(f, 'to_dict') else f for f in (spec.filters or [])]
    op = (spec.operation or "count").lower().strip()

    # 4. CONDITIONAL_COUNT across multiple or single columns
    if op == "conditional_count":
        eval_cols = target_cols if target_cols else ([target_col] if target_col else [])
        cond = spec.condition or {}
        cond_op = str(cond.get("operator", "equals") if isinstance(cond, dict) else getattr(cond, "operator", "equals")).lower()
        cond_val = cond.get("value") if isinstance(cond, dict) else getattr(cond, "value", None)

        records = []
        rows = []
        for col in eval_cols:
            cnt = _count_column_condition(df_copy[col], cond_op, cond_val)
            records.append({
                "column": col,
                "condition": cond_val,
                "count": cnt
            })
            rows.append([col, cond_val, cnt])

        table_payload = {
            "headers": ["column", "condition", "count"],
            "rows": rows
        }

        cols_count = len(eval_cols)
        summary_text = f"Calculated **{cond_val}** counts across **{cols_count}** columns ({filtered_rows:,} rows analyzed):"

        return QueryResult(
            success=True,
            type=ResponseType.DATA_RESULT.value,
            query={
                "operation": op,
                "columns": eval_cols,
                "condition": {"operator": cond_op, "value": cond_val}
            },
            result=records,
            table=table_payload,
            text=summary_text,
            metadata={
                "rows_analyzed": total_rows,
                "filtered_rows": filtered_rows,
                "columns_analyzed": cols_count
            }
        )

    # 4b. MULTI_COLUMN_VALUE_DISTRIBUTION & VALUE_DISTRIBUTION
    if op in ("multi_column_value_distribution", "value_distribution"):
        eval_cols = target_cols if target_cols else ([target_col] if target_col else [])
        if not eval_cols:
            return QueryResult(
                success=False,
                type=ResponseType.ERROR.value,
                error=f"Operation '{op}' requires at least one target column."
            )

        cond = spec.condition
        cond_op = None
        cond_val = None
        if cond:
            cond_op = str(cond.get("operator", "equals") if isinstance(cond, dict) else getattr(cond, "operator", "equals")).lower()
            cond_val = cond.get("value") if isinstance(cond, dict) else getattr(cond, "value", None)

        grade_order_weight = {
            "O": 10, "A+": 9, "A": 8, "B+": 7, "B": 6, "C+": 5, "C": 4, "D": 3, "E": 2, "P": 1, "PASS": 1,
            "F": -1, "FAIL": -1, "RA": -2, "U": -3, "AB": -4, "ABSENT": -4, "W": -5, "WH": -6
        }

        all_distinct_vals_set = set()
        col_value_counts = {}

        for col in eval_cols:
            s = df_copy[col].dropna().astype(str).str.strip()
            s = s[s != ""]  # remove empty strings

            if cond_val is not None:
                if isinstance(cond_val, (list, tuple, set)):
                    target_set = {str(v).strip().upper() for v in cond_val}
                    s = s[s.str.upper().isin(target_set)]
                elif cond_op in ("in", "contains"):
                    target_set = {str(v).strip().upper() for v in (cond_val if isinstance(cond_val, list) else [cond_val])}
                    s = s[s.str.upper().isin(target_set)]
                else:
                    s = s[s.str.upper() == str(cond_val).strip().upper()]

            counts = s.value_counts()
            col_value_counts[col] = counts
            all_distinct_vals_set.update(counts.index.tolist())

        def _grade_sort_key(v):
            vu = str(v).upper()
            if vu in grade_order_weight:
                return (0, -grade_order_weight[vu], vu)
            return (1, 0, str(v))

        distinct_vals = sorted(list(all_distinct_vals_set), key=_grade_sort_key)

        records = []
        rows = []
        for col in eval_cols:
            counts = col_value_counts.get(col, pd.Series(dtype=int))
            row = [col]
            for val in distinct_vals:
                c = int(counts.get(val, 0))
                records.append({
                    "subject": col,
                    "column": col,
                    "grade": val,
                    "value": val,
                    "count": c
                })
                row.append(c)
            rows.append(row)

        headers = ["Subject"] + [str(v) for v in distinct_vals]
        table_payload = {
            "headers": headers,
            "rows": rows
        }

        cols_count = len(eval_cols)
        distinct_count = len(distinct_vals)
        if cond_val is not None:
            summary_text = f"Calculated grade distribution for **{cond_val}** across **{cols_count}** subjects ({filtered_rows:,} rows analyzed):"
        elif cols_count == 1:
            summary_text = f"Calculated grade distribution for **{eval_cols[0]}** ({filtered_rows:,} rows analyzed, {distinct_count} distinct grades):"
        else:
            summary_text = f"Calculated grade distribution across **{cols_count}** subjects ({filtered_rows:,} rows analyzed, {distinct_count} distinct grades):"

        cond_dict = {"operator": cond_op, "value": cond_val} if cond_val is not None else None

        return QueryResult(
            success=True,
            type=ResponseType.DATA_RESULT.value,
            query={
                "operation": op,
                "columns": eval_cols,
                "column": eval_cols[0] if len(eval_cols) == 1 else None,
                "condition": cond_dict,
                "group_by": [],
                "filters": [f.to_dict() if hasattr(f, "to_dict") else f for f in spec.filters],
                "measure": "count",
                "value_distribution": True,
                "raw_question": spec.raw_question
            },
            result=records,
            table=table_payload,
            text=summary_text,
            metadata={
                "rows_analyzed": total_rows,
                "filtered_rows": filtered_rows,
                "rows_before_filter": total_rows,
                "rows_after_filter": filtered_rows,
                "fields_used": fields_used,
                "filters_applied": filters_applied,
                "columns_analyzed": cols_count,
                "distinct_values_count": distinct_count,
                "query_plan": spec.to_dict()
            }
        )

    # 5. Group-By Execution
    if group_cols:
        records, table_payload, summary_text = _execute_groupby(df_copy, op, target_col, group_cols, spec)
        overall = _compute_overall(df_copy, op, target_col)
        return QueryResult(
            success=True,
            type=ResponseType.DATA_RESULT.value,
            query={"operation": op, "column": target_col, "group_by": group_cols, "filters": filters_applied},
            result=records,
            table=table_payload,
            text=summary_text,
            metadata={
                "rows_analyzed": total_rows,
                "filtered_rows": filtered_rows,
                "rows_before_filter": total_rows,
                "rows_after_filter": filtered_rows,
                "fields_used": fields_used,
                "filters_applied": filters_applied,
                "aggregation": op.upper(),
                "group_by": group_cols,
                "groups_count": len(records),
                "groups_total": int(df_copy.groupby(group_cols, dropna=False).ngroups) if len(df_copy) else 0,
                "value_column": table_payload["headers"][-1] if table_payload.get("headers") else None,
                # Deterministic whole-population aggregate (pre-limit), used for totals and shares.
                "overall_value": overall,
                "total": overall if op in ("sum", "count") else None,
                "query_plan": spec.to_dict()
            }
        )

    # 6. Non-Grouped DISTINCT Operation
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
            query={"operation": op, "column": target_col, "filters": filters_applied},
            result=unique_vals,
            list=list_payload,
            table=table_payload,
            text=summary_text,
            metadata={
                "rows_analyzed": total_rows,
                "filtered_rows": filtered_rows,
                "rows_before_filter": total_rows,
                "rows_after_filter": filtered_rows,
                "fields_used": fields_used,
                "filters_applied": filters_applied,
                "count": count_val,
                "query_plan": spec.to_dict()
            }
        )

    # 7. Non-Grouped COUNT_DISTINCT Operation
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
            query={"operation": op, "column": target_col, "filters": filters_applied},
            result=val,
            scalar=scalar_payload,
            text=summary_text,
            metadata={
                "rows_analyzed": total_rows,
                "filtered_rows": filtered_rows,
                "rows_before_filter": total_rows,
                "rows_after_filter": filtered_rows,
                "fields_used": fields_used,
                "filters_applied": filters_applied,
                "aggregation": "COUNT_DISTINCT",
                "group_by": group_cols,
                "query_plan": spec.to_dict()
            }
        )

    # 8. Non-Grouped Standard Aggregations (sum, average, count, min, max)
    if op in ("sum", "average", "mean", "min", "max", "count"):
        val = _compute_scalar(df_copy, op, target_col)
        formatted_val = f"{val:,.2f}" if isinstance(val, float) else f"{val:,}" if isinstance(val, int) else str(val)
        metric_name = target_col or "records"
        filter_phrase = ""
        if spec.filters:
            f_parts = []
            for f in spec.filters:
                fc = f.column if hasattr(f, 'column') else f.get('column')
                fv = f.value if hasattr(f, 'value') else f.get('value')
                f_parts.append(f"{fc} = {fv}")
            if f_parts:
                filter_phrase = f" for **{' and '.join(f_parts)}**"

        summary_text = f"The **{op}** of **{metric_name}**{filter_phrase} is **{formatted_val}**."
        scalar_payload = {
            "metric": metric_name,
            "aggregation": op,
            "value": val
        }
        return QueryResult(
            success=True,
            type=ResponseType.DATA_RESULT.value,
            query={"operation": op, "column": target_col, "filters": filters_applied},
            result=val,
            scalar=scalar_payload,
            text=summary_text,
            metadata={
                "rows_analyzed": total_rows,
                "filtered_rows": filtered_rows,
                "rows_before_filter": total_rows,
                "rows_after_filter": filtered_rows,
                "fields_used": fields_used,
                "filters_applied": filters_applied,
                "aggregation": op.upper(),
                "group_by": group_cols,
                "query_plan": spec.to_dict()
            }
        )

    return QueryResult(
        success=False,
        type=ResponseType.ERROR.value,
        error=f"Unrecognized operation '{op}'."
    )


def _count_column_condition(series: pd.Series, op: str, val: Any) -> int:
    """Counts rows in a column series meeting a condition safely and deterministically."""
    if len(series) == 0:
        return 0

    if op in ("equals", "=", "=="):
        if val is None:
            return int(series.isna().sum())
        # String match ignoring case and whitespace
        str_series = series.astype(str).str.strip()
        str_val = str(val).strip()
        return int((str_series.str.upper() == str_val.upper()).sum())

    elif op in ("!=", "<>"):
        if val is None:
            return int(series.notna().sum())
        str_series = series.astype(str).str.strip()
        str_val = str(val).strip()
        return int((str_series.str.upper() != str_val.upper()).sum())

    elif op == "contains":
        return int(series.astype(str).str.contains(str(val), case=False, na=False).sum())

    elif op == "in" and isinstance(val, (list, tuple, set)):
        val_set = {str(v).strip().upper() for v in val}
        return int(series.astype(str).str.strip().str.upper().isin(val_set).sum())

    elif op in (">", ">=", "<", "<="):
        num_series = pd.to_numeric(series, errors="coerce")
        try:
            num_val = float(val)
            if op == ">":
                return int((num_series > num_val).sum())
            elif op == ">=":
                return int((num_series >= num_val).sum())
            elif op == "<":
                return int((num_series < num_val).sum())
            elif op == "<=":
                return int((num_series <= num_val).sum())
        except Exception:
            pass

    return 0


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


def _compute_overall(df: pd.DataFrame, op: str, col: Optional[str]) -> Any:
    """Aggregate of the whole filtered frame (not per group)."""
    if op == "count_distinct":
        return int(df[col].nunique()) if col and col in df.columns else None
    if op == "count" and not col:
        return int(len(df))
    return _compute_scalar(df, op, col)


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
    filter_phrase = ""
    if spec.filters:
        f_parts = []
        for f in spec.filters:
            fc = f.column if hasattr(f, 'column') else f.get('column')
            fv = f.value if hasattr(f, 'value') else f.get('value')
            f_parts.append(f"{fc} = {fv}")
        if f_parts:
            filter_phrase = f" for **{' and '.join(f_parts)}**"
    summary_text = f"Breakdown of {metric_desc} grouped by **{group_str}**{filter_phrase}{limit_desc} ({len(records)} groups found):"

    return records, {"headers": headers, "rows": rows}, summary_text


def _apply_filters(df: pd.DataFrame, filters: List[Any], resolve_col_fn,
                   trace: Optional[List[Dict[str, Any]]] = None) -> pd.DataFrame:
    """Applies filter criteria to DataFrame safely with strict zero-match and column checks."""
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
            raise ColumnNotFoundError(f"The dataset does not contain a field corresponding to '{col_raw}'.")

        series = df[col]
        is_date = _is_date_filter(series, val)
        norm_op = str(op).lower().strip()

        if norm_op in ("=", "==", "equals", "eq", "is"):
            if is_date:
                df = df[pd.to_datetime(series, errors="coerce") == pd.to_datetime(val)]
            elif pd.api.types.is_numeric_dtype(series) and not isinstance(val, str):
                df = df[series == val]
            elif isinstance(val, (int, float)) and pd.api.types.is_numeric_dtype(series):
                df = df[series == val]
            else:
                str_series = series.astype(str).str.strip().str.lower()
                str_val = str(val).strip().lower()
                df = df[str_series == str_val]

        elif norm_op in ("!=", "<>", "not_equals", "neq", "is_not"):
            if is_date:
                df = df[pd.to_datetime(series, errors="coerce") != pd.to_datetime(val)]
            elif pd.api.types.is_numeric_dtype(series) and not isinstance(val, str):
                df = df[series != val]
            elif isinstance(val, (int, float)) and pd.api.types.is_numeric_dtype(series):
                df = df[series != val]
            else:
                str_series = series.astype(str).str.strip().str.lower()
                str_val = str(val).strip().lower()
                df = df[str_series != str_val]

        elif norm_op in (">", "gt", "greater_than"):
            if is_date:
                df = df[pd.to_datetime(series, errors="coerce") > pd.to_datetime(val)]
            else:
                try:
                    df = df[pd.to_numeric(series, errors="coerce") > float(val)]
                except Exception:
                    df = df[series > val]

        elif norm_op in (">=", "gte", "greater_or_equal", "greater_than_or_equal"):
            if is_date:
                df = df[pd.to_datetime(series, errors="coerce") >= pd.to_datetime(val)]
            else:
                try:
                    df = df[pd.to_numeric(series, errors="coerce") >= float(val)]
                except Exception:
                    df = df[series >= val]

        elif norm_op in ("<", "lt", "less_than"):
            if is_date:
                df = df[pd.to_datetime(series, errors="coerce") < pd.to_datetime(val)]
            else:
                try:
                    df = df[pd.to_numeric(series, errors="coerce") < float(val)]
                except Exception:
                    df = df[series < val]

        elif norm_op in ("<=", "lte", "less_or_equal", "less_than_or_equal"):
            if is_date:
                df = df[pd.to_datetime(series, errors="coerce") <= pd.to_datetime(val)]
            else:
                try:
                    df = df[pd.to_numeric(series, errors="coerce") <= float(val)]
                except Exception:
                    df = df[series <= val]

        elif norm_op in ("between", "range"):
            if isinstance(val, (list, tuple)) and len(val) == 2:
                v1, v2 = val[0], val[1]
                if is_date:
                    dt_s = pd.to_datetime(series, errors="coerce", format="mixed")
                    end = pd.to_datetime(v2)
                    if isinstance(v2, str) and re.fullmatch(r"\s*\d{4}-\d{2}-\d{2}\s*", v2):
                        # A date-only upper bound means "through the end of that day".
                        df = df[(dt_s >= pd.to_datetime(v1)) & (dt_s < end + pd.Timedelta(days=1))]
                    else:
                        df = df[(dt_s >= pd.to_datetime(v1)) & (dt_s <= end)]
                else:
                    try:
                        num_s = pd.to_numeric(series, errors="coerce")
                        df = df[(num_s >= float(v1)) & (num_s <= float(v2))]
                    except Exception:
                        df = df[(series >= v1) & (series <= v2)]

        elif norm_op in ("in", "is_in"):
            if isinstance(val, (list, tuple, set)):
                val_set = {str(v).strip().lower() for v in val}
                df = df[series.astype(str).str.strip().str.lower().isin(val_set)]
            else:
                str_series = series.astype(str).str.strip().str.lower()
                str_val = str(val).strip().lower()
                df = df[str_series == str_val]

        elif norm_op in ("contains", "like"):
            clean_val = str(val).strip()
            df = df[series.astype(str).str.contains(re.escape(clean_val), case=False, na=False)]

        else:
            str_series = series.astype(str).str.strip().str.lower()
            str_val = str(val).strip().lower()
            df = df[str_series == str_val]

        f_dict = {"column": col, "operator": op, "value": val}
        if trace is not None:
            trace.append({"filter": f_dict, "rows_after": len(df)})
        if len(df) == 0:
            raise ZeroMatchError(f"No rows matched {col_raw} = {val}.", filter_spec=f_dict)

    return df


def _is_date_filter(series: pd.Series, val: Any = None) -> bool:
    """Checks if series or value represents date values."""
    if pd.api.types.is_datetime64_any_dtype(series):
        return True
    from .semantics import is_year_series
    if is_year_series(series):
        # Integer year columns (e.g. Year = 2024) are compared numerically, never as timestamps.
        return False
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
