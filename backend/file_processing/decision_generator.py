"""
Dynamic Decision Analysis Generator.

Transforms any uploaded dataset (CSV/XLS/XLSX) into high-impact, evidence-backed
decision findings based strictly on actual dataset distributions, cross-column
comparisons, time-series shifts, concentration, and statistical anomalies.

Zero hardcoded fields, values, or sample assumptions.
"""

from typing import Dict, Any, List, Optional
import numpy as np
import pandas as pd


def format_column_name(col: str) -> str:
    """Converts raw column names into readable labels."""
    if not col:
        return ""
    clean = str(col).replace("_", " ").replace("-", " ").strip()
    words = clean.split()
    return " ".join(w.capitalize() if not w.isupper() else w for w in words)


def is_currency_col(col_name: str) -> bool:
    """Infers if column represents monetary currency based on name."""
    s = col_name.lower()
    currency_keywords = [
        "sales", "revenue", "profit", "cost", "charge", "price",
        "fee", "spend", "salary", "budget", "amount", "income", "bill"
    ]
    return any(k in s for k in currency_keywords)


def format_number(val: Optional[float], is_currency: bool = False, is_pct: bool = False) -> str:
    """Formats numeric values into standard human-readable units."""
    if val is None or pd.isna(val):
        return "—"
    try:
        num = float(val)
    except (ValueError, TypeError):
        return str(val)

    prefix = "$" if is_currency else ""
    suffix = "%" if is_pct else ""

    if is_pct:
        return f"{num:+.1f}%" if num > 0 else f"{num:.1f}%"

    abs_num = abs(num)
    sign = "-" if num < 0 else ""

    if abs_num >= 1_000_000_000:
        return f"{sign}{prefix}{abs_num / 1_000_000_000:.2f}B{suffix}"
    if abs_num >= 1_000_000:
        return f"{sign}{prefix}{abs_num / 1_000_000:.2f}M{suffix}"
    if abs_num >= 10_000:
        return f"{sign}{prefix}{abs_num / 1_000:.1f}K{suffix}"
    if abs_num >= 1_000:
        return f"{sign}{prefix}{num:,.0f}{suffix}"
    if abs_num < 1 and abs_num > 0:
        return f"{sign}{prefix}{num:.2f}{suffix}"
    return f"{sign}{prefix}{num:,.2f}".rstrip("0").rstrip(".") + suffix


def is_id_col(col_name: str) -> bool:
    """Detects if a column is likely an identifier/key rather than an analytical measure."""
    s = str(col_name).lower().replace("_", "").replace("-", "").strip()
    return s in ("id", "rowid", "orderid", "customerid", "recordid", "index", "uid", "uuid", "key") or s.endswith("id")


