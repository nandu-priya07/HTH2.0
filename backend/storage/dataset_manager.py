"""
Dataset Manager & Registry Service.
Handles in-memory caching, disk loading, dataset listing,
and dynamic analytical question suggestion generation.
"""

import os
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional
import pandas as pd

from file_processing.schema_inference import infer_schema
from file_processing.data_profiler import profile_dataset

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent
RAW_DIR = BASE_DIR / "uploads" / "raw"
PROCESSED_DIR = BASE_DIR / "uploads" / "processed"

# In-memory registry of datasets
DATASET_REGISTRY: Dict[str, Dict[str, Any]] = {}


def register_dataset(dataset_id: str, info: Dict[str, Any]) -> None:
    """Stores or updates dataset information in the in-memory registry."""
    DATASET_REGISTRY[dataset_id] = info


def get_or_load_dataset(dataset_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Retrieves dataset from in-memory registry, or loads processed CSV from disk if available.
    If dataset_id is None, returns the most recently loaded/modified dataset.
    """
    # 1. Check in-memory registry for specific dataset_id
    if dataset_id and dataset_id in DATASET_REGISTRY:
        return DATASET_REGISTRY[dataset_id]

    # 2. If no dataset_id specified, return most recent from in-memory registry if available
    if not dataset_id and DATASET_REGISTRY:
        return list(DATASET_REGISTRY.values())[-1]

    # 3. Check disk for processed CSV files
    if PROCESSED_DIR.exists():
        if dataset_id:
            target_csv = PROCESSED_DIR / f"{dataset_id}.csv"
            candidates = [target_csv] if target_csv.exists() else []
        else:
            candidates = sorted(
                list(PROCESSED_DIR.glob("*.csv")),
                key=lambda p: (p.stat().st_mtime, p.stat().st_size),
                reverse=True
            )

        if candidates:
            csv_path = candidates[0]
            ds_id = csv_path.stem

            try:
                df = pd.read_csv(csv_path)
                schema = infer_schema(df)
                profile = profile_dataset(df, schema)

                # Check if raw file exists to recover original filename
                original_filename = f"{ds_id}.csv"
                file_size = csv_path.stat().st_size
                file_type = "csv"

                if RAW_DIR.exists():
                    raw_matches = list(RAW_DIR.glob(f"{ds_id}.*"))
                    if raw_matches:
                        raw_file = raw_matches[0]
                        file_type = raw_file.suffix.lstrip(".").lower()
                        file_size = raw_file.stat().st_size

                ds_entry = {
                    "dataset_id": ds_id,
                    "filename": original_filename,
                    "stored_filename": f"{ds_id}.{file_type}",
                    "processed_filename": f"{ds_id}.csv",
                    "file_path": str(csv_path),
                    "file_type": file_type,
                    "file_size": file_size,
                    "status": "processed",
                    "data": df,
                    "metadata": {
                        "dataset_id": ds_id,
                        "original_filename": original_filename,
                        "processed_filename": f"{ds_id}.csv",
                        "row_count": len(df),
                        "column_count": len(df.columns),
                        "rows": len(df),
                        "columns": len(df.columns)
                    },
                    "schema": schema,
                    "profile": profile,
                    "cleaning_report": {
                        "clean_dataset": True,
                        "rows_removed": 0
                    },
                    "result": {
                        "dataset_id": ds_id,
                        "original_filename": original_filename,
                        "processed_filename": f"{ds_id}.csv",
                        "schema": schema,
                        "profile": profile,
                        "metadata": {
                            "rows": len(df),
                            "columns": len(df.columns)
                        }
                    }
                }
                DATASET_REGISTRY[ds_id] = ds_entry
                return ds_entry
            except Exception as e:
                logger.error(f"Failed to auto-load processed dataset from {csv_path}: {e}")

    return None


def list_all_datasets() -> List[Dict[str, Any]]:
    """
    Lists all available datasets from memory and processed disk storage.
    Returns list of serialized dataset dictionaries suitable for frontend consumption.
    """
    # 1. Discover all processed datasets on disk
    if PROCESSED_DIR.exists():
        csv_files = sorted(
            list(PROCESSED_DIR.glob("*.csv")),
            key=lambda p: (p.stat().st_mtime, p.stat().st_size),
            reverse=True
        )
        for csv_file in csv_files:
            ds_id = csv_file.stem
            if ds_id not in DATASET_REGISTRY:
                get_or_load_dataset(ds_id)

    # 2. Build serialized dataset summaries
    datasets: List[Dict[str, Any]] = []
    # Reverse to show newest first
    for ds_id, info in reversed(list(DATASET_REGISTRY.items())):
        metadata = info.get("metadata") or info.get("result", {}).get("metadata") or {}
        df = info.get("data")
        row_count = metadata.get("row_count") or metadata.get("rows") or (len(df) if df is not None else 0)
        col_count = metadata.get("column_count") or metadata.get("columns") or (len(df.columns) if df is not None else 0)

        schema = info.get("schema") or info.get("result", {}).get("schema")
        profile = info.get("profile") or info.get("result", {}).get("profile")
        cleaning_report = info.get("cleaning_report") or info.get("result", {}).get("cleaning_report")

        datasets.append({
            "dataset_id": ds_id,
            "filename": info.get("filename") or f"{ds_id}.csv",
            "stored_filename": info.get("stored_filename") or f"{ds_id}.csv",
            "processed_filename": info.get("processed_filename") or f"{ds_id}.csv",
            "file_type": info.get("file_type", "csv"),
            "file_size": info.get("file_size", 0),
            "status": info.get("status", "processed"),
            "metadata": {
                **metadata,
                "rows": row_count,
                "columns": col_count,
                "row_count": row_count,
                "column_count": col_count
            },
            "rows": row_count,
            "columns": col_count,
            "schema": schema,
            "profile": profile,
            "cleaning_report": cleaning_report
        })

    return datasets


def generate_suggestions(schema: Optional[Dict[str, Any]], profile: Optional[Dict[str, Any]] = None) -> List[str]:
    """
    Generates 4 dynamic analytical question suggestions tailored to the dataset columns.
    Maps to the 4 UI recommendation cards: Ranking, Trend, Breakdown, Analysis.
    """
    default_suggestions = [
        "What are the top 5 products by revenue?",
        "Show me the monthly sales trend",
        "What is the total sales by region?",
        "What is the average profit by category?"
    ]

    if not schema or not isinstance(schema, dict):
        return default_suggestions

    num_cols = schema.get("numeric_columns", [])
    cat_cols = schema.get("categorical_columns", [])
    date_cols = schema.get("date_columns", [])
    id_cols = set(schema.get("identifier_columns", []))

    # Priority scoring for metrics
    metric_priority = [
        "sales", "revenue", "profit", "amount", "price", "cost", "income",
        "salary", "quantity", "total", "score", "discount", "margin", "units",
        "rating", "balance", "spend", "value"
    ]

    def score_metric(col_name: str) -> int:
        c_lower = col_name.lower().strip()
        if col_name in id_cols or "id" in c_lower:
            return -100
        if "year" in c_lower or "zip" in c_lower or "postal" in c_lower or "code" in c_lower:
            return -50
        for idx, kw in enumerate(metric_priority):
            if kw in c_lower:
                return 100 - idx
        return 10

    sorted_metrics = sorted(num_cols, key=score_metric, reverse=True)
    valid_metrics = [m for m in sorted_metrics if score_metric(m) > 0]
    if not valid_metrics and num_cols:
        valid_metrics = [m for m in num_cols if m not in id_cols] or num_cols

    # Priority scoring for dimensions / categories
    dim_priority = [
        "category", "sub_category", "subcategory", "region", "country", "country_region",
        "state", "city", "segment", "department", "brand", "product", "product_name",
        "type", "status", "customer", "customer_name", "gender", "market", "channel"
    ]

    def score_dimension(col_name: str) -> int:
        c_lower = col_name.lower().strip()
        if col_name in id_cols:
            return -100
        for idx, kw in enumerate(dim_priority):
            if kw in c_lower:
                return 100 - idx
        return 10

    sorted_dims = sorted(cat_cols, key=score_dimension, reverse=True)
    valid_dims = [d for d in sorted_dims if score_dimension(d) > 0]
    if not valid_dims and cat_cols:
        valid_dims = [d for d in cat_cols if d not in id_cols] or cat_cols

    m1 = valid_metrics[0] if valid_metrics else None
    m2 = valid_metrics[1] if len(valid_metrics) > 1 else m1

    d1 = valid_dims[0] if valid_dims else None
    d2 = valid_dims[1] if len(valid_dims) > 1 else (valid_dims[0] if valid_dims else None)
    d3 = valid_dims[2] if len(valid_dims) > 2 else d1

    date_col = date_cols[0] if date_cols else None

    suggestions: List[str] = []

    # 1. Ranking Suggestion
    if m1 and d1:
        suggestions.append(f"What are the top 5 {d1} by {m1}?")
    elif d1:
        suggestions.append(f"What are the top 5 most frequent {d1}?")
    elif m1:
        suggestions.append(f"What is the maximum {m1}?")
    else:
        suggestions.append(default_suggestions[0])

    # 2. Trend / Time / Secondary Grouping Suggestion
    if m1 and date_col:
        suggestions.append(f"Show {m1} trend over {date_col}")
    elif m1 and d2 and d2 != d1:
        suggestions.append(f"Show {m1} across {d2}")
    elif d2 and d2 != d1:
        suggestions.append(f"List the unique {d2}")
    elif m2:
        suggestions.append(f"What is the total {m2}?")
    else:
        suggestions.append(default_suggestions[1])

    # 3. Breakdown Suggestion
    target_dim = d2 if (d2 and d2 != d1) else d1
    if m1 and target_dim:
        suggestions.append(f"What is the total {m1} by {target_dim}?")
    elif target_dim:
        suggestions.append(f"List the unique {target_dim}")
    elif m1:
        suggestions.append(f"What is the total {m1}?")
    else:
        suggestions.append(default_suggestions[2])

    # 4. Analysis / Average / Distinct Suggestion
    analysis_dim = d3 if d3 else (d1 if d1 else None)
    if m2 and analysis_dim:
        suggestions.append(f"What is the average {m2} by {analysis_dim}?")
    elif m1 and analysis_dim:
        suggestions.append(f"What is the average {m1} by {analysis_dim}?")
    elif m1:
        suggestions.append(f"What is the average {m1}?")
    elif analysis_dim:
        suggestions.append(f"Count records by {analysis_dim}")
    else:
        suggestions.append(default_suggestions[3])

    return suggestions[:4]
