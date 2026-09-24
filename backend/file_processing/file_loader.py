import os
import logging
from pathlib import Path
import pandas as pd

logger = logging.getLogger(__name__)

ALLOWED_EXTENSIONS = {".csv", ".xlsx", ".xls"}

class FileLoaderError(Exception):
    """Custom exception raised when file loading or validation fails."""
    pass

def load_file(file_path: str | Path) -> pd.DataFrame:
    """
    Validates and loads an uploaded CSV or Excel file into a raw Pandas DataFrame.

    :param file_path: Path to the stored raw file (.csv, .xlsx, .xls)
    :return: Unmodified raw pd.DataFrame
    :raises FileLoaderError: If file validation or parsing fails
    """
    path_obj = Path(file_path)

    # 1. Validate file exists
    if not path_obj.exists():
        logger.error(f"File does not exist: {file_path}")
        raise FileLoaderError(f"File does not exist: {file_path}")

    # 2. Validate path points to a regular file
    if not path_obj.is_file():
        logger.error(f"Path is not a valid file: {file_path}")
        raise FileLoaderError("Path is not a valid file.")

    # 3. Validate extension
    ext = path_obj.suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        logger.error(f"Unsupported file extension: {ext} for {file_path}")
        raise FileLoaderError(f"Unsupported file type: {ext}. Supported formats: CSV, XLSX, XLS.")

    # 4. Validate file size is non-zero
    if path_obj.stat().st_size == 0:
        logger.error(f"File is 0 bytes: {file_path}")
        raise FileLoaderError("The uploaded file is empty.")

    logger.info(f"Loading dataset: {path_obj.name}")
    logger.info(f"File type: {ext.lstrip('.')}")

    # 5. Load file using Pandas according to extension (using dtype=str to preserve raw string fidelity like leading zeros)
    df = None
    if ext == ".csv":
        try:
            # Try loading with standard UTF-8 encoding first
            df = pd.read_csv(path_obj, dtype=str, encoding="utf-8")
        except UnicodeDecodeError:
            try:
                # Fallback encoding for legacy Windows CSV files
                logger.warning(f"UTF-8 decode failed for {file_path}, retrying with latin1 encoding")
                df = pd.read_csv(path_obj, dtype=str, encoding="latin1")
            except Exception as e:
                logger.error(f"Failed to parse CSV file with fallback encoding: {e}")
                raise FileLoaderError("Unable to parse CSV file.")
        except Exception as e:
            logger.error(f"Unable to parse CSV file {file_path}: {e}")
            raise FileLoaderError("Unable to parse CSV file.")
    elif ext in (".xlsx", ".xls"):
        try:
            df = pd.read_excel(path_obj, dtype=str)
        except Exception as e:
            logger.error(f"Unable to parse Excel file {file_path}: {e}")
            raise FileLoaderError("Unable to parse Excel file.")

    # 6. Validate that returned DataFrame contains usable data
    if df is None or df.empty or len(df.columns) == 0:
        logger.error(f"DataFrame loaded from {file_path} contains no usable tabular data")
        raise FileLoaderError("The file does not contain any usable tabular data.")

    logger.info(f"Successfully loaded dataset: Rows={len(df)}, Columns={len(df.columns)}")

    return df
