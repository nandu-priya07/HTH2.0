"""
Deterministic Time-Series Trend Engine.
Calculates period-over-period aggregation, percentage changes, trend direction, peaks, and troughs.
"""

from typing import Any, Dict, List, Optional
import re
import pandas as pd
import numpy as np
from .models import QuerySpec, QueryResult, ResponseType


def run_trend_analysis(df: pd.DataFrame, spec: QuerySpec) -> QueryResult:
    """
    Deterministically computes time-series trend statistics for a given metric and time column.
    """
    if df is None or df.empty:
        return QueryResult(
            success=False,
            type=ResponseType.ERROR.value,
            error="Dataset is empty or unavailable."
        )

    # 1. Identify Target Metric Column
    metric_col = spec.column or spec.target_column
    df_col_lower_map = {c.lower(): c for c in df.columns}

    if not metric_col:
        # Find first numeric metric in df
        num_cols = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
        if num_cols:
            metric_col = num_cols[0]
        else:
            return QueryResult(
                success=False,
                type=ResponseType.ERROR.value,
                error="No numeric metric column found for trend analysis."
            )
    else:
        metric_col = df_col_lower_map.get(metric_col.lower(), metric_col)

    if metric_col not in df.columns:
        return QueryResult(
            success=False,
            type=ResponseType.ERROR.value,
            error=f"Metric column '{metric_col}' not found in dataset."
        )

    # 2. Identify Time Column
    time_col = spec.time_column
    if time_col:
        time_col = df_col_lower_map.get(time_col.lower(), time_col)

    if not time_col or time_col not in df.columns:
        # Search for date/time column
        for c in df.columns:
            if pd.api.types.is_datetime64_any_dtype(df[c]) or any(k in c.lower() for k in ("date", "time", "year", "month", "day", "created", "order")):
                time_col = c
                break

    if not time_col or time_col not in df.columns:
        return QueryResult(
            success=False,
            type=ResponseType.ERROR.value,
            error="No valid date/time column found for trend analysis."
        )

    # Prepare DataFrame
    work_df = df.copy()
    if spec.filters:
        for f in spec.filters:
            f_col = f.column if hasattr(f, "column") else f.get("column")
            f_val = f.value if hasattr(f, "value") else f.get("value")
            if f_col and f_col in work_df.columns and f_val is not None:
                work_df = work_df[work_df[f_col].astype(str).str.lower() == str(f_val).lower()]

    if work_df.empty:
        return QueryResult(
            success=False,
            type=ResponseType.ERROR.value,
            error="Filter criteria matched 0 rows."
        )

    # Parse Datetime
    try:
        work_df["_parsed_time"] = pd.to_datetime(work_df[time_col], errors="coerce")
        work_df = work_df.dropna(subset=["_parsed_time"])
    except Exception as e:
        return QueryResult(
            success=False,
            type=ResponseType.ERROR.value,
            error=f"Could not parse date column '{time_col}': {str(e)}"
        )

    if work_df.empty:
        return QueryResult(
            success=False,
            type=ResponseType.ERROR.value,
            error=f"No valid datetime values in column '{time_col}'."
        )

    # Determine Frequency ('M', 'Q', 'Y', 'D')
    freq_str = (spec.frequency or "").lower()
    if "year" in freq_str or "annual" in freq_str:
        freq_code = "YE"
        label_fmt = "%Y"
        freq_name = "year"
    elif "quarter" in freq_str:
        freq_code = "QE"
        label_fmt = "%Y-Q%q"
        freq_name = "quarter"
    elif "day" in freq_str or "daily" in freq_str:
        freq_code = "D"
        label_fmt = "%Y-%m-%d"
        freq_name = "day"
    else:
        freq_code = "ME"
        label_fmt = "%Y-%m"
        freq_name = "month"

    # Aggregation
    work_df["_metric_num"] = pd.to_numeric(work_df[metric_col], errors="coerce").fillna(0)
    
    # Resample
    try:
        resampled = work_df.set_index("_parsed_time")["_metric_num"].resample(freq_code).sum().reset_index()
    except Exception:
        # Fallback if pandas version resample code issue
        resampled = work_df.set_index("_parsed_time")["_metric_num"].resample("M").sum().reset_index()
        freq_name = "month"

    if resampled.empty:
        return QueryResult(
            success=False,
            type=ResponseType.ERROR.value,
            error="Trend aggregation returned empty series."
        )

    resampled = resampled.sort_values("_parsed_time")
    
    # Format periods
    if freq_name == "year":
        resampled["period"] = resampled["_parsed_time"].dt.strftime("%Y")
    elif freq_name == "quarter":
        resampled["period"] = resampled["_parsed_time"].dt.to_period("Q").astype(str)
    elif freq_name == "day":
        resampled["period"] = resampled["_parsed_time"].dt.strftime("%Y-%m-%d")
    else:
        resampled["period"] = resampled["_parsed_time"].dt.strftime("%Y-%m")

    resampled["value"] = resampled["_metric_num"].round(2)
    resampled["change"] = resampled["value"].diff().fillna(0.0).round(2)
    resampled["pct_change"] = (resampled["value"].pct_change().fillna(0.0) * 100).round(2)

    series_list = []
    for _, r in resampled.iterrows():
        series_list.append({
            "period": str(r["period"]),
            "value": float(r["value"]),
            "change": float(r["change"]),
            "pct_change": float(r["pct_change"])
        })

    vals = resampled["value"].values
    n = len(vals)
    peak_idx = int(np.argmax(vals))
    trough_idx = int(np.argmin(vals))

    peak = {"period": str(resampled.iloc[peak_idx]["period"]), "value": float(vals[peak_idx])}
    trough = {"period": str(resampled.iloc[trough_idx]["period"]), "value": float(vals[trough_idx])}

    # Direction detection
    if n >= 2:
        x = np.arange(n)
        slope, _ = np.polyfit(x, vals, 1)
        net_pct = ((vals[-1] - vals[0]) / (vals[0] if vals[0] != 0 else 1)) * 100
        if slope > 0 and net_pct > 5:
            direction = "increasing"
        elif slope < 0 and net_pct < -5:
            direction = "decreasing"
        elif np.std(vals) / (np.mean(vals) if np.mean(vals) != 0 else 1) < 0.1:
            direction = "stable"
        else:
            direction = "fluctuating"
    else:
        direction = "stable"

    canonical = {
        "intent": "trend",
        "metric": metric_col,
        "time_column": time_col,
        "frequency": freq_name,
        "series": series_list,
        "growth": [s["pct_change"] for s in series_list],
        "trend_direction": direction,
        "peak": peak,
        "trough": trough,
        "total_periods": n,
        "start_period": series_list[0]["period"] if series_list else "",
        "end_period": series_list[-1]["period"] if series_list else ""
    }

    # Table for UI rendering
    table_rows = [[s["period"], f"${s['value']:,.2f}" if "profit" in metric_col.lower() or "sales" in metric_col.lower() else f"{s['value']:,.2f}", f"{s['change']:+,.2f}", f"{s['pct_change']:+.2f}%"] for s in series_list]
    table = {
        "headers": ["Period", f"{metric_col.title()}", "Change", "% Change"],
        "rows": table_rows
    }

    text_summary = (
        f"The {metric_col} trend across {n} {freq_name}s is {direction}. "
        f"Peak occurred in {peak['period']} ({peak['value']:,.2f}) and trough in {trough['period']} ({trough['value']:,.2f})."
    )

    return QueryResult(
        success=True,
        type=ResponseType.DATA_RESULT.value,
        query=spec.to_dict(),
        result=canonical,
        table=table,
        text=text_summary,
        canonical_data=canonical,
        trend_data=canonical,
        fields_used=[metric_col, time_col],
        metadata={
            "rows_analyzed": len(work_df),
            "trend_direction": direction
        }
    )
