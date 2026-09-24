import sys
import json
from pathlib import Path
import pandas as pd
import numpy as np
import pytest

# Ensure backend root is in sys.path for relative package imports
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from file_processing.schema_inference import infer_schema
from file_processing.data_profiler import profile_dataset, DataProfilerError

def test_superstore_data_profiling():
    """Test 1 — Superstore-like dataset profiling"""
    data = {
        "Row ID": [1, 2, 3, 4],
        "Order ID": ["CA-2016-152156", "CA-2016-152156", "CA-2016-138688", "US-2015-108966"],
        "Order Date": ["2016-11-08", "2016-11-08", "2016-06-12", "2015-10-11"],
        "Ship Mode": ["Second Class", "Second Class", "Second Class", "Standard Class"],
        "Region": ["South", "South", "West", "South"],
        "Product Name": ["Bush Somerset Bookcase", "Hon Deluxe Fabric Chair", "Self-Adhesive Labels", "Bretford Conference Table"],
        "Sales": [261.96, 731.94, 14.62, 957.5775],
        "Quantity": [2, 3, 2, 5],
        "Discount": [0.0, 0.0, 0.0, 0.45],
        "Profit": [41.9136, 219.582, 6.8714, -383.031]
    }
    df = pd.DataFrame(data)
    schema = infer_schema(df)
    profile = profile_dataset(df, schema, top_n=3)

    assert profile["row_count"] == 4
    assert profile["column_count"] == 10
    assert profile["duplicate_row_count"] == 0
    assert profile["duplicate_row_percentage"] == 0.0

    # Quality Summary
    quality = profile["quality"]
    assert quality["total_missing_values"] == 0
    assert quality["columns_with_missing_values"] == 0
    assert quality["duplicate_rows"] == 0
    assert quality["columns_with_all_null_values"] == 0

    # Check Numeric Column Stats (Sales)
    sales_prof = next(c for c in profile["columns"] if c["name"] == "Sales")
    assert sales_prof["semantic_type"] == "numeric"
    stats = sales_prof["statistics"]
    assert stats["count"] == 4
    assert stats["min"] == 14.62
    assert stats["max"] == 957.5775
    assert stats["sum"] == round(261.96 + 731.94 + 14.62 + 957.5775, 4)

    # Check Categorical Top Values (Region)
    region_prof = next(c for c in profile["columns"] if c["name"] == "Region")
    assert region_prof["semantic_type"] == "categorical"
    assert "top_values" in region_prof
    top_region = region_prof["top_values"][0]
    assert top_region["value"] == "South"
    assert top_region["count"] == 3

    # Check Date Column Stats (Order Date)
    date_prof = next(c for c in profile["columns"] if c["name"] == "Order Date")
    assert date_prof["semantic_type"] == "date"
    assert date_prof["statistics"]["min_date"].startswith("2015-10-11")
    assert date_prof["statistics"]["max_date"].startswith("2016-11-08")

    # Check Text Column Stats (Product Name)
    text_prof = next(c for c in profile["columns"] if c["name"] == "Product Name")
    assert text_prof["semantic_type"] == "text"
    assert "average_length" in text_prof["statistics"]
    assert text_prof["statistics"]["minimum_length"] > 0

    # Ensure profile is 100% JSON serializable
    json_output = json.dumps(profile)
    assert len(json_output) > 0

def test_missing_values_and_all_null_column():
    """Test 2 — Missing value counts, null percentages, and all-null column handling"""
    data = {
        "col_clean": [10, 20, 30, 40],
        "col_missing": [1.5, np.nan, 3.5, np.nan],
        "col_all_null": [np.nan, None, np.nan, None]
    }
    df = pd.DataFrame(data)
    schema = infer_schema(df)
    profile = profile_dataset(df, schema)

    missing_prof = next(c for c in profile["columns"] if c["name"] == "col_missing")
    assert missing_prof["missing_count"] == 2
    assert missing_prof["missing_percentage"] == 50.0
    assert missing_prof["non_null_count"] == 2

    all_null_prof = next(c for c in profile["columns"] if c["name"] == "col_all_null")
    assert all_null_prof["all_null"] is True
    assert all_null_prof["missing_count"] == 4
    assert all_null_prof["missing_percentage"] == 100.0
    assert all_null_prof["statistics"] is None

    assert profile["quality"]["total_missing_values"] == 6
    assert profile["quality"]["columns_with_missing_values"] == 2
    assert profile["quality"]["columns_with_all_null_values"] == 1

def test_duplicate_row_detection():
    """Test 3 — Dataset duplicate row calculation"""
    data = {
        "col1": [1, 2, 1, 2, 3],
        "col2": ["A", "B", "A", "B", "C"]
    }
    df = pd.DataFrame(data)
    schema = infer_schema(df)
    profile = profile_dataset(df, schema)

    assert profile["row_count"] == 5
    assert profile["duplicate_row_count"] == 2
    assert profile["duplicate_row_percentage"] == 40.0

def test_constant_column():
    """Test 4 — Constant column detection (all values identical)"""
    data = {
        "constant_col": ["Online", "Online", "Online", "Online"],
        "var_col": [1, 2, 3, 4]
    }
    df = pd.DataFrame(data)
    schema = infer_schema(df)
    profile = profile_dataset(df, schema)

    const_prof = next(c for c in profile["columns"] if c["name"] == "constant_col")
    assert const_prof["constant"] is True
    assert const_prof["unique_count"] == 1

def test_invalid_input_error_handling():
    """Test 5 — Invalid input exception handling"""
    with pytest.raises(DataProfilerError) as exc1:
        profile_dataset(None, {})
    assert "Input must be a valid Pandas DataFrame" in str(exc1.value)

    with pytest.raises(DataProfilerError) as exc2:
        profile_dataset(pd.DataFrame({"a": [1]}), None)
    assert "Input schema must be a valid dictionary" in str(exc2.value)

if __name__ == "__main__":
    test_superstore_data_profiling()
    test_missing_values_and_all_null_column()
    test_duplicate_row_detection()
    test_constant_column()
    test_invalid_input_error_handling()
    print("\n✅ ALL DATA PROFILER TESTS PASSED SUCCESSFULLY!")
