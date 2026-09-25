"""
Dataset Runtime Manager service backed by Python process memory and Supabase Storage.
Provides in-memory caching for loaded dataset runtimes (DuckDB, Pandas, Schema, Value Index, Geo Hierarchy, Derived Metrics).
Prevents downloading and re-parsing datasets from Supabase Storage on every user query.
"""

import io
import json
import logging
import os
import re
import threading
import time
from typing import Any, Dict, List, Optional, Union

import duckdb
import pandas as pd
from psycopg2.extras import RealDictCursor

from analyst.value_indexer import DatasetValueIndex, ValueIndexer
from core.supabase import get_supabase_connection
from file_processing.data_profiler import profile_dataset
from file_processing.schema_inference import infer_schema
from geo.hierarchy_discovery import discover_hierarchy
from services.storage_service import SupabaseStorageService

logger = logging.getLogger(__name__)


class DatasetRuntime:
    """
    In-memory runtime cache object representing a loaded, processed dataset.
    Prevents repeated Supabase Storage downloads, Parquet/CSV parsing, DuckDB connection creation,
    and schema/index building on subsequent queries.
    """

    def __init__(
        self,
        dataset_id: str,
        version: str,
        df: pd.DataFrame,
        schema: Optional[Dict[str, Any]] = None,
        profile: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        cleaning_report: Optional[Dict[str, Any]] = None,
        filename: Optional[str] = None,
        stored_filename: Optional[str] = None,
        processed_filename: Optional[str] = None,
        file_type: str = "csv",
        file_size: int = 0,
        status: str = "processed"
    ):
        self.dataset_id: str = dataset_id
        self.version: str = version or str(time.time())
        self.df: pd.DataFrame = df
        self.filename: str = filename or f"{dataset_id}.csv"
        self.stored_filename: str = stored_filename or f"{dataset_id}.csv"
        self.processed_filename: str = processed_filename or f"{dataset_id}.csv"
        self.file_type: str = file_type
        self.file_size: int = file_size
        self.status: str = status

        self.schema: Dict[str, Any] = schema or {}
        self.profile: Dict[str, Any] = profile or {}
        self.metadata: Dict[str, Any] = metadata or {}
        self.cleaning_report: Dict[str, Any] = cleaning_report or {}

        # Build value index, geo hierarchy, derived metrics, column metadata once
        self.value_index: DatasetValueIndex = ValueIndexer.build_index(dataset_id, df)
        self.geo_hierarchy: List[Dict[str, Any]] = discover_hierarchy(df, self.profile)
        self.derived_metrics: Dict[str, Any] = self._extract_derived_metrics()
        self.column_metadata: Dict[str, Any] = self._extract_column_metadata()

        # Reusable in-memory DuckDB connection & registered table view
        self.duckdb_connection: duckdb.DuckDBPyConnection = duckdb.connect(database=":memory:")
        self.duckdb_connection.register("dataset", df)
        sanitized_tbl = re.sub(r"[^a-zA-Z0-9_]", "_", f"dataset_{dataset_id}")
        try:
            self.duckdb_connection.register(sanitized_tbl, df)
        except Exception:
            pass

        now = time.time()
        self.created_at: float = now
        self.last_used_at: float = now

    def touch(self) -> None:
        """Updates last_used_at timestamp for LRU cache tracking."""
        self.last_used_at = time.time()

    def _extract_derived_metrics(self) -> Dict[str, Any]:
        """Discovers or builds derived metrics from dataset columns."""
        cols = list(self.df.columns) if self.df is not None else []
        col_lower = {str(c).lower(): c for c in cols}
        metrics = {}
        if "quantity" in col_lower and ("price" in col_lower or "unit_price" in col_lower):
            p_col = col_lower.get("price") or col_lower.get("unit_price")
            metrics["Revenue"] = {
                "name": "Revenue",
                "formula": f"{col_lower['quantity']} * {p_col}",
                "operands": [col_lower['quantity'], p_col],
                "operator": "*"
            }
        if "sales" in col_lower and "profit" in col_lower:
            metrics["Profit_Margin"] = {
                "name": "Profit Margin",
                "formula": f"{col_lower['profit']} / {col_lower['sales']}",
                "operands": [col_lower['profit'], col_lower['sales']],
                "operator": "/"
            }
        return metrics

    def _extract_column_metadata(self) -> Dict[str, Any]:
        """Extracts per-column metadata (dtype, sample values, null counts, unique counts)."""
        col_meta = {}
        if self.df is not None and not self.df.empty:
            for col in self.df.columns:
                series = self.df[col]
                col_meta[str(col)] = {
                    "name": str(col),
                    "dtype": str(series.dtype),
                    "unique_count": int(series.nunique(dropna=True)),
                    "null_count": int(series.isna().sum()),
                    "sample_values": series.dropna().head(5).astype(str).tolist()
                }
        return col_meta

    def to_dict(self) -> Dict[str, Any]:
        """Returns standard dict representation for full backward compatibility."""
        return {
            "dataset_id": self.dataset_id,
            "version": self.version,
            "filename": self.filename,
            "stored_filename": self.stored_filename,
            "processed_filename": self.processed_filename,
            "file_type": self.file_type,
            "file_size": self.file_size,
            "status": self.status,
            "data": self.df,
            "duckdb_connection": self.duckdb_connection,
            "metadata": self.metadata,
            "schema": self.schema,
            "profile": self.profile,
            "cleaning_report": self.cleaning_report,
            "value_index": self.value_index,
            "geo_hierarchy": self.geo_hierarchy,
            "derived_metrics": self.derived_metrics,
            "column_metadata": self.column_metadata,
            "created_at": self.created_at,
            "last_used_at": self.last_used_at,
            "result": {
                "dataset_id": self.dataset_id,
                "original_filename": self.filename,
                "processed_filename": self.processed_filename,
                "schema": self.schema,
                "profile": self.profile,
                "metadata": self.metadata,
                "cleaning_report": self.cleaning_report
            }
        }

    # Dict-like subscript interface for full backwards-compatibility
    def __getitem__(self, item: str) -> Any:
        return self.to_dict()[item]

    def get(self, item: str, default: Any = None) -> Any:
        return self.to_dict().get(item, default)

    def __contains__(self, item: str) -> bool:
        return item in self.to_dict()

    def keys(self):
        return self.to_dict().keys()

    def items(self):
        return self.to_dict().items()

    def values(self):
        return self.to_dict().values()


