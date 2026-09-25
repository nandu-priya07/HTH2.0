"""
Deterministic Dataset Profiling Engine.
Calculates dataset metrics, column profiles, missing values, duplicates, and statistical summaries.
"""

from typing import Any, Dict, List, Optional
import pandas as pd
import numpy as np
from .models import QuerySpec, QueryResult, ResponseType


def run_dataset_summary(df: pd.DataFrame, spec: Optional[QuerySpec] = None) -> QueryResult:
    """
    Deterministically profiles the dataset.
    Returns structured QueryResult with canonical summary JSON and formatted table.
    """
    if df is None or df.empty:
        return QueryResult(
            success=False,
            type=ResponseType.ERROR.value,
            error="Dataset is empty or unavailable."
        )

    num_rows = len(df)
    num_cols = len(df.columns)

    numeric_cols = []
    categorical_cols = []
    date_cols = []
    missing_dict = {}

    date_range_info = None

    for col in df.columns:
        null_count = int(df[col].isna().sum())
        if null_count > 0:
            missing_dict[str(col)] = null_count

        # Check datetime
        if pd.api.types.is_datetime64_any_dtype(df[col]):
            date_cols.append(str(col))
            non_null = df[col].dropna()
            if not non_null.empty:
                date_range_info = {
                    "column": str(col),
                    "start": str(non_null.min()),
                    "end": str(non_null.max())
                }
        elif pd.api.types.is_numeric_dtype(df[col]):
            numeric_cols.append(str(col))
        else:
            # Check if parseable as datetime
            sample = df[col].dropna().head(10).astype(str)
            if not sample.empty and any(k in str(col).lower() for k in ("date", "time", "year", "month", "day", "created", "order")):
                try:
                    converted = pd.to_datetime(df[col], errors="coerce")
                    if converted.dropna().shape[0] > num_rows * 0.5:
                        date_cols.append(str(col))
                        non_null = converted.dropna()
                        if not non_null.empty and not date_range_info:
                            date_range_info = {
                                "column": str(col),
                                "start": str(non_null.min().date()),
                                "end": str(non_null.max().date())
                            }
                        continue
                except Exception:
                    pass
            categorical_cols.append(str(col))

    num_summary = []
    key_metrics = {}
    for col in numeric_cols[:10]:
        s = df[col].dropna()
        if not s.empty:
            stats = {
                "column": col,
                "min": float(s.min()),
                "max": float(s.max()),
                "mean": round(float(s.mean()), 2),
                "median": round(float(s.median()), 2),
                "std": round(float(s.std()), 2) if len(s) > 1 else 0.0
            }
            num_summary.append(stats)
            key_metrics[col] = {
                "sum": round(float(s.sum()), 2),
                "avg": round(float(s.mean()), 2)
            }

    cat_summary = []
    top_categories = {}
    for col in categorical_cols[:10]:
        s = df[col].dropna()
        if not s.empty:
            vc = s.value_counts()
            top_val = str(vc.index[0]) if len(vc) > 0 else "N/A"
            top_cnt = int(vc.iloc[0]) if len(vc) > 0 else 0
            cat_summary.append({
                "column": col,
                "unique_count": int(s.nunique()),
                "top_value": top_val,
                "top_count": top_cnt
            })
            top_categories[col] = {
                "top_value": top_val,
                "count": top_cnt,
                "unique": int(s.nunique())
            }

    duplicates_count = int(df.duplicated().sum())
    total_cells = num_rows * num_cols
    total_missing = sum(missing_dict.values())
    completeness_pct = round((1.0 - (total_missing / total_cells if total_cells > 0 else 0.0)) * 100, 2)

    quality_info = {
        "completeness_percentage": completeness_pct,
        "duplicate_rows": duplicates_count,
        "total_missing_values": total_missing
    }

    canonical = {
        "intent": "dataset_summary",
        "rows": num_rows,
        "columns": num_cols,
        "date_range": date_range_info,
        "numeric_columns": numeric_cols,
        "categorical_columns": categorical_cols,
        "date_columns": date_cols,
        "missing_values": missing_dict,
        "duplicates": duplicates_count,
        "key_metrics": key_metrics,
        "top_categories": top_categories,
        "quality": quality_info,
        "numeric_summaries": num_summary,
        "categorical_summaries": cat_summary
    }

    # Format table output for frontend display
    table_rows = [
        ["Total Rows", str(num_rows)],
        ["Total Columns", str(num_cols)],
        ["Numeric Columns", f"{len(numeric_cols)} ({', '.join(numeric_cols[:4])})"],
        ["Categorical Columns", f"{len(categorical_cols)} ({', '.join(categorical_cols[:4])})"],
        ["Data Completeness", f"{completeness_pct}%"],
        ["Duplicate Rows", str(duplicates_count)]
    ]
    if date_range_info:
        table_rows.append(["Date Range", f"{date_range_info['start']} to {date_range_info['end']} ({date_range_info['column']})"])

    table = {
        "headers": ["Metric", "Value"],
        "rows": table_rows
    }

    summary_text = (
        f"Dataset contains {num_rows:,} rows across {num_cols} columns. "
        f"Completeness is {completeness_pct}% with {duplicates_count} duplicate rows."
    )

    return QueryResult(
        success=True,
        type=ResponseType.DATA_RESULT.value,
        query=spec.to_dict() if spec else {"operation": "dataset_summary"},
        result=canonical,
        table=table,
        text=summary_text,
        canonical_data=canonical,
        summary_data=canonical,
        fields_used=list(df.columns[:10]),
        metadata={
            "rows_analyzed": num_rows,
            "columns_analyzed": num_cols
        }
    )
