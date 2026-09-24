import sys
from pathlib import Path
import pandas as pd
import numpy as np
import pytest

# Ensure backend root is in sys.path for relative package imports
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from file_processing.schema_inference import infer_schema, SchemaInferenceError

def test_superstore_dataset_schema():
    """Test 1 — Superstore-like dataset schema inference"""
    data = {
        "Row ID": [1, 2, 3, 4],
        "Order ID": ["CA-2016-152156", "CA-2016-152156", "CA-2016-138688", "US-2015-108966"],
        "Order Date": ["2016-11-08", "2016-11-08", "2016-06-12", "2015-10-11"],
        "Ship Date": ["2016-11-11", "2016-11-11", "2016-06-16", "2015-10-18"],
        "Ship Mode": ["Second Class", "Second Class", "Second Class", "Standard Class"],
        "Customer ID": ["CG-12520", "CG-12520", "DV-13045", "SO-20335"],
        "Customer Name": ["Claire Gute", "Claire Gute", "Darrin Van Huff", "Sean O'Donnell"],
        "Segment": ["Consumer", "Consumer", "Corporate", "Consumer"],
        "Country/Region": ["United States", "United States", "United States", "United States"],
        "City": ["Henderson", "Henderson", "Los Angeles", "Fort Lauderdale"],
        "State/Province": ["Kentucky", "Kentucky", "California", "Florida"],
        "Postal Code": [42420, 42420, 90036, 33311],
        "Region": ["South", "South", "West", "South"],
        "Product ID": ["FUR-BO-10001798", "FUR-CH-10000454", "OFF-LA-10000240", "FUR-TA-10000577"],
        "Category": ["Furniture", "Furniture", "Office Supplies", "Furniture"],
        "Sub-Category": ["Bookcases", "Chairs", "Labels", "Tables"],
        "Product Name": ["Bush Somerset Bookcase", "Hon Deluxe Fabric Chair", "Self-Adhesive Labels", "Bretford Conference Table"],
        "Sales": [261.96, 731.94, 14.62, 957.5775],
        "Quantity": [2, 3, 2, 5],
        "Discount": [0.0, 0.0, 0.0, 0.45],
        "Profit": [41.9136, 219.582, 6.8714, -383.031]
    }
    df = pd.DataFrame(data)
    schema = infer_schema(df)

    assert schema["row_count"] == 4
    assert schema["column_count"] == 21

    # Verify grouped column lists
    assert "Sales" in schema["numeric_columns"]
    assert "Profit" in schema["numeric_columns"]
    assert "Quantity" in schema["numeric_columns"]
    assert "Discount" in schema["numeric_columns"]

    assert "Order Date" in schema["date_columns"]
    assert "Ship Date" in schema["date_columns"]

    assert "Order ID" in schema["identifier_columns"]
    assert "Customer ID" in schema["identifier_columns"]
    assert "Product ID" in schema["identifier_columns"]

    assert "Region" in schema["categorical_columns"]
    assert "Category" in schema["categorical_columns"]
    assert "Ship Mode" in schema["categorical_columns"]

def test_custom_employee_dataset():
    """Test 2 — Completely different arbitrary dataset"""
    data = {
        "employee_name": ["Alice", "Bob", "Charlie", "David"],
        "age": [25, 30, 35, 40],
        "salary": [50000.0, 60000.0, 75000.0, 90000.0],
        "department": ["Engineering", "Sales", "Engineering", "HR"],
        "joining_date": ["2024-01-10", "2024-02-15", "2023-05-20", "2022-11-01"]
    }
    df = pd.DataFrame(data)
    schema = infer_schema(df)

    assert "age" in schema["numeric_columns"]
    assert "salary" in schema["numeric_columns"]
    assert "joining_date" in schema["date_columns"]
    assert "department" in schema["categorical_columns"]

def test_missing_values_nullability():
    """Test 3 — Nullability and missing count detection"""
    data = {
        "col_clean": [1, 2, 3, 4],
        "col_with_nulls": [10.5, np.nan, 30.2, np.nan]
    }
    df = pd.DataFrame(data)
    schema = infer_schema(df)

    clean_meta = next(c for c in schema["columns"] if c["name"] == "col_clean")
    null_meta = next(c for c in schema["columns"] if c["name"] == "col_with_nulls")

    assert clean_meta["nullable"] is False
    assert clean_meta["missing_count"] == 0

    assert null_meta["nullable"] is True
    assert null_meta["missing_count"] == 2

def test_boolean_detection():
    """Test 4 — Boolean column inference"""
    data = {
        "is_active": [True, False, True, False],
        "has_discount": ["Yes", "No", "Yes", "No"]
    }
    df = pd.DataFrame(data)
    schema = infer_schema(df)

    assert "is_active" in schema["boolean_columns"]
    assert "has_discount" in schema["boolean_columns"]

def test_identifier_detection():
    """Test 5 — Identifier patterns (IDs, codes, SKUs)"""
    data = {
        "customer_id": ["CUST-001", "CUST-002", "CUST-003", "CUST-004"],
        "product_code": ["P001", "P002", "P003", "P004"],
        "quantity": [10, 20, 15, 30]  # Quantity must remain numeric!
    }
    df = pd.DataFrame(data)
    schema = infer_schema(df)

    assert "customer_id" in schema["identifier_columns"]
    assert "product_code" in schema["identifier_columns"]
    assert "quantity" in schema["numeric_columns"]

def test_all_null_empty_column():
    """Test 6 — Column with all null values"""
    data = {
        "valid_col": [1, 2, 3],
        "all_nulls": [np.nan, None, np.nan]
    }
    df = pd.DataFrame(data)
    schema = infer_schema(df)

    null_meta = next(c for c in schema["columns"] if c["name"] == "all_nulls")
    assert null_meta["semantic_type"] == "unknown"

def test_invalid_input_error_handling():
    """Test 7 — Invalid input and empty DataFrame error handling"""
    with pytest.raises(SchemaInferenceError) as exc1:
        infer_schema(None)
    assert "Input must be a valid Pandas DataFrame" in str(exc1.value)

    with pytest.raises(SchemaInferenceError) as exc2:
        infer_schema(pd.DataFrame())
    assert "Cannot infer schema for empty DataFrame" in str(exc2.value)

if __name__ == "__main__":
    test_superstore_dataset_schema()
    test_custom_employee_dataset()
    test_missing_values_nullability()
    test_boolean_detection()
    test_identifier_detection()
    test_all_null_empty_column()
    test_invalid_input_error_handling()
    print("\n✅ ALL SCHEMA INFERENCE TESTS PASSED SUCCESSFULLY!")
