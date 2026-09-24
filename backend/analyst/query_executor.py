"""
Analytics Executor module.
Executes validated QuerySpec objects strictly against Pandas DataFrames.
Decoupled from natural language parsing, semantic rules, and dataset schemas.
"""

from pathlib import Path
from typing import Any, Dict, List, Optional, Union
import numpy as np
import pandas as pd

from .query_types import (
    QuerySpec,
    QueryResult,
    QueryStatus,
    ResultType,
    FilterSpec,
    SortSpec
)
from .query_errors import ErrorCode, AnalystError


def execute_query(
    query_spec: Union[QuerySpec, Dict[str, Any]],
    dataframe: pd.DataFrame,
    # Backward compatibility arguments
    semantic_model: Optional[Any] = None,
    semantic_embeddings: Optional[Any] = None
) -> QueryResult:
    """
    Executes a validated QuerySpec against a Pandas DataFrame.
    Returns structured QueryResult without natural-language text.
    """
    if isinstance(query_spec, dict):
        spec = QuerySpec(**query_spec)
    else:
        spec = query_spec

    if spec.status != QueryStatus.VALID:
        return QueryResult(
            success=False,
            result_type=ResultType.ERROR.value,
            error={
                "code": spec.error.get("code") if isinstance(spec.error, dict) else (spec.error.code if spec.error else ErrorCode.QUERY_VALIDATION_ERROR),
                "message": spec.message or (spec.error.get("message") if isinstance(spec.error, dict) else (spec.error.message if spec.error else "Query is not in VALID status"))
            }
        )

    if dataframe is None or not isinstance(dataframe, pd.DataFrame):
        return QueryResult(
            success=False,
            result_type=ResultType.ERROR.value,
            error={
                "code": ErrorCode.EXECUTION_ERROR,
                "message": "Input must be a valid Pandas DataFrame."
            }
        )

    total_rows = len(dataframe)
    df = dataframe.copy()

    # Column case-insensitive mapping lookup
    col_map = {c.lower(): c for c in df.columns}

    def _resolve_df_col(name: Optional[str]) -> Optional[str]:
        if not name:
            return None
        if name in df.columns:
            return name
        return col_map.get(name.lower(), name)

    # -------------------------------------------------------------
    # 1. Apply Filters
    # -------------------------------------------------------------
    if spec.filters:
        try:
            df = _apply_filters(df, spec.filters, _resolve_df_col)
        except Exception as e:
            return QueryResult(
                success=False,
                result_type=ResultType.ERROR.value,
                error={
                    "code": ErrorCode.EXECUTION_ERROR,
                    "message": f"Error applying filters: {str(e)}"
                }
            )

    filtered_rows = len(df)
    metric_col = _resolve_df_col(spec.metric)
    group_cols = [_resolve_df_col(g) for g in spec.group_by if _resolve_df_col(g) in df.columns]

    # -------------------------------------------------------------
    # 2. Time Trend Processing
    # -------------------------------------------------------------
    time_col = _resolve_df_col(spec.time_dimension)
    if (spec.operation == "trend" or spec.time_granularity) and time_col in df.columns:
        gran = (spec.time_granularity or "month").lower()
        try:
            dt_series = pd.to_datetime(df[time_col], errors="coerce")
            if gran == "day":
                df["_period"] = dt_series.dt.strftime("%Y-%m-%d")
            elif gran == "week":
                df["_period"] = dt_series.dt.strftime("%Y-W%W")
            elif gran == "month":
                df["_period"] = dt_series.dt.strftime("%Y-%m")
            elif gran == "quarter":
                df["_period"] = dt_series.dt.to_period("Q").astype(str)
            elif gran == "year":
                df["_period"] = dt_series.dt.strftime("%Y")
            else:
                df["_period"] = dt_series.dt.strftime("%Y-%m")

            if "_period" not in group_cols:
                group_cols.insert(0, "_period")
        except Exception as e:
            return QueryResult(
                success=False,
                result_type=ResultType.ERROR.value,
                error={"code": ErrorCode.EXECUTION_ERROR, "message": f"Time trend conversion failed: {str(e)}"}
            )

    # -------------------------------------------------------------
    # 3. Execution: Distinct vs Grouped vs Scalar vs Detail
    # -------------------------------------------------------------
    try:
        # Case Distinct: Return list of unique values
        if spec.operation == "distinct":
            target_col = _resolve_df_col(spec.column or spec.metric)
            if not target_col or target_col not in df.columns:
                return QueryResult(
                    success=False,
                    result_type=ResultType.ERROR.value,
                    error={
                        "code": ErrorCode.COLUMN_NOT_FOUND,
                        "message": f"Column '{spec.column or spec.metric}' was not found in the dataset."
                    }
                )

            distinct_series = df[target_col].dropna().drop_duplicates()
            if spec.sort:
                s_dir = "asc"
                for s in spec.sort:
                    s_dir = (s.get("direction") if isinstance(s, dict) else s.direction) or "asc"
                distinct_series = distinct_series.sort_values(ascending=(str(s_dir).lower() == "asc"))

            if spec.limit and spec.limit > 0:
                distinct_series = distinct_series.head(spec.limit)

            raw_values = distinct_series.tolist()
            values = [_sanitize_scalar(v) for v in raw_values]

            return QueryResult(
                success=True,
                result_type=ResultType.LIST.value,
                column=target_col,
                values=values,
                count=len(values),
                columns=[target_col],
                rows=[[v] for v in values],
                metadata={
                    "rows_analyzed": total_rows,
                    "filtered_rows": filtered_rows,
                    "count": len(values)
                }
            )

        # Case Count Distinct: Scalar count of unique values
        if spec.operation == "count_distinct" or (spec.operation == "count" and spec.aggregation == "count_distinct"):
            target_col = _resolve_df_col(spec.column or spec.metric)
            if target_col and target_col in df.columns:
                val = int(df[target_col].dropna().nunique())
            else:
                val = int(len(df.drop_duplicates()))

            return QueryResult(
                success=True,
                result_type=ResultType.SCALAR.value,
                column=target_col,
                value=val,
                metadata={
                    "rows_analyzed": total_rows,
                    "filtered_rows": filtered_rows
                }
            )

        # Case A: Grouped Aggregation
        if group_cols:
            res_df = _execute_grouped_aggregation(
                df=df,
                group_cols=group_cols,
                metric_col=metric_col,
                operation=spec.operation,
                aggregation=spec.aggregation or "sum"
            )

            # Apply Sorting
            res_df = _apply_sorting(res_df, spec.sort, metric_col)

            # Apply Limit
            if spec.limit and spec.limit > 0:
                res_df = res_df.head(spec.limit)

            # Clean column names (e.g. rename _period back to time_dimension or period)
            rename_map = {"_period": spec.time_dimension or "period"}
            res_df.rename(columns=rename_map, inplace=True)

            # Format rows safely (handling NaN, inf, timestamp)
            columns = list(res_df.columns)
            rows = _sanitize_dataframe_rows(res_df)

            return QueryResult(
                success=True,
                result_type=ResultType.TABLE.value,
                columns=columns,
                rows=rows,
                metadata={
                    "rows_analyzed": total_rows,
                    "filtered_rows": filtered_rows,
                    "row_count": len(rows)
                }
            )

        # Case B: Scalar Aggregation
        if spec.operation in ("aggregation", "count") or (spec.aggregation and metric_col):
            val = _execute_scalar_aggregation(
                df=df,
                metric_col=metric_col,
                operation=spec.operation,
                aggregation=spec.aggregation or "sum"
            )
            return QueryResult(
                success=True,
                result_type=ResultType.SCALAR.value,
                value=val,
                metadata={
                    "rows_analyzed": total_rows,
                    "filtered_rows": filtered_rows
                }
            )

        # Case C: Detail / Filtered rows without aggregation
        res_df = df
        if spec.sort:
            res_df = _apply_sorting(res_df, spec.sort, metric_col)
        if spec.limit and spec.limit > 0:
            res_df = res_df.head(spec.limit)

        columns = list(res_df.columns)
        rows = _sanitize_dataframe_rows(res_df)
        return QueryResult(
            success=True,
            result_type=ResultType.DETAIL.value,
            columns=columns,
            rows=rows,
            metadata={
                "rows_analyzed": total_rows,
                "filtered_rows": filtered_rows,
                "row_count": len(rows)
            }
        )

    except Exception as e:
        return QueryResult(
            success=False,
            result_type=ResultType.ERROR.value,
            error={
                "code": ErrorCode.EXECUTION_ERROR,
                "message": f"Execution error: {str(e)}"
            }
        )


