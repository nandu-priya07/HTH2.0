import re
import logging
import pandas as pd
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

class SchemaInferenceError(Exception):
    """Custom exception raised when schema inference fails."""
    pass

NUMERIC_NAME_KEYWORDS = [
    "sales", "revenue", "price", "cost", "amount", "profit", "discount",
    "income", "salary", "age", "quantity", "score", "total", "rate", "fee", "balance"
]

def infer_schema(df: pd.DataFrame) -> Dict[str, Any]:
    """
    Dynamically inspects a Pandas DataFrame and infers physical dtypes,
    logical semantic types, nullability, unique counts, and column groupings.

    :param df: Input raw pd.DataFrame
    :return: Structured schema dictionary
    :raises SchemaInferenceError: If input is invalid or empty
    """
    if df is None or not isinstance(df, pd.DataFrame):
        logger.error("Schema inference received invalid input (not a DataFrame)")
        raise SchemaInferenceError("Input must be a valid Pandas DataFrame.")

    if df.empty or len(df.columns) == 0:
        logger.error("Cannot infer schema for empty DataFrame")
        raise SchemaInferenceError("Cannot infer schema for empty DataFrame.")

    row_count = len(df)
    column_count = len(df.columns)

    columns_meta: List[Dict[str, Any]] = []
    numeric_columns: List[str] = []
    categorical_columns: List[str] = []
    date_columns: List[str] = []
    identifier_columns: List[str] = []
    boolean_columns: List[str] = []
    text_columns: List[str] = []

    for col in df.columns:
        col_str = str(col)
        series = df[col]
        dtype_str = str(series.dtype)
        missing_count = int(series.isnull().sum())
        nullable = missing_count > 0
        unique_count = int(series.nunique(dropna=True))
        non_null_series = series.dropna()

        semantic_type, confidence = _infer_column_semantic_type(
            col_name=col_str,
            series=series,
            non_null_series=non_null_series,
            row_count=row_count,
            unique_count=unique_count
        )

        col_dict = {
          "name": col_str,
          "original_name": col_str,
          "dtype": dtype_str,
          "semantic_type": semantic_type,
          "nullable": nullable,
          "unique_count": unique_count,
          "missing_count": missing_count,
          "inference_confidence": round(confidence, 2)
        }
        columns_meta.append(col_dict)

        # Categorize column into grouped lists
        if semantic_type == "numeric":
            numeric_columns.append(col_str)
        elif semantic_type == "categorical":
            categorical_columns.append(col_str)
        elif semantic_type == "date":
            date_columns.append(col_str)
        elif semantic_type == "identifier":
            identifier_columns.append(col_str)
        elif semantic_type == "boolean":
            boolean_columns.append(col_str)
        elif semantic_type == "text":
            text_columns.append(col_str)

    schema = {
        "row_count": row_count,
        "column_count": column_count,
        "columns": columns_meta,
        "numeric_columns": numeric_columns,
        "categorical_columns": categorical_columns,
        "date_columns": date_columns,
        "identifier_columns": identifier_columns,
        "boolean_columns": boolean_columns,
        "text_columns": text_columns
    }

    logger.info(f"Schema inference completed successfully: {column_count} columns processed.")
    return schema