from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
PROCESSED_DIR = BASE_DIR / "uploads" / "processed"
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)


class DatasetRuntimeManager:
    """
    Centralized Dataset Runtime Manager.
    Manages in-memory cache of DatasetRuntime objects with thread-safe loading locks,
    LRU eviction, cache invalidation, and version tracking.
    """

    _instance = None
    _instance_lock = threading.Lock()

    def __init__(self):
        self._cache: Dict[str, DatasetRuntime] = {}
        self._loading_locks: Dict[str, threading.Lock] = {}
        self._global_lock = threading.Lock()
        self.max_cache_size: int = int(os.getenv("DATASET_RUNTIME_CACHE_SIZE", "20"))

    @classmethod
    def get_instance(cls) -> "DatasetRuntimeManager":
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = DatasetRuntimeManager()
        return cls._instance

    def _get_loading_lock(self, dataset_id: str) -> threading.Lock:
        with self._global_lock:
            if dataset_id not in self._loading_locks:
                self._loading_locks[dataset_id] = threading.Lock()
            return self._loading_locks[dataset_id]

    def is_dataset_loaded(self, dataset_id: str) -> bool:
        clean_id = str(dataset_id).strip()
        with self._global_lock:
            return clean_id in self._cache

    def get_dataset_runtime(self, dataset_id: str, updated_at: Optional[str] = None) -> Optional[DatasetRuntime]:
        """
        Looks up dataset runtime in cache. If found and version matches, returns existing runtime.
        If version changed or missing, returns None.
        """
        if not dataset_id or not str(dataset_id).strip():
            return None
        clean_id = str(dataset_id).strip()

        with self._global_lock:
            runtime = self._cache.get(clean_id)
            if runtime is not None:
                if updated_at and runtime.version != str(updated_at):
                    logger.info(f"[DatasetRuntime] Cache stale for dataset={clean_id} (cached={runtime.version}, expected={updated_at})")
                    return None
                runtime.touch()
                logger.info(f"[DatasetRuntime] CACHE HIT dataset={clean_id}")
                logger.info(f"[DatasetRuntime] Reusing runtime")
                return runtime

        return None

    def load_dataset_runtime(
        self,
        dataset_id: str,
        chat_id: Optional[str] = None,
        existing_df: Optional[pd.DataFrame] = None,
        existing_info: Optional[Dict[str, Any]] = None
    ) -> Optional[DatasetRuntime]:
        """
        Loads dataset runtime once: from memory, provided DataFrame, local disk, or Supabase Storage.
        Uses per-dataset lock to prevent concurrent duplicate loading.
        """
        if not dataset_id or not str(dataset_id).strip():
            return None
        clean_id = str(dataset_id).strip()

        lock = self._get_loading_lock(clean_id)
        with lock:
            # Re-check cache inside lock (in case another thread loaded it while waiting)
            with self._global_lock:
                existing_runtime = self._cache.get(clean_id)
                if existing_runtime is not None:
                    existing_runtime.touch()
                    logger.info(f"[DatasetRuntime] CACHE HIT dataset={clean_id}")
                    logger.info(f"[DatasetRuntime] Reusing runtime")
                    return existing_runtime

            logger.info(f"[DatasetRuntime] CACHE MISS dataset={clean_id}")
            t0 = time.perf_counter()

            # If existing DataFrame & info are passed directly (e.g. from file upload pipeline)
            if existing_df is not None and existing_info is not None:
                version_str = str(existing_info.get("updated_at") or time.time())
                schema = existing_info.get("schema") or existing_info.get("result", {}).get("schema") or infer_schema(existing_df)
                profile = existing_info.get("profile") or existing_info.get("result", {}).get("profile") or profile_dataset(existing_df, schema)
                metadata = existing_info.get("metadata") or existing_info.get("result", {}).get("metadata") or {
                    "dataset_id": clean_id,
                    "row_count": len(existing_df),
                    "column_count": len(existing_df.columns)
                }
                cleaning_report = existing_info.get("cleaning_report") or {"clean_dataset": True, "rows_removed": 0}

                # Save local disk copy for ultra-fast restart reloads
                try:
                    local_pq = PROCESSED_DIR / f"{clean_id}.parquet"
                    existing_df.to_parquet(local_pq, index=False)
                except Exception:
                    pass

                runtime = DatasetRuntime(
                    dataset_id=clean_id,
                    version=version_str,
                    df=existing_df,
                    schema=schema,
                    profile=profile,
                    metadata=metadata,
                    cleaning_report=cleaning_report,
                    filename=existing_info.get("filename"),
                    stored_filename=existing_info.get("stored_filename"),
                    processed_filename=existing_info.get("processed_filename"),
                    file_type=existing_info.get("file_type", "csv"),
                    file_size=existing_info.get("file_size", 0),
                    status=existing_info.get("status", "processed")
                )
                self._store_in_cache(clean_id, runtime)
                duration = time.perf_counter() - t0
                logger.info(f"[DatasetRuntime] Runtime created in {duration:.3f}s")
                return runtime

            # Check local disk cache first (< 20ms load)
            local_parquet = PROCESSED_DIR / f"{clean_id}.parquet"
            local_csv = PROCESSED_DIR / f"{clean_id}.csv"

            disk_df = None
            if local_parquet.exists():
                try:
                    disk_df = pd.read_parquet(local_parquet)
                except Exception:
                    pass
            elif local_csv.exists():
                try:
                    disk_df = pd.read_csv(local_csv)
                except Exception:
                    pass

            # Query Supabase PostgreSQL datasets metadata for schema/version
            try:
                with get_supabase_connection() as conn:
                    with conn.cursor(cursor_factory=RealDictCursor) as cur:
                        cur.execute("SELECT * FROM public.datasets WHERE id = %s;", (clean_id,))
                        ds_row = cur.fetchone()

                        if ds_row:
                            version_str = str(ds_row.get("updated_at") or time.time())
                            df = disk_df

                            if df is None:
                                logger.info(f"[DatasetRuntime] Downloading dataset={clean_id} from Supabase Storage...")
                                storage_service = SupabaseStorageService()
                                cur.execute(
                                    """
                                    SELECT storage_path FROM public.dataset_files 
                                    WHERE dataset_id = %s AND file_role = 'processed'
                                    ORDER BY created_at DESC LIMIT 1;
                                    """,
                                    (clean_id,)
                                )
                                file_row = cur.fetchone()

                                content_bytes = None
                                if file_row and file_row.get("storage_path"):
                                    content_bytes = storage_service.download_file(file_row["storage_path"])

                                if not content_bytes:
                                    cur.execute(
                                        """
                                        SELECT storage_path FROM public.dataset_files 
                                        WHERE dataset_id = %s 
                                        ORDER BY created_at DESC LIMIT 1;
                                        """,
                                        (clean_id,)
                                    )
                                    fallback_row = cur.fetchone()
                                    if fallback_row:
                                        content_bytes = storage_service.download_file(fallback_row["storage_path"])

                                if content_bytes:
                                    try:
                                        df = pd.read_parquet(io.BytesIO(content_bytes))
                                    except Exception:
                                        try:
                                            df = pd.read_csv(io.BytesIO(content_bytes))
                                        except Exception:
                                            df = pd.read_excel(io.BytesIO(content_bytes))

                                    # Save local parquet copy for future sub-second reloads
                                    if df is not None:
                                        try:
                                            df.to_parquet(local_parquet, index=False)
                                        except Exception:
                                            pass

                            if df is not None:
                                schema = _parse_json_field(ds_row.get("schema_json")) or infer_schema(df)
                                profile = _parse_json_field(ds_row.get("profile_json")) or profile_dataset(df, schema)
                                metadata = _parse_json_field(ds_row.get("metadata_json")) or {
                                    "dataset_id": clean_id,
                                    "original_filename": ds_row.get("filename"),
                                    "processed_filename": ds_row.get("processed_filename"),
                                    "row_count": len(df),
                                    "column_count": len(df.columns)
                                }
                                cleaning_report = _parse_json_field(ds_row.get("cleaning_report_json")) or {"clean_dataset": True, "rows_removed": 0}

                                runtime = DatasetRuntime(
                                    dataset_id=clean_id,
                                    version=version_str,
                                    df=df,
                                    schema=schema,
                                    profile=profile,
                                    metadata=metadata,
                                    cleaning_report=cleaning_report,
                                    filename=ds_row.get("filename"),
                                    stored_filename=ds_row.get("stored_filename"),
                                    processed_filename=ds_row.get("processed_filename"),
                                    file_type=ds_row.get("file_type", "csv"),
                                    file_size=ds_row.get("file_size", 0),
                                    status=ds_row.get("status", "processed")
                                )
                                self._store_in_cache(clean_id, runtime)
                                duration = time.perf_counter() - t0
                                logger.info(f"[DatasetRuntime] Runtime created in {duration:.3f}s")
                                return runtime
            except Exception as e:
                logger.error(f"Error loading dataset {clean_id}: {e}")

            return None

    def _store_in_cache(self, dataset_id: str, runtime: DatasetRuntime) -> None:
        with self._global_lock:
            # Check for LRU eviction if cache size exceeded
            while len(self._cache) >= self.max_cache_size and dataset_id not in self._cache:
                lru_id = min(self._cache.keys(), key=lambda k: self._cache[k].last_used_at)
                logger.info(f"[DatasetRuntime] Cache limit ({self.max_cache_size}) reached. Evicting LRU dataset: {lru_id}")
                evicted = self._cache.pop(lru_id)
                try:
                    evicted.duckdb_connection.close()
                except Exception:
                    pass

            self._cache[dataset_id] = runtime

    def release_dataset_runtime(self, dataset_id: str) -> bool:
        """Unloads dataset from cache."""
        clean_id = str(dataset_id).strip()
        with self._global_lock:
            if clean_id in self._cache:
                runtime = self._cache.pop(clean_id)
                try:
                    runtime.duckdb_connection.close()
                except Exception:
                    pass
                logger.info(f"[DatasetRuntime] Released runtime for dataset={clean_id}")
                return True
        return False

    def invalidate_dataset_runtime(self, dataset_id: str) -> bool:
        """Invalidates cache when dataset changes, is reprocessed, or deleted."""
        return self.release_dataset_runtime(dataset_id)

    def clear_all(self) -> None:
        """Clears all cached dataset runtimes."""
        with self._global_lock:
            for runtime in self._cache.values():
                try:
                    runtime.duckdb_connection.close()
                except Exception:
                    pass
            self._cache.clear()
            logger.info("[DatasetRuntime] Cleared all cached runtimes.")


def _parse_json_field(val: Any) -> Any:
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


# Convenience functions
def get_dataset_runtime(dataset_id: str) -> Optional[DatasetRuntime]:
    return DatasetRuntimeManager.get_instance().get_dataset_runtime(dataset_id)


def load_dataset_runtime(
    dataset_id: str,
    chat_id: Optional[str] = None,
    existing_df: Optional[pd.DataFrame] = None,
    existing_info: Optional[Dict[str, Any]] = None
) -> Optional[DatasetRuntime]:
    return DatasetRuntimeManager.get_instance().load_dataset_runtime(
        dataset_id, chat_id=chat_id, existing_df=existing_df, existing_info=existing_info
    )


def release_dataset_runtime(dataset_id: str) -> bool:
    return DatasetRuntimeManager.get_instance().release_dataset_runtime(dataset_id)


def invalidate_dataset_runtime(dataset_id: str) -> bool:
    return DatasetRuntimeManager.get_instance().invalidate_dataset_runtime(dataset_id)


def is_dataset_loaded(dataset_id: str) -> bool:
    return DatasetRuntimeManager.get_instance().is_dataset_loaded(dataset_id)