def _apply_filters(df: pd.DataFrame, filters: List[Any], resolve_col_fn) -> pd.DataFrame:
    """Applies filter specifications to dataframe."""
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
        if col not in df.columns:
            continue

        series = df[col]

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
            if _is_date_filter(series, val):
                df = df[pd.to_datetime(series, errors="coerce") > pd.to_datetime(val)]
            else:
                try:
                    df = df[pd.to_numeric(series, errors="coerce") > float(val)]
                except Exception:
                    df = df[series > val]
        elif op == ">=":
            if _is_date_filter(series, val):
                df = df[pd.to_datetime(series, errors="coerce") >= pd.to_datetime(val)]
            else:
                try:
                    df = df[pd.to_numeric(series, errors="coerce") >= float(val)]
                except Exception:
                    df = df[series >= val]
        elif op == "<":
            if _is_date_filter(series, val):
                df = df[pd.to_datetime(series, errors="coerce") < pd.to_datetime(val)]
            else:
                try:
                    df = df[pd.to_numeric(series, errors="coerce") < float(val)]
                except Exception:
                    df = df[series < val]
        elif op == "<=":
            if _is_date_filter(series, val):
                df = df[pd.to_datetime(series, errors="coerce") <= pd.to_datetime(val)]
            else:
                try:
                    df = df[pd.to_numeric(series, errors="coerce") <= float(val)]
                except Exception:
                    df = df[series <= val]
        elif op == "contains":
            df = df[series.astype(str).str.contains(str(val), case=False, na=False)]
        elif op == "starts_with":
            df = df[series.astype(str).str.lower().str.startswith(str(val).lower(), na=False)]
        elif op == "ends_with":
            df = df[series.astype(str).str.lower().str.endswith(str(val).lower(), na=False)]
        elif op == "in":
            if isinstance(val, (list, tuple, set)):
                val_set = {str(v).lower() for v in val}
                df = df[series.astype(str).str.lower().isin(val_set)]
            else:
                df = df[series == val]
        elif op == "not_in":
            if isinstance(val, (list, tuple, set)):
                val_set = {str(v).lower() for v in val}
                df = df[~series.astype(str).str.lower().isin(val_set)]
            else:
                df = df[series != val]
        elif op == "between":
            if isinstance(val, (list, tuple)) and len(val) == 2:
                v1, v2 = val[0], val[1]
                if _is_date_filter(series, val):
                    dt_s = pd.to_datetime(series, errors="coerce")
                    df = df[(dt_s >= pd.to_datetime(v1)) & (dt_s <= pd.to_datetime(v2))]
                else:
                    try:
                        num_s = pd.to_numeric(series, errors="coerce")
                        df = df[(num_s >= float(v1)) & (num_s <= float(v2))]
                    except Exception:
                        df = df[(series >= v1) & (series <= v2)]
    return df


