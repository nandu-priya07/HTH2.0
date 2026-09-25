"""
Deterministic Complex Insight, Contribution, Comparison, and Decision Analysis Engine.
Calculates multi-dimensional comparative metrics, period-over-period contribution to change, and decision matrices.
"""

from typing import Any, Dict, List, Optional, Tuple
import pandas as pd
import numpy as np
from .models import QuerySpec, QueryResult, ResponseType


def run_complex_insight(df: pd.DataFrame, spec: QuerySpec) -> QueryResult:
    """
    Deterministically computes multi-dimensional contribution analysis and underperformance metrics.
    """
    if df is None or df.empty:
        return QueryResult(
            success=False,
            type=ResponseType.ERROR.value,
            error="Dataset is empty or unavailable."
        )

    df_col_lower_map = {c.lower(): c for c in df.columns}

    # Find metric (profit, sales, revenue, etc.)
    metric_col = spec.column or spec.target_column
    if metric_col:
        metric_col = df_col_lower_map.get(metric_col.lower(), metric_col)
    else:
        for m in ("profit", "sales", "revenue", "amount"):
            if m in df_col_lower_map:
                metric_col = df_col_lower_map[m]
                break
        if not metric_col:
            num_cols = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
            metric_col = num_cols[0] if num_cols else df.columns[0]

    # Find candidate dimension (category, region, state, product, segment)
    dim_col = spec.group_by[0] if spec.group_by else None
    if dim_col:
        dim_col = df_col_lower_map.get(dim_col.lower(), dim_col)
    else:
        for d in ("category", "state", "region", "product_name", "segment", "sub_category"):
            if d in df_col_lower_map:
                dim_col = df_col_lower_map[d]
                break

    if not dim_col or dim_col not in df.columns:
        cat_cols = [c for c in df.columns if not pd.api.types.is_numeric_dtype(df[c])]
        dim_col = cat_cols[0] if cat_cols else df.columns[0]

    work_df = df.copy()
    work_df["_metric_num"] = pd.to_numeric(work_df[metric_col], errors="coerce").fillna(0)

    # Check if time column available for Period-over-Period contribution
    time_col = None
    for c in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[c]) or any(k in c.lower() for k in ("date", "time", "year", "created", "order")):
            time_col = c
            break

    contribution_analysis = None
    if time_col and time_col in work_df.columns:
        try:
            work_df["_dt"] = pd.to_datetime(work_df[time_col], errors="coerce")
            valid_dt = work_df.dropna(subset=["_dt"]).sort_values("_dt")
            if len(valid_dt) > 10:
                half = len(valid_dt) // 2
                p1_df = valid_dt.iloc[:half]
                p2_df = valid_dt.iloc[half:]

                p1_tot = float(p1_df["_metric_num"].sum())
                p2_tot = float(p2_df["_metric_num"].sum())
                tot_change = p2_tot - p1_tot

                p1_dim = p1_df.groupby(dim_col)["_metric_num"].sum()
                p2_dim = p2_df.groupby(dim_col)["_metric_num"].sum()

                dim_contribs = []
                all_keys = set(p1_dim.index).union(set(p2_dim.index))
                for k in all_keys:
                    v1 = float(p1_dim.get(k, 0.0))
                    v2 = float(p2_dim.get(k, 0.0))
                    diff = v2 - v1
                    pct_of_change = round((diff / tot_change * 100) if tot_change != 0 else 0.0, 2)
                    dim_contribs.append({
                        "dimension_value": str(k),
                        "period_1": round(v1, 2),
                        "period_2": round(v2, 2),
                        "change": round(diff, 2),
                        "contribution_pct": pct_of_change
                    })
                dim_contribs.sort(key=lambda x: x["change"])

                contribution_analysis = {
                    "total_change": round(tot_change, 2),
                    "period_1_total": round(p1_tot, 2),
                    "period_2_total": round(p2_tot, 2),
                    "dimension": dim_col,
                    "contributors": dim_contribs
                }
        except Exception:
            contribution_analysis = None

    # Multi-metric snapshot per dimension
    grouped = work_df.groupby(dim_col)["_metric_num"].agg(["sum", "mean", "count"]).reset_index()
    grouped.columns = [dim_col, "total", "average", "count"]
    grouped = grouped.sort_values("total", ascending=True)

    # Check for profit margin if sales column also exists
    sales_col = df_col_lower_map.get("sales") or df_col_lower_map.get("revenue")
    if sales_col and sales_col in work_df.columns and sales_col != metric_col:
        work_df["_sales_num"] = pd.to_numeric(work_df[sales_col], errors="coerce").fillna(0)
        s_grouped = work_df.groupby(dim_col)["_sales_num"].sum()
        grouped["sales"] = grouped[dim_col].map(s_grouped).fillna(0.0)
        grouped["margin_pct"] = np.where(grouped["sales"] != 0, (grouped["total"] / grouped["sales"]) * 100, 0.0).round(2)

    dim_summary = []
    for _, r in grouped.iterrows():
        item = {
            "entity": str(r[dim_col]),
            "total": round(float(r["total"]), 2),
            "average": round(float(r["average"]), 2),
            "count": int(r["count"])
        }
        if "margin_pct" in r:
            item["sales"] = round(float(r["sales"]), 2)
            item["margin_pct"] = float(r["margin_pct"])
        dim_summary.append(item)

    canonical = {
        "intent": "complex_insight",
        "metric": metric_col,
        "dimension": dim_col,
        "dimension_rankings": dim_summary,
        "contribution_analysis": contribution_analysis
    }

    table_headers = ["Entity", f"Total {metric_col.title()}", "Average", "Count"]
    if dim_summary and "margin_pct" in dim_summary[0]:
        table_headers.extend(["Sales", "Margin %"])

    table_rows = []
    for d in dim_summary:
        row = [d["entity"], f"{d['total']:,.2f}", f"{d['average']:,.2f}", str(d["count"])]
        if "margin_pct" in d:
            row.extend([f"{d['sales']:,.2f}", f"{d['margin_pct']:+.2f}%"])
        table_rows.append(row)

    table = {
        "headers": table_headers,
        "rows": table_rows
    }

    text_summary = f"Multi-dimensional analysis of {metric_col} across {dim_col}. Lowest performing entity: {dim_summary[0]['entity']} ({dim_summary[0]['total']:,.2f})."

    return QueryResult(
        success=True,
        type=ResponseType.DATA_RESULT.value,
        query=spec.to_dict(),
        result=canonical,
        table=table,
        text=text_summary,
        canonical_data=canonical,
        fields_used=[metric_col, dim_col],
        metadata={
            "dimension": dim_col,
            "metric": metric_col
        }
    )


