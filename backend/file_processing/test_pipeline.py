import os
import sys
import json
import tempfile
from pathlib import Path
import pandas as pd
import pytest

# Ensure backend root is in sys.path for relative package imports
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from file_processing.pipeline import process_file, validate_processing_result, FileProcessingError

def test_superstore_pipeline_end_to_end():
    """Test 1 — Superstore dataset end-to-end processing"""
    data = {
        "Row ID": [1, 2, 3, 4],
        "Order ID": ["CA-2016-152156", "CA-2016-152156", "CA-2016-138688", "US-2015-108966"],
        "Order Date": ["2016-11-08", "2016-11-08", "2016-06-12", "2015-10-11"],
        "Ship Date": ["2016-11-11", "2016-11-11", "2016-06-16", "2015-10-18"],
        "Ship Mode": ["Second Class", "Second Class", "Second Class", "Standard Class"],
        "Customer ID": ["CG-12520", "CG-12520", "DV-13045", "SO-20335"],
        "Customer Name": [" Claire Gute ", "Claire Gute", "Darrin Van Huff", "Sean O'Donnell"],
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
        "Sales": ["$261.96", "$731.94", "$14.62", "$957.57"],
        "Quantity": [2, 3, 2, 5],
        "Discount": [0.0, 0.0, 0.0, 0.45],
        "Profit": [41.9136, 219.582, 6.8714, -383.031]
    }
    sample_df = pd.DataFrame(data)
    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        sample_df.to_excel(tmp_path, index=False)

        result = process_file(
            file_path=tmp_path,
            dataset_id="test_superstore_uuid",
            original_filename="superstore.xlsx"
        )

        assert result["success"] is True
        assert result["dataset_id"] == "test_superstore_uuid"
        assert result["original_filename"] == "superstore.xlsx"

        cleaned_df = result["data"]
        assert isinstance(cleaned_df, pd.DataFrame)
        assert len(cleaned_df) == 4
        assert len(cleaned_df.columns) == 21

        # Check column standardization
        assert "row_id" in cleaned_df.columns
        assert "order_id" in cleaned_df.columns
        assert "order_date" in cleaned_df.columns
        assert "customer_name" in cleaned_df.columns
        assert "country_region" in cleaned_df.columns
        assert "sales" in cleaned_df.columns

        # Check types
        assert pd.api.types.is_numeric_dtype(cleaned_df["sales"])
        assert pd.api.types.is_datetime64_any_dtype(cleaned_df["order_date"])

        # Check metadata, schema, profile, cleaning_report presence
        assert result["metadata"]["row_count"] == 4
        assert result["metadata"]["column_count"] == 21
        assert "columns" in result["schema"]
        assert "quality" in result["profile"]
        assert "cleaning_report" in result

        # Verify JSON serializability of metadata, schema, profile, report
        serializable_meta = {
            "metadata": result["metadata"],
            "schema": result["schema"],
            "profile": result["profile"],
            "cleaning_report": result["cleaning_report"]
        }
        json_output = json.dumps(serializable_meta)
        assert len(json_output) > 0
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

def test_dataset_a_sales():
    """Test 2 — Dataset A (Sales CSV)"""
    content = "order_date,region,sales,profit\n2026-01-01,North,1200.50,340.00\n2026-01-02,South,800.00,120.00\n"
    with tempfile.NamedTemporaryFile(suffix=".csv", mode="w", delete=False, encoding="utf-8") as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    try:
        result = process_file(tmp_path, dataset_id="ds_a")
        df = result["data"]
        assert list(df.columns) == ["order_date", "region", "sales", "profit"]
        assert pd.api.types.is_numeric_dtype(df["sales"])
        assert pd.api.types.is_datetime64_any_dtype(df["order_date"])
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

def test_dataset_b_employees():
    """Test 3 — Dataset B (Employees CSV with leading zeros in identifier)"""
    content = "employee_id,name,age,department,salary,joining_date\n00101,Alice,28,Engineering,75000,2024-01-10\n00102,Bob,34,Sales,62000,2023-05-15\n"
    with tempfile.NamedTemporaryFile(suffix=".csv", mode="w", delete=False, encoding="utf-8") as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    try:
        result = process_file(tmp_path, dataset_id="ds_b")
        df = result["data"]
        assert list(df.columns) == ["employee_id", "name", "age", "department", "salary", "joining_date"]
        # Verify leading zero preservation in employee_id identifier
        assert df["employee_id"].iloc[0] == "00101"
        assert pd.api.types.is_numeric_dtype(df["salary"])
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

def test_dataset_c_products():
    """Test 4 — Dataset C (Products CSV with boolean and text)"""
    content = "product_code,country,rating,available,description\nP001,USA,4.8,True,High performance laptop with sleek metallic body\nP002,UK,4.2,False,Compact tablet\n"
    with tempfile.NamedTemporaryFile(suffix=".csv", mode="w", delete=False, encoding="utf-8") as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    try:
        result = process_file(tmp_path, dataset_id="ds_c")
        df = result["data"]
        assert "available" in df.columns
        assert pd.api.types.is_numeric_dtype(df["rating"])
        assert df["product_code"].iloc[0] == "P001"
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

