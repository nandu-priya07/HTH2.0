"""
Dataset Manager & Registry Service backed by Supabase PostgreSQL and Supabase Storage.
Handles dataset registration, in-memory caching, Supabase loading/saving, and dataset suggestions.
"""

import io
import json
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional
import pandas as pd
from psycopg2.extras import RealDictCursor, Json

from core.supabase import get_supabase_connection
from services.storage_service import SupabaseStorageService
from services.dataset_runtime import (
    DatasetRuntimeManager,
    get_dataset_runtime,
    load_dataset_runtime,
    release_dataset_runtime,
    invalidate_dataset_runtime,
    is_dataset_loaded
)
from file_processing.schema_inference import infer_schema
from file_processing.data_profiler import profile_dataset

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent
RAW_DIR = BASE_DIR / "uploads" / "raw"
PROCESSED_DIR = BASE_DIR / "uploads" / "processed"
CHATS_DIR = BASE_DIR / "storage" / "chats"

# In-memory registry of active datasets
DATASET_REGISTRY: Dict[str, Dict[str, Any]] = {}


def register_dataset(dataset_id: str, info: Dict[str, Any]) -> None:
    """Stores or updates dataset information in the in-memory registry and runtime manager."""
    DATASET_REGISTRY[dataset_id] = info
    df = info.get("data")
    if df is not None:
        load_dataset_runtime(dataset_id, existing_df=df, existing_info=info)


def _parse_json(val: Any) -> Any:
    if val is None:
        return None
    if isinstance(val, (dict, list)):
        return val
    if isinstance(val, str):
        try:
            return json.loads(val)
        except Exception:
            return None
    return val


def save_dataset_meta(dataset_id: str, meta: Dict[str, Any], chat_id: Optional[str] = None, user_id: Optional[str] = None) -> None:
    """
    Persists dataset metadata sidecar directly into Supabase PostgreSQL.
    """
    try:
        with get_supabase_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE public.datasets
                    SET metadata_json = %s, updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s;
                    """,
                    (Json(meta), dataset_id)
                )
    except Exception as e:
        logger.warning(f"Failed to update dataset metadata in Supabase for {dataset_id}: {e}")


def persist_dataset_to_supabase(
    dataset_id: str,
    info: Dict[str, Any],
    chat_id: Optional[str] = None,
    user_id: Optional[str] = None
) -> None:
    """
    Persists master dataset metadata record into Supabase PostgreSQL.
    """
    filename = info.get("filename") or f"{dataset_id}.csv"
    stored_filename = info.get("stored_filename") or f"{dataset_id}.csv"
    processed_filename = info.get("processed_filename") or f"{dataset_id}.csv"
    file_type = info.get("file_type", "csv")
    file_size = info.get("file_size", 0)
    status_str = info.get("status", "processed")

    metadata = info.get("metadata") or info.get("result", {}).get("metadata") or {}
    schema = info.get("schema") or info.get("result", {}).get("schema") or {}
    profile = info.get("profile") or info.get("result", {}).get("profile") or {}
    cleaning_report = info.get("cleaning_report") or info.get("result", {}).get("cleaning_report") or {}

    row_count = metadata.get("row_count") or metadata.get("rows") or 0
    col_count = metadata.get("column_count") or metadata.get("columns") or 0

    with get_supabase_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO public.datasets (
                    id, user_id, chat_id, filename, stored_filename, processed_filename,
                    file_type, file_size, row_count, column_count, status,
                    schema_json, profile_json, cleaning_report_json, metadata_json,
                    updated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                ON CONFLICT (id) DO UPDATE SET
                    chat_id = COALESCE(EXCLUDED.chat_id, public.datasets.chat_id),
                    user_id = COALESCE(EXCLUDED.user_id, public.datasets.user_id),
                    filename = EXCLUDED.filename,
                    stored_filename = EXCLUDED.stored_filename,
                    processed_filename = EXCLUDED.processed_filename,
                    file_type = EXCLUDED.file_type,
                    file_size = EXCLUDED.file_size,
                    row_count = EXCLUDED.row_count,
                    column_count = EXCLUDED.column_count,
                    status = EXCLUDED.status,
                    schema_json = EXCLUDED.schema_json,
                    profile_json = EXCLUDED.profile_json,
                    cleaning_report_json = EXCLUDED.cleaning_report_json,
                    metadata_json = EXCLUDED.metadata_json,
                    updated_at = CURRENT_TIMESTAMP;
                """,
                (
                    dataset_id,
                    user_id,
                    chat_id,
                    filename,
                    stored_filename,
                    processed_filename,
                    file_type,
                    file_size,
                    row_count,
                    col_count,
                    status_str,
                    Json(schema),
                    Json(profile),
                    Json(cleaning_report),
                    Json(metadata)
                )
            )
    logger.info(f"Persisted dataset master metadata into Supabase for dataset '{dataset_id}'")