def _is_date_filter(series: pd.Series, val: Any = None) -> bool:
    """Checks if a series or filter value indicates datetime comparison."""
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


def _execute_scalar_aggregation(
    df: pd.DataFrame,
    metric_col: Optional[str],
    operation: str,
    aggregation: str
) -> Any:
    """Calculates a single scalar aggregation value."""
    if len(df) == 0:
        return 0

    agg = aggregation.lower()

    if agg == "count_distinct" and metric_col:
        return int(df[metric_col].nunique())

    if operation == "count" or agg == "count":
        if metric_col:
            return int(df[metric_col].count())
        return int(len(df))

    if not metric_col or metric_col not in df.columns:
        return int(len(df))

    series = pd.to_numeric(df[metric_col], errors="coerce").dropna()
    if len(series) == 0:
        return 0

    if agg == "sum":
        val = series.sum()
    elif agg in ("mean", "average"):
        val = series.mean()
    elif agg == "min":
        val = series.min()
    elif agg == "max":
        val = series.max()
    elif agg == "median":
        val = series.median()
    else:
        val = series.sum()

    if isinstance(val, (float, np.floating)):
        return round(float(val), 4)
    if isinstance(val, (int, np.integer)):
        return int(val)
    return val


def _execute_grouped_aggregation(
    df: pd.DataFrame,
    group_cols: List[str],
    metric_col: Optional[str],
    operation: str,
    aggregation: str
) -> pd.DataFrame:
    """Executes groupby aggregation on specified dimensions."""
    agg = aggregation.lower()

    if len(df) == 0:
        cols = list(group_cols) + ["value"]
        return pd.DataFrame(columns=cols)

    if operation == "count" and not metric_col:
        res = df.groupby(group_cols, as_index=False).size()
        res.rename(columns={"size": "value"}, inplace=True)
        return res

    if agg == "count_distinct" and metric_col:
        res = df.groupby(group_cols, as_index=False)[metric_col].nunique()
        res.rename(columns={metric_col: "value"}, inplace=True)
        return res

    if metric_col and metric_col in df.columns:
        # Ensure metric is numeric for numeric aggregations
        if agg in ("sum", "mean", "average", "median"):
            df[metric_col] = pd.to_numeric(df[metric_col], errors="coerce")

        agg_map = {
            "sum": "sum",
            "mean": "mean",
            "average": "mean",
            "min": "min",
            "max": "max",
            "median": "median",
            "count": "count"
        }
        fn = agg_map.get(agg, "sum")
        res = df.groupby(group_cols, as_index=False)[metric_col].agg(fn)
        res.rename(columns={metric_col: "value"}, inplace=True)
        if pd.api.types.is_float_dtype(res["value"]):
            res["value"] = res["value"].round(4)
        return res

    # Fallback to row counts
    res = df.groupby(group_cols, as_index=False).size()
    res.rename(columns={"size": "value"}, inplace=True)
    return res


