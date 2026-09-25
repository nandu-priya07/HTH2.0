"""
ValueIndexer module for low-latency dataset value indexing.
Indexes string, categorical, and geographic values per dataset,
enabling schema-aware fuzzy matching against dataset values.
Stored in memory and persisted via Supabase PostgreSQL.
"""

import logging
from typing import Dict, List, Any, Optional
import pandas as pd
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class IndexedValue(BaseModel):
    column: str
    normalized: str
    display: str
    frequency: int = 1


class DatasetValueIndex(BaseModel):
    dataset_id: str
    columns_indexed: List[str]
    indexed_values: List[IndexedValue]


_VALUE_INDEX_CACHE: Dict[str, DatasetValueIndex] = {}


class ValueIndexer:
    """
    Builds and caches lightweight, searchable value indexes for categorical/string/geographic dataset columns.
    """

    @staticmethod
    def build_index(dataset_id: str, df: pd.DataFrame, max_distinct_per_col: int = 250) -> DatasetValueIndex:
        if dataset_id in _VALUE_INDEX_CACHE:
            return _VALUE_INDEX_CACHE[dataset_id]

        indexed_list: List[IndexedValue] = []
        columns_indexed: List[str] = []

        if df is not None and not df.empty:
            sample_df = df.sample(n=50000, random_state=42) if len(df) > 50000 else df
            for col in sample_df.columns:
                series = sample_df[col].dropna()
                # Index object/string/categorical or low-cardinality columns
                if pd.api.types.is_object_dtype(series) or pd.api.types.is_string_dtype(series) or series.nunique() <= max_distinct_per_col:
                    val_counts = series.astype(str).str.strip().value_counts().head(max_distinct_per_col)
                    if not val_counts.empty:
                        columns_indexed.append(col)
                        for display_val, count in val_counts.items():
                            if not display_val or display_val.lower() in ("nan", "none", "null", ""):
                                continue
                            indexed_list.append(
                                IndexedValue(
                                    column=col,
                                    normalized=display_val.lower(),
                                    display=str(display_val),
                                    frequency=int(count)
                                )
                            )

        idx = DatasetValueIndex(
            dataset_id=dataset_id,
            columns_indexed=columns_indexed,
            indexed_values=indexed_list
        )
        _VALUE_INDEX_CACHE[dataset_id] = idx
        logger.info(f"Built value index for dataset {dataset_id}: {len(indexed_list)} unique values across {len(columns_indexed)} columns.")
        return idx

    @staticmethod
    def get_index(dataset_id: str) -> Optional[DatasetValueIndex]:
        return _VALUE_INDEX_CACHE.get(dataset_id)

    @staticmethod
    def set_index(dataset_id: str, index: DatasetValueIndex) -> None:
        _VALUE_INDEX_CACHE[dataset_id] = index
