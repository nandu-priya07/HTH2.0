import sys
import os
import tempfile
from pathlib import Path
import pandas as pd
import numpy as np
import pytest

# Ensure backend root is in sys.path for relative package imports
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from file_processing.file_loader import load_file
from file_processing.schema_inference import infer_schema
from file_processing.data_profiler import profile_dataset
from file_processing.data_cleaner import clean_dataset, DataCleanerError

def test_column_name_standardization():
    """Test 1 — Column-name standardization"""
    data = {
        "Customer Name": ["Alice"],
        "Country/Region": ["USA"],
        " State ": ["CA"]
    }
    df = pd.DataFrame(data)
    schema = infer_schema(df)
    profile = profile_dataset(df, schema)
    result = clean_dataset(df, schema, profile)

    cleaned_df = result["data"]
    assert list(cleaned_df.columns) == ["customer_name", "country_region", "state"]
    assert result["cleaning_report"]["column_renames"][0] == {"original": "Customer Name", "standardized": "customer_name"}

def test_whitespace_cleaning():
    """Test 2 — Whitespace cleaning"""
    data = {
        "customer_name": [" Alice ", " Bob", "Charlie "]
    }
    df = pd.DataFrame(data)
    schema = infer_schema(df)
    profile = profile_dataset(df, schema)
    result = clean_dataset(df, schema, profile)

    cleaned_df = result["data"]
    assert list(cleaned_df["customer_name"]) == ["Alice", "Bob", "Charlie"]
    assert result["cleaning_report"]["whitespace_values_cleaned"] == 3

def test_missing_value_normalization():
    """Test 3 — Missing-value normalization"""
    data = {
        "id": [1, 2, 3, 4, 5],
        "city": ["New York", "", "N/A", "null", "London"]
    }
    df = pd.DataFrame(data)
    schema = infer_schema(df)
    profile = profile_dataset(df, schema)
    result = clean_dataset(df, schema, profile, remove_exact_duplicates=True)

    cleaned_df = result["data"]
    assert len(cleaned_df) == 5
    assert cleaned_df["city"].isnull().sum() == 3
    assert result["cleaning_report"]["missing_values_normalized"] == 3

def test_numeric_conversion():
    """Test 4 — Numeric currency and comma formatting conversion"""
    data = {
        "sales": ["$1,200.50", "500", "2,000"]
    }
    df = pd.DataFrame(data)
    schema = infer_schema(df)
    profile = profile_dataset(df, schema)
    result = clean_dataset(df, schema, profile)

    cleaned_df = result["data"]
    assert pd.api.types.is_numeric_dtype(cleaned_df["sales"])
    assert list(cleaned_df["sales"]) == [1200.50, 500.0, 2000.0]

def test_invalid_numeric_conversion_to_nan():
    """Test 5 — Invalid numeric value conversion to NaN (not zero) + warning"""
    data = {
        "sales": ["100.0", "unknown", "200.0"]
    }
    df = pd.DataFrame(data)
    schema = infer_schema(df)
    profile = profile_dataset(df, schema)
    result = clean_dataset(df, schema, profile)

    cleaned_df = result["data"]
    assert pd.isna(cleaned_df["sales"].iloc[1])
    assert cleaned_df["sales"].iloc[1] != 0
    assert len(result["cleaning_report"]["warnings"]) > 0

def test_date_conversion():
    """Test 6 — Date string parsing and conversion"""
    data = {
        "order_date": ["2023-01-03", "2023-01-04"]
    }
    df = pd.DataFrame(data)
    schema = infer_schema(df)
    profile = profile_dataset(df, schema)
    result = clean_dataset(df, schema, profile)

    cleaned_df = result["data"]
    assert pd.api.types.is_datetime64_any_dtype(cleaned_df["order_date"])

def test_invalid_date_conversion_to_nat():
    """Test 7 — Invalid date conversion to NaT + warning"""
    data = {
        "order_date": ["2023-01-03", "INVALID_DATE"]
    }
    df = pd.DataFrame(data)
    schema = infer_schema(df)
    profile = profile_dataset(df, schema)
    result = clean_dataset(df, schema, profile)

    cleaned_df = result["data"]
    assert pd.isna(cleaned_df["order_date"].iloc[1])
    assert len(result["cleaning_report"]["warnings"]) > 0

def test_identifier_preservation():
    """Test 8 — Identifier preservation (leading zeros retained)"""
    data = {
        "customer_id": ["00123", "00124"]
    }
    df = pd.DataFrame(data)
    schema = infer_schema(df)
    profile = profile_dataset(df, schema)
    result = clean_dataset(df, schema, profile)

    cleaned_df = result["data"]
    assert list(cleaned_df["customer_id"]) == ["00123", "00124"]

def test_duplicate_row_removal():
    """Test 9 — Exact duplicate row removal"""
    data = {
        "name": ["Alice", "Bob", "Alice", "Bob", "Charlie"],
        "dept": ["Sales", "HR", "Sales", "HR", "IT"]
    }
    df = pd.DataFrame(data)
    schema = infer_schema(df)
    profile = profile_dataset(df, schema)
    result = clean_dataset(df, schema, profile, remove_exact_duplicates=True)

    cleaned_df = result["data"]
    assert len(cleaned_df) == 3
    assert result["metadata"]["duplicate_rows_removed"] == 2

def test_full_pipeline_integration():
    """Test 10 & 11 — Complete Person 1 Pipeline Integration (Load -> Infer -> Profile -> Clean)"""
    content = "Customer Name,Sales,Order Date\n Alice ,$100,2023-01-03\n Bob ,$200,2023-01-04\n"
    with tempfile.NamedTemporaryFile(suffix=".csv", mode="w", delete=False, encoding="utf-8") as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    try:
        df_raw = load_file(tmp_path)
        schema = infer_schema(df_raw)
        profile = profile_dataset(df_raw, schema)
        result = clean_dataset(df_raw, schema, profile)

        cleaned_df = result["data"]
        assert list(cleaned_df.columns) == ["customer_name", "sales", "order_date"]
        assert cleaned_df.iloc[0]["customer_name"] == "Alice"
        assert cleaned_df.iloc[0]["sales"] == 100.0
        assert "metadata" in result
        assert "cleaning_report" in result
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

def test_invalid_input_error_handling():
    """Test 12 — Invalid input handling"""
    with pytest.raises(DataCleanerError) as exc1:
        clean_dataset(None, {}, {})
    assert "Input must be a valid Pandas DataFrame" in str(exc1.value)

    with pytest.raises(DataCleanerError) as exc2:
        clean_dataset(pd.DataFrame({"a": [1]}), None, {})
    assert "Input schema must be a valid dictionary" in str(exc2.value)

if __name__ == "__main__":
    test_column_name_standardization()
    test_whitespace_cleaning()
    test_missing_value_normalization()
    test_numeric_conversion()
    test_invalid_numeric_conversion_to_nan()
    test_date_conversion()
    test_invalid_date_conversion_to_nat()
    test_identifier_preservation()
    test_duplicate_row_removal()
    test_full_pipeline_integration()
    test_invalid_input_error_handling()
    print("\n✅ ALL DATA CLEANER TESTS PASSED SUCCESSFULLY!")