def _apply_sorting(
    df: pd.DataFrame,
    sort_specs: List[Any],
    metric_col: Optional[str]
) -> pd.DataFrame:
    """Applies sort specifications to dataframe."""
    if not sort_specs:
        if "value" in df.columns:
            return df.sort_values(by="value", ascending=False).reset_index(drop=True)
        return df

    for s in sort_specs:
        if isinstance(s, dict):
            s_col = s.get("column", "value")
            s_dir = s.get("direction", "desc")
        else:
            s_col = s.column
            s_dir = s.direction

        target_col = "value"
        if s_col in df.columns:
            target_col = s_col
        elif metric_col in df.columns and s_col == metric_col:
            target_col = "value" if "value" in df.columns else metric_col

        if target_col in df.columns:
            df = df.sort_values(by=target_col, ascending=(s_dir.lower() == "asc")).reset_index(drop=True)

    return df


def _sanitize_scalar(val: Any) -> Any:
    """Converts a scalar value to JSON-serializable Python native type."""
    if pd.isna(val):
        return None
    if isinstance(val, (np.floating, float)):
        return round(float(val), 4)
    if isinstance(val, (np.integer, int)):
        return int(val)
    if isinstance(val, (pd.Timestamp, np.datetime64)):
        return str(val)
    return val


def _sanitize_dataframe_rows(df: pd.DataFrame) -> List[List[Any]]:
    """Converts DataFrame records to JSON-serializable Python native types."""
    rows = []
    for _, record in df.iterrows():
        clean_row = [_sanitize_scalar(val) for val in record]
        rows.append(clean_row)
    return rows


def load_processed_dataset(
    dataset_id: str,
    base_dir: Optional[Union[str, Path]] = None
) -> pd.DataFrame:
    """
    Loads a processed dataset CSV by dataset_id from backend/uploads/processed/.
    """
    if base_dir is None:
        base_dir = Path(__file__).resolve().parent.parent / "uploads" / "processed"
    else:
        base_dir = Path(base_dir)

    target_path = base_dir / f"{dataset_id}.csv"
    if not target_path.exists():
        raise FileNotFoundError(f"Processed dataset not found at {target_path}")

    return pd.read_csv(target_path)