def get_or_load_dataset(dataset_id: Optional[str] = None, chat_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Retrieves dataset runtime from DatasetRuntimeManager or loads processed file from Supabase Storage.
    """
    if not dataset_id or not str(dataset_id).strip():
        return None

    clean_id = str(dataset_id).strip()

    # 1. Check DatasetRuntimeManager cache
    runtime = get_dataset_runtime(clean_id)
    if runtime is not None:
        DATASET_REGISTRY[clean_id] = runtime.to_dict()
        return runtime.to_dict()

    # 2. Check legacy DATASET_REGISTRY if loaded with DataFrame
    if clean_id in DATASET_REGISTRY and DATASET_REGISTRY[clean_id].get("data") is not None:
        info = DATASET_REGISTRY[clean_id]
        rt = load_dataset_runtime(clean_id, chat_id=chat_id, existing_df=info.get("data"), existing_info=info)
        if rt:
            return rt.to_dict()

    # 3. Load via DatasetRuntimeManager from Supabase Storage
    rt = load_dataset_runtime(clean_id, chat_id=chat_id)
    if rt:
        DATASET_REGISTRY[clean_id] = rt.to_dict()
        return rt.to_dict()

    # 4. Legacy fallback to local disk files if present during migration
    target_csv = None
    if chat_id:
        chat_csv = CHATS_DIR / str(chat_id) / "files" / f"{clean_id}.csv"
        if chat_csv.exists():
            target_csv = chat_csv

    if not target_csv and CHATS_DIR.exists():
        matches = list(CHATS_DIR.glob(f"*/files/{clean_id}.csv"))
        if matches:
            target_csv = matches[0]

    if not target_csv and PROCESSED_DIR.exists():
        legacy_csv = PROCESSED_DIR / f"{clean_id}.csv"
        if legacy_csv.exists():
            target_csv = legacy_csv

    if target_csv and target_csv.exists():
        try:
            df = pd.read_csv(target_csv)
            schema = infer_schema(df)
            profile = profile_dataset(df, schema)
            ds_entry = {
                "dataset_id": clean_id,
                "filename": f"{clean_id}.csv",
                "stored_filename": f"{clean_id}.csv",
                "processed_filename": f"{clean_id}.csv",
                "file_type": "csv",
                "file_size": target_csv.stat().st_size,
                "status": "processed",
                "data": df,
                "metadata": {
                    "dataset_id": clean_id,
                    "row_count": len(df),
                    "column_count": len(df.columns),
                    "rows": len(df),
                    "columns": len(df.columns)
                },
                "schema": schema,
                "profile": profile,
                "cleaning_report": {"clean_dataset": True, "rows_removed": 0},
                "result": {
                    "dataset_id": clean_id,
                    "schema": schema,
                    "profile": profile,
                    "metadata": {"rows": len(df), "columns": len(df.columns)}
                }
            }
            rt = load_dataset_runtime(clean_id, chat_id=chat_id, existing_df=df, existing_info=ds_entry)
            DATASET_REGISTRY[clean_id] = ds_entry
            return ds_entry
        except Exception as e:
            logger.error(f"Failed legacy disk load for dataset {clean_id}: {e}")

    return None


def list_all_datasets() -> List[Dict[str, Any]]:
    """
    Lists all active/processed datasets from Supabase PostgreSQL and memory.
    """
    datasets_map: Dict[str, Dict[str, Any]] = {}

    try:
        with get_supabase_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT * FROM public.datasets ORDER BY updated_at DESC;")
                rows = cur.fetchall()

                for row in rows:
                    ds_id = row["id"]
                    metadata = _parse_json(row["metadata_json"]) or {}
                    schema = _parse_json(row["schema_json"])
                    profile = _parse_json(row["profile_json"])
                    cleaning_report = _parse_json(row["cleaning_report_json"])

                    row_count = row["row_count"] or metadata.get("row_count") or metadata.get("rows") or 0
                    col_count = row["column_count"] or metadata.get("column_count") or metadata.get("columns") or 0

                    datasets_map[ds_id] = {
                        "dataset_id": ds_id,
                        "filename": row["filename"],
                        "stored_filename": row["stored_filename"],
                        "processed_filename": row["processed_filename"],
                        "file_type": row["file_type"],
                        "file_size": row["file_size"],
                        "status": row["status"],
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
                    }
    except Exception as e:
        logger.error(f"Error listing datasets from Supabase PostgreSQL: {e}")

    # Include any remaining in-memory datasets
    for ds_id, info in DATASET_REGISTRY.items():
        if ds_id not in datasets_map:
            metadata = info.get("metadata") or info.get("result", {}).get("metadata") or {}
            df = info.get("data")
            row_count = metadata.get("row_count") or metadata.get("rows") or (len(df) if df is not None else 0)
            col_count = metadata.get("column_count") or metadata.get("columns") or (len(df.columns) if df is not None else 0)

            datasets_map[ds_id] = {
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
                "schema": info.get("schema") or info.get("result", {}).get("schema"),
                "profile": info.get("profile") or info.get("result", {}).get("profile"),
                "cleaning_report": info.get("cleaning_report") or info.get("result", {}).get("cleaning_report")
            }

    return list(datasets_map.values())


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