def generate_dataset_decisions(
    df: Optional[pd.DataFrame],
    schema: Dict[str, Any],
    profile: Dict[str, Any],
    dataset_id: str = "dataset"
) -> Dict[str, Any]:
    """
    Generates actionable, evidence-backed decision findings for the dataset.
    """
    decisions: List[Dict[str, Any]] = []

    if df is None or df.empty:
        return {
            "success": True,
            "dataset_id": dataset_id,
            "row_count": 0,
            "column_count": 0,
            "decisions": [],
            "has_numeric": False,
            "has_categorical": False,
            "has_date": False
        }

    total_rows = len(df)
    total_cols = len(df.columns)

    numeric_cols = schema.get("numeric_columns", [])
    categorical_cols = schema.get("categorical_columns", [])
    date_cols = schema.get("date_columns", [])

    # Filter columns that actually exist in the dataframe
    numeric_cols = [c for c in numeric_cols if c in df.columns]
    categorical_cols = [c for c in categorical_cols if c in df.columns]
    date_cols = [c for c in date_cols if c in df.columns]

    # Additional discovery if schema lacked them
    if not numeric_cols:
        for c in df.columns:
            if pd.api.types.is_numeric_dtype(df[c]) and df[c].nunique() > 1:
                numeric_cols.append(c)

    # Sort numeric columns: real measures first (non-IDs), then currency/analytics keywords first
    def measure_priority(c: str) -> int:
        if is_id_col(c):
            return 100
        if is_currency_col(c):
            return 1
        s = c.lower()
        if any(w in s for w in ["total", "spend", "tenure", "rate", "count", "score", "value", "charges"]):
            return 2
        return 10

    numeric_cols.sort(key=measure_priority)

    if not categorical_cols:
        for c in df.columns:
            if c not in numeric_cols and 1 < df[c].nunique() <= 50:
                categorical_cols.append(c)

    # Additional discovery if schema lacked them
    if not date_cols:
        for c in df.columns:
            s = c.lower()
            if any(w in s for w in ["date", "time", "timestamp", "year", "month", "day"]):
                date_cols.append(c)
            elif pd.api.types.is_datetime64_any_dtype(df[c]):
                date_cols.append(c)

    # Filter out pure identifier columns and near-uniform columns (e.g. 98% same country)
    meaningful_categoricals = []
    for c in categorical_cols:
        if 1 < df[c].nunique() <= 30 and not is_id_col(c):
            val_counts = df[c].value_counts()
            if not val_counts.empty:
                top_pct = val_counts.iloc[0] / max(total_rows, 1)
                if top_pct < 0.95:  # avoid single-value dominated columns
                    meaningful_categoricals.append(c)

    has_numeric = len(numeric_cols) > 0
    has_categorical = len(meaningful_categoricals) > 0
    has_date = len(date_cols) > 0

    # ─────────────────────────────────────────────────────────────
    # Finding 1: Above / Below Group Comparison
    # Scan candidate pairs to find the most significant variance
    # ─────────────────────────────────────────────────────────────
    best_comp = None
    if has_numeric and has_categorical:
        for num_col in numeric_cols[:2]:
            is_curr = is_currency_col(num_col)
            for cat_col in meaningful_categoricals[:4]:
                try:
                    grouped = df.groupby(cat_col)[num_col].mean().dropna()
                    if len(grouped) >= 2:
                        top_group = grouped.idxmax()
                        top_val = float(grouped.max())
                        other_vals = grouped.drop(index=top_group)
                        avg_other = float(other_vals.mean()) if not other_vals.empty else top_val

                        if avg_other > 0:
                            diff_pct = ((top_val - avg_other) / avg_other) * 100.0
                            if diff_pct >= 5.0 and (best_comp is None or diff_pct > best_comp["diff_pct"]):
                                best_comp = {
                                    "num_col": num_col,
                                    "cat_col": cat_col,
                                    "top_group": top_group,
                                    "top_val": top_val,
                                    "avg_other": avg_other,
                                    "diff_pct": diff_pct,
                                    "is_curr": is_curr
                                }
                except Exception:
                    continue

    if best_comp:
        num_label = format_column_name(best_comp["num_col"])
        cat_label = format_column_name(best_comp["cat_col"])
        top_group = best_comp["top_group"]
        diff_pct = best_comp["diff_pct"]
        is_curr = best_comp["is_curr"]

        decisions.append({
            "id": f"dec_comp_{best_comp['num_col']}_{best_comp['cat_col']}",
            "type": "above_below",
            "finding": f"{top_group} {num_label.lower()} is {diff_pct:.0f}% above the average of other {cat_label.lower()} groups.",
            "metrics": [
                {
                    "label": f"{top_group} avg.",
                    "value": format_number(best_comp["top_val"], is_currency=is_curr)
                },
                {
                    "label": f"Avg. other {cat_label.lower()}",
                    "value": format_number(best_comp["avg_other"], is_currency=is_curr)
                },
                {
                    "label": "Variance",
                    "value": f"+{diff_pct:.1f}%"
                }
            ],
            "evidence": [
                f"AVG({best_comp['num_col']}) GROUP BY {best_comp['cat_col']}",
                f"{total_rows:,} rows analyzed",
                "No filters applied"
            ],
            "analysis": f"Ranking + comparison across the {cat_label} field against group benchmark averages.",
            "details": {
                "primary_group": str(top_group),
                "primary_value": best_comp["top_val"],
                "comparison_value": best_comp["avg_other"],
                "diff_percent": diff_pct,
                "dimension": best_comp["cat_col"],
                "metric": best_comp["num_col"]
            }
        })

    # ─────────────────────────────────────────────────────────────
    # Finding 2: Concentration & Volume Contribution
    # Scan for the highest volume share across dimensions
    # ─────────────────────────────────────────────────────────────
    best_conc = None
    if has_numeric and has_categorical:
        num_col = numeric_cols[0]
        is_curr = is_currency_col(num_col)

        for cat_col in meaningful_categoricals[:4]:
            if best_comp and cat_col == best_comp["cat_col"] and len(meaningful_categoricals) > 1:
                # prefer distinct dimension if available
                continue
            try:
                grouped_sum = df.groupby(cat_col)[num_col].sum().dropna()
                total_sum = float(grouped_sum.sum())
                if total_sum > 0 and len(grouped_sum) >= 2:
                    top_group = grouped_sum.idxmax()
                    top_sum = float(grouped_sum.max())
                    share_pct = (top_sum / total_sum) * 100.0

                    if share_pct >= 20.0 and (best_conc is None or share_pct > best_conc["share_pct"]):
                        best_conc = {
                            "num_col": num_col,
                            "cat_col": cat_col,
                            "top_group": top_group,
                            "top_sum": top_sum,
                            "total_sum": total_sum,
                            "share_pct": share_pct,
                            "group_count": len(grouped_sum),
                            "is_curr": is_curr
                        }
            except Exception:
                continue

    if best_conc:
        num_label = format_column_name(best_conc["num_col"])
        cat_label = format_column_name(best_conc["cat_col"])
        top_group = best_conc["top_group"]
        share_pct = best_conc["share_pct"]
        is_curr = best_conc["is_curr"]

        decisions.append({
            "id": f"dec_conc_{best_conc['num_col']}_{best_conc['cat_col']}",
            "type": "concentration",
            "finding": f"{top_group} accounts for {share_pct:.1f}% of total {num_label.lower()} across the analyzed dataset.",
            "metrics": [
                {
                    "label": f"{top_group} {num_label.lower()}",
                    "value": format_number(best_conc["top_sum"], is_currency=is_curr)
                },
                {
                    "label": f"Total {num_label.lower()}",
                    "value": format_number(best_conc["total_sum"], is_currency=is_curr)
                },
                {
                    "label": "Volume share",
                    "value": f"{share_pct:.1f}%"
                }
            ],
            "evidence": [
                f"SUM({best_conc['num_col']}) GROUP BY {best_conc['cat_col']}",
                f"{total_rows:,} rows analyzed",
                f"Aggregated volume across {best_conc['group_count']} distinct {cat_label.lower()} segments"
            ],
            "analysis": f"Volume concentration and contribution weighting across the {cat_label} dimension.",
            "details": {
                "top_group": str(top_group),
                "top_sum": best_conc["top_sum"],
                "total_sum": best_conc["total_sum"],
                "share_percent": share_pct,
                "dimension": best_conc["cat_col"],
                "metric": best_conc["num_col"]
            }
        })

    # ─────────────────────────────────────────────────────────────
    # Finding 3: Time-Based Trend / Period-Over-Period Findings
    # STRICTLY when a valid date/time column is present!
    # ─────────────────────────────────────────────────────────────
    if has_numeric and has_date:
        date_col = date_cols[0]
        num_col = numeric_cols[0]
        is_curr = is_currency_col(num_col)
        num_label = format_column_name(num_col)
        date_label = format_column_name(date_col)

        try:
            parsed_dates = pd.to_datetime(df[date_col], errors="coerce")
            valid_mask = parsed_dates.notna() & df[num_col].notna()

            if valid_mask.sum() >= 6:
                temp_df = pd.DataFrame({
                    "ds": parsed_dates[valid_mask],
                    "y": pd.to_numeric(df.loc[valid_mask, num_col], errors="coerce")
                }).dropna()

                # Group by Month
                temp_df["period"] = temp_df["ds"].dt.to_period("M")
                monthly = temp_df.groupby("period")["y"].sum().sort_index()

                if len(monthly) >= 3:
                    peak_period = monthly.idxmax()
                    peak_val = float(monthly.max())
                    period_avg = float(monthly.mean())
                    num_periods = len(monthly)

                    uplift_over_avg = ((peak_val - period_avg) / max(period_avg, 1)) * 100.0

                    decisions.append({
                        "id": f"dec_trend_{num_col}_{date_col}",
                        "type": "trend",
                        "finding": f"{num_label} reached its historical peak during {peak_period} with {format_number(peak_val, is_currency=is_curr)}.",
                        "metrics": [
                            {
                                "label": f"Peak ({peak_period})",
                                "value": format_number(peak_val, is_currency=is_curr)
                            },
                            {
                                "label": "Monthly average",
                                "value": format_number(period_avg, is_currency=is_curr)
                            },
                            {
                                "label": "Periods observed",
                                "value": f"{num_periods}"
                            }
                        ],
                        "evidence": [
                            f"SUM({num_col}) GROUP BY {date_col} (monthly)",
                            f"Trend across {num_periods} months ({total_rows:,} rows)",
                            "Temporal aggregation with no filters"
                        ],
                        "analysis": f"Trend analysis and peak cycle detection across the inferred {date_label} timeline.",
                        "details": {
                            "peak_period": str(peak_period),
                            "peak_value": peak_val,
                            "period_avg": period_avg,
                            "uplift_percent": uplift_over_avg,
                            "periods_observed": num_periods,
                            "date_column": date_col,
                            "metric": num_col
                        }
                    })
        except Exception:
            pass

    # ─────────────────────────────────────────────────────────────
    # Finding 4: Statistical Outliers / Anomaly Risk
    # ─────────────────────────────────────────────────────────────
    if has_numeric:
        num_col = numeric_cols[0]
        is_curr = is_currency_col(num_col)
        num_label = format_column_name(num_col)

        s = pd.to_numeric(df[num_col], errors="coerce").dropna()
        if len(s) >= 15:
            q1 = float(s.quantile(0.25))
            q3 = float(s.quantile(0.75))
            iqr = q3 - q1

            if iqr > 0:
                upper_fence = q3 + (1.5 * iqr)
                lower_fence = q1 - (1.5 * iqr)
                outliers = s[(s > upper_fence) | (s < lower_fence)]
                outlier_count = len(outliers)

                if outlier_count > 0:
                    max_outlier = float(outliers.max())
                    pct_outliers = (outlier_count / len(s)) * 100.0

                    decisions.append({
                        "id": f"dec_anomaly_{num_col}",
                        "type": "anomaly",
                        "finding": f"{outlier_count} record{'s' if outlier_count != 1 else ''} in {num_label.lower()} deviate significantly from standard distribution fences.",
                        "metrics": [
                            {
                                "label": "Flagged records",
                                "value": f"{outlier_count:,}"
                            },
                            {
                                "label": "Extreme value",
                                "value": format_number(max_outlier, is_currency=is_curr)
                            },
                            {
                                "label": "Upper fence",
                                "value": format_number(upper_fence, is_currency=is_curr)
                            }
                        ],
                        "evidence": [
                            f"Statistical IQR Fence (Q3 + 1.5 x IQR) on {num_col}",
                            f"{total_rows:,} records evaluated",
                            f"Upper threshold {format_number(upper_fence, is_currency=is_curr)}"
                        ],
                        "analysis": f"Statistical outlier detection identifying unusual extreme values in {num_label}.",
                        "details": {
                            "outlier_count": outlier_count,
                            "max_outlier": max_outlier,
                            "upper_fence": upper_fence,
                            "lower_fence": lower_fence,
                            "metric": num_col
                        }
                    })

    # ─────────────────────────────────────────────────────────────
    # Finding 5: Categorical Distribution Dominance / Imbalance
    # ─────────────────────────────────────────────────────────────
    if has_categorical and len(decisions) < 3:
        cat_col = meaningful_categoricals[0]
        cat_label = format_column_name(cat_col)

        val_counts = df[cat_col].value_counts().dropna()
        if len(val_counts) >= 2:
            top_val = str(val_counts.index[0])
            top_count = int(val_counts.iloc[0])
            share_pct = (top_count / total_rows) * 100.0

            if share_pct >= 35.0:
                decisions.append({
                    "id": f"dec_dist_{cat_col}",
                    "type": "distribution",
                    "finding": f"'{top_val}' represents {share_pct:.1f}% of all recorded observations in {cat_label.lower()}.",
                    "metrics": [
                        {
                            "label": f"'{top_val}' count",
                            "value": f"{top_count:,}"
                        },
                        {
                            "label": "Total records",
                            "value": f"{total_rows:,}"
                        },
                        {
                            "label": "Share",
                            "value": f"{share_pct:.1f}%"
                        }
                    ],
                    "evidence": [
                        f"FREQUENCY DISTRIBUTION GROUP BY {cat_col}",
                        f"{total_rows:,} rows analyzed",
                        f"{len(val_counts)} distinct category values"
                    ],
                    "analysis": f"Categorical representation distribution across the {cat_label} field.",
                    "details": {
                        "top_value": top_val,
                        "top_count": top_count,
                        "total_rows": total_rows,
                        "share_percent": share_pct,
                        "dimension": cat_col
                    }
                })

    # ─────────────────────────────────────────────────────────────
    # Finding 6: Secondary Measure Comparison (if available)
    # ─────────────────────────────────────────────────────────────
    if len(numeric_cols) >= 2 and has_categorical and len(decisions) < 4:
        num_col = numeric_cols[1]
        cat_col = meaningful_categoricals[0]
        is_curr = is_currency_col(num_col)

        grouped = df.groupby(cat_col)[num_col].mean().dropna()
        if len(grouped) >= 2:
            top_group = grouped.idxmax()
            top_val = float(grouped.max())
            avg_all = float(grouped.mean())
            diff_pct = ((top_val - avg_all) / max(avg_all, 1)) * 100.0

            num_label = format_column_name(num_col)
            cat_label = format_column_name(cat_col)

            if diff_pct >= 10.0:
                decisions.append({
                    "id": f"dec_sec_{num_col}_{cat_col}",
                    "type": "above_below",
                    "finding": f"{top_group} leads in average {num_label.lower()}, exceeding the category baseline by {diff_pct:.0f}%.",
                    "metrics": [
                        {
                            "label": f"{top_group} avg.",
                            "value": format_number(top_val, is_currency=is_curr)
                        },
                        {
                            "label": "Category average",
                            "value": format_number(avg_all, is_currency=is_curr)
                        },
                        {
                            "label": "Variance",
                            "value": f"+{diff_pct:.1f}%"
                        }
                    ],
                    "evidence": [
                        f"AVG({num_col}) GROUP BY {cat_col}",
                        f"{total_rows:,} rows analyzed",
                        "Secondary measure evaluation"
                    ],
                    "analysis": f"Comparative performance across the {cat_label} field for secondary measure {num_label}.",
                    "details": {
                        "primary_group": str(top_group),
                        "primary_value": top_val,
                        "comparison_value": avg_all,
                        "diff_percent": diff_pct,
                        "dimension": cat_col,
                        "metric": num_col
                    }
                })

    return {
        "success": True,
        "dataset_id": dataset_id,
        "row_count": total_rows,
        "column_count": total_cols,
        "numeric_columns": numeric_cols,
        "categorical_columns": categorical_cols,
        "date_columns": date_cols,
        "decisions": decisions,
        "has_numeric": has_numeric,
        "has_categorical": has_categorical,
        "has_date": has_date
    }
