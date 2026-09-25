"""
Deterministic Statistical Anomaly Detection Engine.
Detects statistical outliers using Z-Score or IQR criteria.
"""

from typing import Any, Dict, List, Optional
import pandas as pd
import numpy as np
from .models import QuerySpec, QueryResult, ResponseType


def run_anomaly_detection(df: pd.DataFrame, spec: QuerySpec) -> QueryResult:
    """
    Executes statistical anomaly detection over time-series or categorical aggregations.
    """
    if df is None or df.empty:
        return QueryResult(
            success=False,
            type=ResponseType.ERROR.value,
            error="Dataset is empty or unavailable."
        )

    # 1. Target Metric
    metric_col = spec.column or spec.target_column
    df_col_lower_map = {c.lower(): c for c in df.columns}

    if not metric_col:
        num_cols = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
        if num_cols:
            metric_col = num_cols[0]
        else:
            return QueryResult(
                success=False,
                type=ResponseType.ERROR.value,
                error="No numeric metric column found for anomaly detection."
            )
    else:
        metric_col = df_col_lower_map.get(metric_col.lower(), metric_col)

    if metric_col not in df.columns:
        return QueryResult(
            success=False,
            type=ResponseType.ERROR.value,
            error=f"Metric column '{metric_col}' not found in dataset."
        )

    work_df = df.copy()
    work_df["_metric_num"] = pd.to_numeric(work_df[metric_col], errors="coerce")
    work_df = work_df.dropna(subset=["_metric_num"])

    if work_df.empty:
        return QueryResult(
            success=False,
            type=ResponseType.ERROR.value,
            error=f"No valid numeric data in column '{metric_col}'."
        )

    # 2. Check if Time aggregation or Categorical Grouping
    time_col = spec.time_column
    if not time_col:
        for c in df.columns:
            if pd.api.types.is_datetime64_any_dtype(df[c]) or any(k in c.lower() for k in ("date", "time", "year", "month", "day", "created", "order")):
                time_col = c
                break

    if time_col and time_col in work_df.columns:
        work_df["_parsed_time"] = pd.to_datetime(work_df[time_col], errors="coerce")
        work_df = work_df.dropna(subset=["_parsed_time"])
        grouped = work_df.set_index("_parsed_time")["_metric_num"].resample("ME").sum().reset_index()
        grouped["dimension"] = grouped["_parsed_time"].dt.strftime("%Y-%m")
    elif spec.group_by and spec.group_by[0] in work_df.columns:
        g_col = spec.group_by[0]
        grouped = work_df.groupby(g_col)["_metric_num"].sum().reset_index()
        grouped["dimension"] = grouped[g_col].astype(str)
    else:
        # Check by row index
        grouped = work_df.reset_index()
        grouped["dimension"] = grouped["index"].apply(lambda i: f"Row #{i+1}")

    vals = grouped["_metric_num"].values
    if len(vals) < 3:
        return QueryResult(
            success=False,
            type=ResponseType.ERROR.value,
            error="Insufficient data points for statistical anomaly detection (minimum 3 required)."
        )

    mean_val = float(np.mean(vals))
    std_val = float(np.std(vals)) if len(vals) > 1 else 1.0
    if std_val == 0.0:
        std_val = 1.0

    anomalies_list = []
    for _, row in grouped.iterrows():
        val = float(row["_metric_num"])
        z_score = (val - mean_val) / std_val
        abs_z = abs(z_score)

        if abs_z >= 2.0:
            if abs_z >= 3.0:
                severity = "Critical"
            elif abs_z >= 2.5:
                severity = "High"
            else:
                severity = "Moderate"

            anomalies_list.append({
                "period": str(row["dimension"]),
                "value": round(val, 2),
                "expected": round(mean_val, 2),
                "deviation": round(val - mean_val, 2),
                "z_score": round(z_score, 2),
                "severity": severity
            })

    # Sort anomalies by z_score absolute severity
    anomalies_list.sort(key=lambda x: abs(x["z_score"]), reverse=True)

    canonical = {
        "intent": "anomaly_detection",
        "metric": metric_col,
        "baseline_mean": round(mean_val, 2),
        "baseline_std": round(std_val, 2),
        "threshold": "Z-Score >= 2.0",
        "anomalies_count": len(anomalies_list),
        "anomalies": anomalies_list
    }

    if anomalies_list:
        table_rows = [[a["period"], f"{a['value']:,.2f}", f"{a['expected']:,.2f}", f"{a['deviation']:+,.2f}", f"{a['z_score']:+.2f}", a["severity"]] for a in anomalies_list]
    else:
        table_rows = [["No anomalies detected", "-", f"Mean: {mean_val:,.2f}", "-", "0.00", "Normal"]]

    table = {
        "headers": ["Entity / Period", f"Actual {metric_col.title()}", "Expected Mean", "Deviation", "Z-Score", "Severity"],
        "rows": table_rows
    }

    if anomalies_list:
        text_summary = f"Detected {len(anomalies_list)} anomalous values in {metric_col} (|Z-Score| >= 2.0). Highest severity: {anomalies_list[0]['period']} ({anomalies_list[0]['value']:,.2f})."
    else:
        text_summary = f"No statistical anomalies detected in {metric_col} (all values within 2 standard deviations of mean {mean_val:,.2f})."

    return QueryResult(
        success=True,
        type=ResponseType.DATA_RESULT.value,
        query=spec.to_dict(),
        result=canonical,
        table=table,
        text=text_summary,
        canonical_data=canonical,
        anomaly_data=canonical,
        fields_used=[metric_col],
        metadata={
            "anomalies_count": len(anomalies_list),
            "threshold": "Z-Score >= 2.0"
        }
    )
