"""
Dynamic, schema-agnostic insight generation engine for QueryLens.
Analyzes an uploaded dataset's DataFrame, schema, and profile to produce:
1. Dynamic metric summaries (sum, mean, median, min, max, range, std)
2. Dynamic categorical distributions & dominant frequencies
3. Cross-column comparisons (highest metric by category, share of total)
4. Time-series trends & peak periods (strictly when date columns exist)
5. Statistical anomaly detection (IQR fences on actual dataset records)
6. Calculation evidence for every card
"""

import math
import logging
from typing import Dict, Any, List, Optional
import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)


def _safe_val(v: Any) -> Any:
    if v is None or pd.isna(v):
        return None
    if isinstance(v, (np.floating, float)):
        if math.isnan(v) or math.isinf(v):
            return None
        return round(float(v), 2)
    if isinstance(v, (np.integer, int)):
        return int(v)
    return str(v)


def _format_num(v: Optional[float]) -> str:
    if v is None:
        return "—"
    abs_v = abs(v)
    if abs_v >= 1_000_000:
        return f"{v / 1_000_000:.2f}M"
    if abs_v >= 1_000:
        return f"{v:,.2f}"
    if isinstance(v, float):
        return f"{v:.2f}"
    return f"{v:,}"


def generate_dataset_insights(
    df: Optional[pd.DataFrame],
    schema: Dict[str, Any],
    profile: Dict[str, Any],
    dataset_id: str
) -> Dict[str, Any]:
    """
    Produces complete, dynamic, schema-agnostic analytical insights for any dataset.
    Never hardcodes column names or sample figures.
    """
    total_rows = int(schema.get("row_count") or (len(df) if df is not None else 0))
    total_cols = int(schema.get("column_count") or (len(df.columns) if df is not None else 0))

    numeric_cols = list(schema.get("numeric_columns") or [])
    categorical_cols = list(schema.get("categorical_columns") or [])
    date_cols = list(schema.get("date_columns") or [])
    identifier_cols = list(schema.get("identifier_columns") or [])

    col_profiles = {c["name"]: c for c in profile.get("columns", [])}

    # -------------------------------------------------------------
    # 1. Dynamic Metric Highlights (Numeric)
    # -------------------------------------------------------------
    metrics = []
    for col in numeric_cols[:4]:
        prof = col_profiles.get(col, {})
        stats = prof.get("statistics")
        if not stats and df is not None and col in df.columns:
            s = pd.to_numeric(df[col], errors="coerce").dropna()
            if len(s) > 0:
                stats = {
                    "count": int(len(s)),
                    "mean": float(s.mean()),
                    "median": float(s.median()),
                    "min": float(s.min()),
                    "max": float(s.max()),
                    "std": float(s.std()) if len(s) > 1 else 0.0,
                    "sum": float(s.sum())
                }

        if stats and stats.get("count", 0) > 0:
            sum_val = _safe_val(stats.get("sum"))
            mean_val = _safe_val(stats.get("mean"))
            min_val = _safe_val(stats.get("min"))
            max_val = _safe_val(stats.get("max"))
            median_val = _safe_val(stats.get("median"))
            std_val = _safe_val(stats.get("std"))

            metrics.append({
                "id": f"metric_{col}",
                "column": col,
                "label": f"Total · {col}",
                "metric_display": _format_num(sum_val),
                "sum": sum_val,
                "mean": mean_val,
                "median": median_val,
                "min": min_val,
                "max": max_val,
                "std": std_val,
                "count": stats.get("count"),
                "explanation": f"Mean {_format_num(mean_val)} · range {_format_num(min_val)} – {_format_num(max_val)}",
                "evidence": {
                    "fields": [col],
                    "rows": total_rows,
                    "filteredRows": stats.get("count"),
                    "aggregation": "SUM",
                    "transformation": f"Aggregated {col} across {stats.get('count', total_rows):,} non-null rows"
                }
            })

    # -------------------------------------------------------------
    # 2. Dynamic Categorical Highlights
    # -------------------------------------------------------------
    categoricals = []
    for col in categorical_cols[:4]:
        prof = col_profiles.get(col, {})
        top_values = prof.get("top_values")
        if not top_values and df is not None and col in df.columns:
            vc = df[col].dropna().astype(str).value_counts().head(5)
            top_values = [{"value": str(k), "count": int(v)} for k, v in vc.items()]

        if top_values and len(top_values) > 0:
            top_item = top_values[0]
            top_val_str = str(top_item["value"])
            top_count = int(top_item["count"])
            pct = round((top_count / total_rows) * 100, 1) if total_rows > 0 else 0

            dist_labels = [str(t["value"])[:12] for t in top_values]
            dist_data = [int(t["count"]) for t in top_values]

            categoricals.append({
                "id": f"cat_{col}",
                "column": col,
                "label": f"Most frequent · {col}",
                "top_value": top_val_str,
                "count": top_count,
                "percentage": pct,
                "explanation": f"{top_count:,} of {total_rows:,} rows ({pct}%)",
                "distribution_labels": dist_labels,
                "distribution_data": dist_data,
                "evidence": {
                    "fields": [col],
                    "rows": total_rows,
                    "aggregation": "COUNT / FREQUENCY",
                    "transformation": f"Count of occurrences in {col}, top value '{top_val_str}'"
                }
            })

    # -------------------------------------------------------------
    # 3. Dynamic Automated Insights Cards
    # -------------------------------------------------------------
    automated_insights = []

    # A. Cross-column comparison: Highest numeric metric by category
    if df is not None and len(categorical_cols) > 0 and len(numeric_cols) > 0:
        # Choose the best categorical dimension and numeric measure
        for cat_cand in categorical_cols[:2]:
            for num_cand in numeric_cols[:2]:
                if cat_cand in df.columns and num_cand in df.columns:
                    try:
                        clean_df = df[[cat_cand, num_cand]].dropna()
                        if len(clean_df) > 0:
                            clean_df[num_cand] = pd.to_numeric(clean_df[num_cand], errors="coerce")
                            clean_df = clean_df.dropna()
                            grouped = clean_df.groupby(cat_cand)[num_cand].sum().sort_values(ascending=False).head(5)
                            total_grp_sum = float(clean_df[num_cand].sum())
                            if len(grouped) > 1 and total_grp_sum > 0:
                                top_cat_name = str(grouped.index[0])
                                top_cat_val = float(grouped.iloc[0])
                                top_cat_share = round((top_cat_val / total_grp_sum) * 100, 1)

                                automated_insights.append({
                                    "id": f"compare_{cat_cand}_{num_cand}",
                                    "type": "comparison",
                                    "title": f"Top Performing {cat_cand.replace('_', ' ').title()}",
                                    "metric": top_cat_name,
                                    "change": f"{top_cat_share}% share",
                                    "direction": "up",
                                    "explanation": f"{top_cat_name} contributes the largest share of total {num_cand.replace('_', ' ')} ({_format_num(top_cat_val)}).",
                                    "visual": "bars",
                                    "data": [round(float(v), 2) for v in grouped.values],
                                    "labels": [str(l)[:12] for l in grouped.index],
                                    "evidence": {
                                        "fields": [num_cand, cat_cand],
                                        "rows": total_rows,
                                        "filteredRows": len(clean_df),
                                        "aggregation": "SUM",
                                        "transformation": f"SUM({num_cand}) GROUP BY {cat_cand} ORDER BY SUM({num_cand}) DESC"
                                    }
                                })
                                break
                    except Exception as e:
                        logger.warning(f"Failed cross-column comparison for {cat_cand}, {num_cand}: {e}")
            if len(automated_insights) >= 2:
                break

    # B. Second comparison or Average metric by category
    if df is not None and len(categorical_cols) > 0 and len(numeric_cols) > 0 and len(automated_insights) < 2:
        cat_cand = categorical_cols[0]
        num_cand = numeric_cols[0]
        try:
            clean_df = df[[cat_cand, num_cand]].dropna()
            clean_df[num_cand] = pd.to_numeric(clean_df[num_cand], errors="coerce")
            clean_df = clean_df.dropna()
            avg_grp = clean_df.groupby(cat_cand)[num_cand].mean().sort_values(ascending=False).head(5)
            if len(avg_grp) > 1:
                top_name = str(avg_grp.index[0])
                top_avg = float(avg_grp.iloc[0])
                automated_insights.append({
                    "id": f"avg_{cat_cand}_{num_cand}",
                    "type": "comparison",
                    "title": f"Highest Average {num_cand.replace('_', ' ').title()}",
                    "metric": top_name,
                    "change": f"{_format_num(top_avg)} avg",
                    "direction": "up",
                    "explanation": f"{top_name} leads with the highest average {num_cand.replace('_', ' ')} per record.",
                    "visual": "bars",
                    "data": [round(float(v), 2) for v in avg_grp.values],
                    "labels": [str(l)[:12] for l in avg_grp.index],
                    "evidence": {
                        "fields": [num_cand, cat_cand],
                        "rows": total_rows,
                        "filteredRows": len(clean_df),
                        "aggregation": "AVG",
                        "transformation": f"AVG({num_cand}) GROUP BY {cat_cand} ORDER BY AVG({num_cand}) DESC"
                    }
                })
        except Exception as e:
            logger.warning(f"Failed avg comparison: {e}")

    # C. Time-Series Trend & Peak Period (STRICTLY when date column exists)
    has_date_trend = False
    if df is not None and len(date_cols) > 0 and len(numeric_cols) > 0:
        date_col = date_cols[0]
        num_col = numeric_cols[0]
        try:
            tdf = df[[date_col, num_col]].dropna().copy()
            tdf[num_col] = pd.to_numeric(tdf[num_col], errors="coerce")
            tdf = tdf.dropna()
            tdf["dt"] = pd.to_datetime(tdf[date_col], errors="coerce", format="mixed")
            tdf = tdf.dropna(subset=["dt"])

            if len(tdf) >= 4:
                # Group by period
                span_days = (tdf["dt"].max() - tdf["dt"].min()).days
                if span_days > 90:
                    ts = tdf.set_index("dt").resample("ME")[num_col].sum()
                elif span_days > 14:
                    ts = tdf.set_index("dt").resample("W")[num_col].sum()
                else:
                    ts = tdf.set_index("dt").resample("D")[num_col].sum()

                ts = ts[ts > 0]
                if len(ts) >= 3:
                    ts_values = [round(float(v), 2) for v in ts.values]
                    start_val = ts_values[0] if ts_values[0] > 0 else 1
                    end_val = ts_values[-1]
                    pct_change = round(((end_val - start_val) / start_val) * 100, 1)
                    direction = "up" if pct_change > 0 else "alert" if pct_change < 0 else "flat"
                    change_str = f"{'+' if pct_change > 0 else ''}{pct_change}%"

                    total_series_sum = sum(ts_values)

                    automated_insights.append({
                        "id": f"trend_{num_col}",
                        "type": "trend",
                        "title": f"{num_col.replace('_', ' ').title()} Trend",
                        "metric": _format_num(total_series_sum),
                        "change": change_str,
                        "direction": direction,
                        "explanation": f"Observed over {len(ts_values)} periods across {date_col.replace('_', ' ')}.",
                        "visual": "spark",
                        "data": ts_values,
                        "evidence": {
                            "fields": [num_col, date_col],
                            "rows": total_rows,
                            "filteredRows": len(tdf),
                            "aggregation": "SUM / RESAMPLE",
                            "transformation": f"SUM({num_col}) GROUP BY Time Period on {date_col}"
                        }
                    })

                    # Peak period card
                    peak_idx = int(np.argmax(ts.values))
                    peak_period_name = str(ts.index[peak_idx].strftime("%b %Y" if span_days > 90 else "%Y-%m-%d"))
                    peak_val = float(ts.values[peak_idx])
                    avg_val = float(np.mean(ts.values))
                    uplift = round(((peak_val - avg_val) / avg_val) * 100, 1) if avg_val > 0 else 0

                    automated_insights.append({
                        "id": f"peak_{num_col}",
                        "type": "peak",
                        "title": "Peak Activity Period",
                        "metric": peak_period_name,
                        "change": f"+{uplift}% vs avg",
                        "direction": "up",
                        "explanation": f"Highest recorded {num_col.replace('_', ' ')} ({_format_num(peak_val)}) occurred in {peak_period_name}.",
                        "visual": "bars",
                        "data": ts_values[-6:],
                        "labels": [str(d.strftime("%b" if span_days > 90 else "%d")) for d in ts.index[-6:]],
                        "evidence": {
                            "fields": [num_col, date_col],
                            "rows": total_rows,
                            "filteredRows": len(tdf),
                            "aggregation": "MAX / PEAK",
                            "transformation": f"Identified maximum period on {date_col}"
                        }
                    })
                    has_date_trend = True
        except Exception as e:
            logger.warning(f"Failed time-series trend calculation: {e}")

    # D. Categorical Dominance / Concentration (if a category value holds >= 40% share)
    if df is not None and len(categorical_cols) > 0 and len(automated_insights) < 4:
        for cat_cand in categorical_cols:
            prof = col_profiles.get(cat_cand, {})
            top_vals = prof.get("top_values") or []
            if top_vals and len(top_vals) > 1:
                top_c = top_vals[0]
                share = round((top_c["count"] / total_rows) * 100, 1) if total_rows > 0 else 0
                if share >= 35.0:
                    automated_insights.append({
                        "id": f"dominance_{cat_cand}",
                        "type": "distribution",
                        "title": f"{cat_cand.replace('_', ' ').title()} Concentration",
                        "metric": str(top_c["value"]),
                        "change": f"{share}% share",
                        "direction": "flat",
                        "explanation": f"'{top_c['value']}' represents {share}% of all records in {cat_cand.replace('_', ' ')}.",
                        "visual": "bars",
                        "data": [t["count"] for t in top_vals[:4]],
                        "labels": [str(t["value"])[:12] for t in top_vals[:4]],
                        "evidence": {
                            "fields": [cat_cand],
                            "rows": total_rows,
                            "aggregation": "PERCENTILE SHARE",
                            "transformation": f"Count frequency proportion in {cat_cand}"
                        }
                    })
                    break

    # -------------------------------------------------------------
    # 4. Statistical Anomaly Detection (IQR on numeric columns)
    # -------------------------------------------------------------
    anomalies_list = []
    total_anomaly_count = 0
    anomaly_col = None

    if df is not None and len(numeric_cols) > 0 and total_rows >= 10:
        # Check primary numeric columns for outliers
        for num_col in numeric_cols:
            try:
                s = pd.to_numeric(df[num_col], errors="coerce").dropna()
                if len(s) >= 10:
                    q1 = float(s.quantile(0.25))
                    q3 = float(s.quantile(0.75))
                    iqr = q3 - q1
                    if iqr > 0:
                        upper_fence = q3 + 1.5 * iqr
                        extreme_fence = q3 + 3.0 * iqr

                        outlier_mask = df[num_col] > upper_fence
                        outliers = df[outlier_mask].sort_values(num_col, ascending=False)
                        count = len(outliers)

                        if count > 0:
                            total_anomaly_count = count
                            anomaly_col = num_col

                            # Pick best identifier column
                            id_col = None
                            for idc in identifier_cols:
                                if idc in df.columns:
                                    id_col = idc
                                    break

                            # Build table records
                            for idx, row in outliers.head(8).iterrows():
                                rec_name = str(row[id_col]) if id_col and pd.notna(row.get(id_col)) else f"Row #{idx + 1}"
                                val_num = float(row[num_col])
                                sev = "High" if val_num > extreme_fence else "Medium"
                                reason = f"Unusually high {num_col.replace('_', ' ')}"
                                anomalies_list.append({
                                    "record": rec_name,
                                    "reason": reason,
                                    "severity": sev,
                                    "value": f"{num_col}: {_format_num(val_num)}"
                                })
                            break
            except Exception as e:
                logger.warning(f"Error checking anomalies on {num_col}: {e}")

    # Add Anomaly summary card to automated_insights if anomalies found
    if total_anomaly_count > 0 and anomaly_col:
        automated_insights.append({
            "id": "anomaly_summary",
            "type": "anomaly",
            "title": "Potential Anomaly",
            "metric": f"{total_anomaly_count} records",
            "change": "Review",
            "direction": "alert",
            "explanation": f"{total_anomaly_count:,} records in '{anomaly_col}' sit significantly above the typical distribution.",
            "visual": "spark",
            "data": [round(float(a["value"].split(": ")[-1].replace(",", "").replace("M", "")), 1) if ":" in a["value"] else 10 for a in anomalies_list[:8]],
            "evidence": {
                "fields": [anomaly_col] + (identifier_cols[:1] if identifier_cols else []),
                "rows": total_rows,
                "filteredRows": total_anomaly_count,
                "aggregation": "IQR Outlier Check",
                "transformation": f"Per-record comparison against 1.5× IQR upper fence on {anomaly_col}"
            }
        })

    return {
        "dataset_id": dataset_id,
        "row_count": total_rows,
        "column_count": total_cols,
        "numeric_columns": numeric_cols,
        "categorical_columns": categorical_cols,
        "date_columns": date_cols,
        "identifier_columns": identifier_cols,
        "metrics": metrics,
        "categoricals": categoricals,
        "automated_insights": automated_insights,
        "anomalies": anomalies_list,
        "total_anomalies": total_anomaly_count,
        "has_date": len(date_cols) > 0,
        "has_numeric": len(numeric_cols) > 0,
        "has_categorical": len(categorical_cols) > 0
    }