def _infer_column_semantic_type(
    col_name: str,
    series: pd.Series,
    non_null_series: pd.Series,
    row_count: int,
    unique_count: int
) -> tuple[str, float]:
    """
    Helper function to infer semantic type and confidence score for a single column.
    """
    lower_name = col_name.lower().strip()

    # 1. Handle All-Null / Empty Series
    if len(non_null_series) == 0 or unique_count == 0:
        return "unknown", 1.0

    # 2. Boolean Check
    if pd.api.types.is_bool_dtype(series):
        return "boolean", 1.0

    if unique_count <= 2:
        val_set = {str(val).strip().lower() for val in non_null_series.head(50)}
        bool_candidates = {"true", "false", "1", "0", "yes", "no", "y", "n", "t", "f"}
        if val_set and val_set.issubset(bool_candidates):
            return "boolean", 0.95

    # 3. Postal / ZIP Code Check (Must NOT be classified as numeric to avoid avg zip code)
    if any(p in lower_name for p in ["postal", "zip", "zipcode", "zip_code", "store_code"]):
        return "categorical", 0.95

    # 4. Date / Datetime Check
    if pd.api.types.is_datetime64_any_dtype(series):
        return "date", 1.0

    date_name_hints = ["date", "_date", "time", "timestamp", "dob", "created_at", "updated_at", "joining_date", "transaction_date"]
    has_date_hint = any(hint in lower_name for hint in date_name_hints)

    # Test date parsing for string / object or formatted columns
    if not pd.api.types.is_numeric_dtype(series) or has_date_hint:
        sample_vals = non_null_series.head(100)
        if sample_vals.dtype == object or has_date_hint:
            try:
                parsed = pd.to_datetime(sample_vals, errors="coerce", format="mixed")
                parsed_success_ratio = parsed.notnull().sum() / len(sample_vals) if len(sample_vals) > 0 else 0
                threshold = 0.50 if has_date_hint else 0.80
                if parsed_success_ratio >= threshold:
                    conf = 0.98 if has_date_hint else 0.88
                    return "date", conf
            except Exception:
                pass

    # 5. Identifier Check
    id_name_hints = ["id", "_id", "code", "key", "uuid", "sku", "row_id", "row id", "order_id", "customer_id", "product_id"]
    non_id_words = ["quantity", "count", "total", "amount", "revenue", "sales", "profit", "discount", "price", "cost", "age", "income", "salary"]
    name_words = ["name", "title", "description", "comment", "review", "text", "notes", "summary"]

    is_id_name = any(re.search(rf"\b{re.escape(h)}\b", lower_name) or lower_name.endswith(f"_{h}") or lower_name.startswith(f"{h}_") or lower_name == h for h in id_name_hints)
    is_excluded_from_id = any(w in lower_name for w in non_id_words)
    is_name_or_text_col = any(w in lower_name for w in name_words)

    if is_id_name and not is_excluded_from_id and not is_name_or_text_col:
        return "identifier", 0.95

    uniqueness_ratio = unique_count / row_count if row_count > 0 else 0
    if uniqueness_ratio >= 0.85 and row_count >= 3 and not is_excluded_from_id and not is_name_or_text_col:
        str_sample = non_null_series.astype(str).head(20)
        has_code_pattern = str_sample.str.contains(r"^[A-Za-z0-9\-_]+$", regex=True).any()
        if has_code_pattern or lower_name.endswith("id") or "code" in lower_name:
            return "identifier", 0.90

    # 6. Numeric Check
    if pd.api.types.is_numeric_dtype(series):
        if "year" in lower_name and unique_count <= 20:
            return "numeric", 0.80
        return "numeric", 0.99

    # Check formatted numeric strings (e.g. "$1,200.50", "1,200", "500") or numeric column names
    is_numeric_name = any(w in lower_name for w in NUMERIC_NAME_KEYWORDS)
    str_sample = non_null_series.astype(str).head(50)
    cleaned_sample = str_sample.str.replace(r"[\$,\s]", "", regex=True)
    numeric_parsed = pd.to_numeric(cleaned_sample, errors="coerce")
    numeric_parsed_ratio = numeric_parsed.notnull().sum() / len(str_sample) if len(str_sample) > 0 else 0

    if is_numeric_name or numeric_parsed_ratio >= 0.80:
        return "numeric", 0.90

    # 7. Categorical vs Text Check for Object / String columns
    avg_str_len = str_sample.str.len().mean() if len(str_sample) > 0 else 0

    if is_name_or_text_col or avg_str_len > 25:
        return "text", 0.90

    if uniqueness_ratio <= 0.50 or unique_count <= 50:
        return "categorical", 0.90

    return "categorical", 0.80
