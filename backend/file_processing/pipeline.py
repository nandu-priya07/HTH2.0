import logging
from pathlib import Path
from typing import Dict, Any, Optional
import pandas as pd

from .file_loader import load_file
from .schema_inference import infer_schema
from .data_profiler import profile_dataset
from .data_cleaner import clean_dataset

logger = logging.getLogger(__name__)

class FileProcessingError(Exception):
    """Custom exception raised when any stage of the file processing pipeline fails."""
    def __init__(self, stage: str, error: str):
        self.stage = stage
        self.error = error
        stage_str = stage.upper()
        if not stage_str.endswith("_ERROR"):
            stage_str = f"{stage_str}_ERROR"
        super().__init__(f"[{stage_str}] {error}")

def validate_processing_result(cleaned_df: pd.DataFrame, schema: Dict[str, Any]) -> None:
    """
    Final validation check ensuring the processed DataFrame is non-empty,
    has unique column names, and maps cleanly to the standardized schema.
    """
    if cleaned_df is None or not isinstance(cleaned_df, pd.DataFrame):
        raise ValueError("Processed data is not a valid Pandas DataFrame.")

    if len(cleaned_df.columns) == 0:
        raise ValueError("Processed DataFrame has 0 columns.")

    if not cleaned_df.columns.is_unique:
        raise ValueError("Processed DataFrame contains duplicate column names.")

    schema_col_names = {col["name"] for col in schema.get("columns", [])}
    for col in cleaned_df.columns:
        if col not in schema_col_names:
            raise ValueError(f"Column '{col}' in cleaned DataFrame is missing from standardized schema definition.")

def process_file(
    file_path: str | Path,
    dataset_id: Optional[str] = None,
    original_filename: Optional[str] = None,
    remove_exact_duplicates: bool = True,
    processed_dir: Optional[str | Path] = None
) -> Dict[str, Any]:
    """
    Executes the complete Person 1 file-processing pipeline:
    1. File Loading (file_loader)
    2. Schema Inference (schema_inference)
    3. Data Profiling (data_profiler)
    4. Data Cleaning (data_cleaner)
    5. Final Result Validation
    6. Processed Storage Persistence (save to backend/uploads/processed/<dataset_id>.csv)

    :param file_path: Path to stored raw file under backend/uploads/raw/
    :param dataset_id: Unique UUID dataset identifier
    :param original_filename: Original filename uploaded by user
    :param remove_exact_duplicates: Whether to remove exact duplicate rows
    :param processed_dir: Optional custom directory path for saving processed CSV
    :return: Complete Standardized Dataset Processing Result dictionary
    :raises FileProcessingError: If any pipeline stage or validation or storage fails
    """
    path_obj = Path(file_path)
    if not dataset_id:
        dataset_id = path_obj.stem
    if not original_filename:
        original_filename = path_obj.name

    if processed_dir is None:
        target_processed_dir = Path(__file__).resolve().parent.parent / "uploads" / "processed"
    else:
        target_processed_dir = Path(processed_dir)

    logger.info(f"Starting pipeline processing for dataset_id='{dataset_id}', file='{original_filename}'")

    # Stage 1: Load File
    try:
        raw_df = load_file(path_obj)
    except Exception as e:
        logger.error(f"Stage 1 File Loader failed: {e}")
        raise FileProcessingError(stage="file_load", error=str(e))

    # Stage 2: Schema Inference
    try:
        schema = infer_schema(raw_df)
    except Exception as e:
        logger.error(f"Stage 2 Schema Inference failed: {e}")
        raise FileProcessingError(stage="schema_inference", error=str(e))

    # Stage 3: Data Profiling
    try:
        profile = profile_dataset(raw_df, schema)
    except Exception as e:
        logger.error(f"Stage 3 Data Profiler failed: {e}")
        raise FileProcessingError(stage="profile", error=str(e))

    # Stage 4: Data Cleaning
    try:
        cleaned_result = clean_dataset(raw_df, schema, profile, remove_exact_duplicates=remove_exact_duplicates)
    except Exception as e:
        logger.error(f"Stage 4 Data Cleaner failed: {e}")
        raise FileProcessingError(stage="cleaning", error=str(e))

    cleaned_df = cleaned_result["data"]
    updated_schema = cleaned_result["schema"]
    cleaning_report = cleaned_result["cleaning_report"]

    # Stage 5: Final Result Validation
    try:
        validate_processing_result(cleaned_df, updated_schema)
    except Exception as e:
        logger.error(f"Final Validation failed: {e}")
        raise FileProcessingError(stage="validation", error=str(e))

    # Stage 6: Processed Storage Persistence
    processed_filename = f"{dataset_id}.csv"
    processed_file_path = target_processed_dir / processed_filename

    try:
        target_processed_dir.mkdir(parents=True, exist_ok=True)
        cleaned_df.to_csv(processed_file_path, index=False)
    except Exception as e:
        logger.error(f"Stage 6 Processed Storage failed: {e}")
        raise FileProcessingError(stage="PROCESSED_STORAGE_ERROR", error=str(e))

    metadata = {
        "dataset_id": dataset_id,
        "original_filename": original_filename,
        "processed_filename": processed_filename,
        "row_count": len(cleaned_df),
        "column_count": len(cleaned_df.columns),
        "original_row_count": cleaned_result["metadata"]["original_row_count"],
        "duplicate_rows_removed": cleaned_result["metadata"]["duplicate_rows_removed"]
    }

    pipeline_result = {
        "success": True,
        "dataset_id": dataset_id,
        "original_filename": original_filename,
        "processed_filename": processed_filename,
        "data": cleaned_df,
        "metadata": metadata,
        "schema": updated_schema,
        "profile": profile,
        "cleaning_report": cleaning_report
    }

    logger.info(f"Pipeline processing complete for dataset_id='{dataset_id}'. Saved to '{processed_file_path}'. Final Rows: {len(cleaned_df)}, Cols: {len(cleaned_df.columns)}")
    return pipeline_result