def test_pipeline_error_handling():
    """Test 5 — Error handling across pipeline stages"""
    # Unsupported extension
    with tempfile.NamedTemporaryFile(suffix=".pdf", mode="w", delete=False) as tmp:
        tmp.write("dummy pdf")
        pdf_path = tmp.name

    try:
        with pytest.raises(FileProcessingError) as exc1:
            process_file(pdf_path)
        assert exc1.value.stage == "file_load"
        assert "Unsupported file type" in exc1.value.error
    finally:
        if os.path.exists(pdf_path):
            os.remove(pdf_path)

    # Missing file
    with pytest.raises(FileProcessingError) as exc2:
        process_file("nonexistent_path_999.csv")
    assert exc2.value.stage == "file_load"

    # Empty 0-byte file
    with tempfile.NamedTemporaryFile(suffix=".csv", mode="w", delete=False) as tmp:
        empty_path = tmp.name

    try:
        with pytest.raises(FileProcessingError) as exc3:
            process_file(empty_path)
        assert exc3.value.stage == "file_load"
    finally:
        if os.path.exists(empty_path):
            os.remove(empty_path)

def test_raw_file_unmodified():
    """Test 6 — Verify original raw stored file is unmodified on disk"""
    content = "id,value\n1, 100 \n2, 200 \n"
    with tempfile.NamedTemporaryFile(suffix=".csv", mode="w", delete=False, encoding="utf-8") as tmp:
        tmp.write(content)
        raw_path = tmp.name

    try:
        process_file(raw_path, dataset_id="raw_unmodified_test")
        # Verify file content on disk is identical to original raw content
        with open(raw_path, "r", encoding="utf-8") as f:
            disk_content = f.read()
        assert disk_content == content
    finally:
        if os.path.exists(raw_path):
            os.remove(raw_path)
        processed_file = Path(__file__).resolve().parent.parent / "uploads" / "processed" / "raw_unmodified_test.csv"
        if processed_file.exists():
            processed_file.unlink()

def test_processed_storage_persistence():
    """Test 7 — Verify processed CSV file persistence with correct metadata and schema"""
    content = "Employee ID,Full Name,Salary\n00101, Alice Smith ,75000\n00102, Bob Jones ,80000\n"
    with tempfile.NamedTemporaryFile(suffix=".csv", mode="w", delete=False, encoding="utf-8") as tmp:
        tmp.write(content)
        raw_path = tmp.name

    ds_id = "test_persistence_uuid_123"
    processed_dir = Path(__file__).resolve().parent.parent / "uploads" / "processed"
    processed_file = processed_dir / f"{ds_id}.csv"

    try:
        result = process_file(raw_path, dataset_id=ds_id, original_filename="emp.csv")

        # Verify result structure and metadata
        assert result["success"] is True
        assert result["processed_filename"] == f"{ds_id}.csv"
        assert result["metadata"]["processed_filename"] == f"{ds_id}.csv"
        assert result["metadata"]["dataset_id"] == ds_id
        assert result["metadata"]["original_filename"] == "emp.csv"

        # Verify processed file exists on disk
        assert processed_file.exists()

        # Read processed file and check contents & identifier leading zeros
        proc_df = pd.read_csv(processed_file, dtype=str)
        assert list(proc_df.columns) == ["employee_id", "full_name", "salary"]
        assert proc_df["employee_id"].iloc[0] == "00101"
        assert proc_df["full_name"].iloc[0] == "Alice Smith"
    finally:
        if os.path.exists(raw_path):
            os.remove(raw_path)
        if processed_file.exists():
            processed_file.unlink()

def test_failed_processing_does_not_create_processed_file():
    """Test 8 — Failed processing does not create a file in uploads/processed/"""
    ds_id = "failed_ds_uuid_999"
    processed_dir = Path(__file__).resolve().parent.parent / "uploads" / "processed"
    processed_file = processed_dir / f"{ds_id}.csv"

    # 0-byte file causes Stage 1 FileLoaderError
    with tempfile.NamedTemporaryFile(suffix=".csv", mode="w", delete=False) as tmp:
        empty_path = tmp.name

    try:
        with pytest.raises(FileProcessingError):
            process_file(empty_path, dataset_id=ds_id)

        assert not processed_file.exists()
    finally:
        if os.path.exists(empty_path):
            os.remove(empty_path)
        if processed_file.exists():
            processed_file.unlink()

def test_processed_storage_error_stage(tmp_path):
    """Test 9 — Exception during processed file save raises FileProcessingError with PROCESSED_STORAGE_ERROR"""
    content = "id,value\n1,100\n"
    raw_path = tmp_path / "test_raw.csv"
    raw_path.write_text(content, encoding="utf-8")

    # Create a file with the name target_dir so target_dir.mkdir fails with OSError
    unwritable_dir = tmp_path / "blocked_dir"
    unwritable_dir.write_text("blocking file")

    with pytest.raises(FileProcessingError) as exc_info:
        process_file(raw_path, dataset_id="ds_storage_fail", processed_dir=unwritable_dir)

    assert "PROCESSED_STORAGE" in exc_info.value.stage.upper()
    assert "PROCESSED_STORAGE_ERROR" in str(exc_info.value)

if __name__ == "__main__":
    test_superstore_pipeline_end_to_end()
    test_dataset_a_sales()
    test_dataset_b_employees()
    test_dataset_c_products()
    test_pipeline_error_handling()
    test_raw_file_unmodified()
    test_processed_storage_persistence()
    test_failed_processing_does_not_create_processed_file()
    print("\n✅ ALL PIPELINE END-TO-END TESTS PASSED SUCCESSFULLY!")