def run_comparison(df: pd.DataFrame, spec: QuerySpec) -> QueryResult:
    """
    Deterministically computes side-by-side comparative analysis between entities.
    """
    if df is None or df.empty:
        return QueryResult(
            success=False,
            type=ResponseType.ERROR.value,
            error="Dataset is empty or unavailable."
        )

    df_col_lower_map = {c.lower(): c for c in df.columns}
    entities_to_compare = spec.options or spec.comparison_columns or []

    # Find target entity dimension
    dim_col = spec.group_by[0] if spec.group_by else None
    if dim_col:
        dim_col = df_col_lower_map.get(dim_col.lower(), dim_col)
    else:
        for d in ("category", "state", "region", "segment", "sub_category"):
            if d in df_col_lower_map:
                dim_col = df_col_lower_map[d]
                break

    if not dim_col or dim_col not in df.columns:
        cat_cols = [c for c in df.columns if not pd.api.types.is_numeric_dtype(df[c])]
        dim_col = cat_cols[0] if cat_cols else df.columns[0]

    num_cols = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]

    work_df = df.copy()
    if entities_to_compare:
        work_df = work_df[work_df[dim_col].astype(str).str.lower().isin([e.lower() for e in entities_to_compare])]

    comp_results = []
    for ent, group in work_df.groupby(dim_col):
        metrics_dict = {"entity": str(ent), "record_count": len(group)}
        for nc in num_cols[:5]:
            vals = pd.to_numeric(group[nc], errors="coerce").dropna()
            metrics_dict[f"{nc}_total"] = round(float(vals.sum()), 2) if not vals.empty else 0.0
            metrics_dict[f"{nc}_avg"] = round(float(vals.mean()), 2) if not vals.empty else 0.0
        comp_results.append(metrics_dict)

    canonical = {
        "intent": "comparison",
        "dimension": dim_col,
        "comparison_matrix": comp_results
    }

    headers = ["Entity", "Record Count"]
    for nc in num_cols[:5]:
        headers.append(f"{nc.title()} (Total)")
        headers.append(f"{nc.title()} (Avg)")

    table_rows = []
    for cr in comp_results:
        row = [cr["entity"], str(cr["record_count"])]
        for nc in num_cols[:5]:
            row.append(f"{cr.get(f'{nc}_total', 0.0):,.2f}")
            row.append(f"{cr.get(f'{nc}_avg', 0.0):,.2f}")
        table_rows.append(row)

    table = {
        "headers": headers,
        "rows": table_rows
    }

    return QueryResult(
        success=True,
        type=ResponseType.DATA_RESULT.value,
        query=spec.to_dict(),
        result=canonical,
        table=table,
        text=f"Comparative analysis across {len(comp_results)} entities in {dim_col}.",
        canonical_data=canonical,
        comparison_data=canonical,
        fields_used=[dim_col] + num_cols[:5]
    )


def run_decision_analysis(df: pd.DataFrame, spec: QuerySpec) -> QueryResult:
    """
    Deterministically produces multi-criteria decision matrix for options.
    """
    comp_res = run_comparison(df, spec)
    if not comp_res.success or not comp_res.canonical_data:
        return comp_res

    matrix = comp_res.canonical_data.get("comparison_matrix", [])
    dim_col = comp_res.canonical_data.get("dimension", "Option")

    options = [m["entity"] for m in matrix]
    factors = [k.replace("_total", "").replace("_avg", "") for k in matrix[0].keys() if k not in ("entity", "record_count")] if matrix else []

    tradeoffs = []
    for m in matrix:
        tradeoffs.append({
            "option": m["entity"],
            "strengths": [f"High {k}" for k, v in m.items() if isinstance(v, (int, float)) and v > 0][:2],
            "weaknesses": [f"Lower {k}" for k, v in m.items() if isinstance(v, (int, float)) and v <= 0][:2]
        })

    decision_data = {
        "intent": "decision_analysis",
        "dimension": dim_col,
        "options": options,
        "factors": list(set(factors)),
        "tradeoffs": tradeoffs,
        "evidence": matrix,
        "uncertainties": ["Market fluctuations", "Unobserved external variables"]
    }

    comp_res.canonical_data = decision_data
    comp_res.decision_data = decision_data
    return comp_res
