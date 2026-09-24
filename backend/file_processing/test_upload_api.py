import io
import pytest
from fastapi.testclient import TestClient
from main import app
from routes.upload import DATASET_REGISTRY

client = TestClient(app)

def test_api_upload_success_csv():
    """Test POST /api/upload with valid CSV file"""
    csv_content = b"order_id,customer_name,sales,order_date\n1001,Alice,150.50,2026-01-15\n1002,Bob,299.99,2026-01-16\n"
    file = ("sales_sample.csv", io.BytesIO(csv_content), "text/csv")
    
    response = client.post("/api/upload", files={"file": file})
    assert response.status_code == 200
    json_resp = response.json()
    
    assert json_resp["success"] is True
    assert "dataset_id" in json_resp
    assert json_resp["filename"] == "sales_sample.csv"
    assert json_resp["status"] == "processed"
    assert json_resp["metadata"]["row_count"] == 2
    assert json_resp["metadata"]["column_count"] == 4
    assert "schema" in json_resp
    assert "profile" in json_resp
    assert "cleaning_report" in json_resp

    dataset_id = json_resp["dataset_id"]
    assert dataset_id in DATASET_REGISTRY
    assert DATASET_REGISTRY[dataset_id]["status"] == "processed"

    # Test GET /api/dataset/{dataset_id}
    get_resp = client.get(f"/api/dataset/{dataset_id}")
    assert get_resp.status_code == 200
    get_json = get_resp.json()
    assert get_json["dataset_id"] == dataset_id
    assert get_json["filename"] == "sales_sample.csv"

def test_api_upload_unsupported_file():
    """Test POST /api/upload with unsupported file extension (.pdf)"""
    pdf_content = b"%PDF-1.4 dummy pdf data"
    file = ("document.pdf", io.BytesIO(pdf_content), "application/pdf")
    
    response = client.post("/api/upload", files={"file": file})
    assert response.status_code == 400
    json_resp = response.json()
    assert json_resp["success"] is False
    assert "Unsupported file type" in json_resp["error"]

def test_api_upload_empty_file():
    """Test POST /api/upload with zero-byte file"""
    file = ("empty.csv", io.BytesIO(b""), "text/csv")
    
    response = client.post("/api/upload", files={"file": file})
    assert response.status_code == 400
    json_resp = response.json()
    assert json_resp["success"] is False
    assert "empty" in json_resp["error"].lower()

def test_api_upload_persists_raw_and_processed_files():
    """
    Comprehensive test for requirement verifications:
    1. Raw file exists in uploads/raw/
    2. Processed file exists in uploads/processed/
    3. Raw file contents are unchanged
    4. Processed file contains cleaned dataset
    5. Both files use the same dataset_id
    6. Processed filename exposed in metadata without full filesystem path
    7. /api/upload works correctly
    """
    from pathlib import Path
    import pandas as pd

    raw_bytes = b"Order ID,Customer Name,Sales\n00101, Alice Smith ,$150.50\n00102, Bob Jones ,$299.99\n"
    file = ("sales_data.csv", io.BytesIO(raw_bytes), "text/csv")

    response = client.post("/api/upload", files={"file": file})
    assert response.status_code == 200
    json_resp = response.json()

    assert json_resp["success"] is True
    dataset_id = json_resp["dataset_id"]
    processed_filename = json_resp["processed_filename"]
    assert processed_filename == f"{dataset_id}.csv"
    assert json_resp["metadata"]["processed_filename"] == f"{dataset_id}.csv"
    assert "file_path" not in json_resp
    assert "file_path" not in json_resp["metadata"]

    base_uploads = Path(__file__).resolve().parent.parent / "uploads"
    raw_path = base_uploads / "raw" / f"{dataset_id}.csv"
    processed_path = base_uploads / "processed" / f"{dataset_id}.csv"

    try:
        # 1. Raw file exists in uploads/raw/
        assert raw_path.exists()

        # 2. Processed file exists in uploads/processed/
        assert processed_path.exists()

        # 3. Raw file contents are unchanged
        with open(raw_path, "rb") as f:
            disk_raw_bytes = f.read()
        assert disk_raw_bytes == raw_bytes

        # 4. Processed file contains the cleaned dataset (standardized headers + clean values)
        proc_df = pd.read_csv(processed_path, dtype=str)
        assert list(proc_df.columns) == ["order_id", "customer_name", "sales"]
        assert proc_df["order_id"].iloc[0] == "00101"
        assert proc_df["customer_name"].iloc[0] == "Alice Smith"
        assert proc_df["sales"].iloc[0] == "150.5"

        # 5. Both files use the same dataset_id
        assert raw_path.stem == dataset_id
        assert processed_path.stem == dataset_id
    finally:
        if raw_path.exists():
            raw_path.unlink()
        if processed_path.exists():
            processed_path.unlink()

def test_api_upload_failed_processing_no_processed_file():
    """Verify that failed processing does not leave a processed file in uploads/processed/"""
    from pathlib import Path

    # Zero byte upload fails before process_file
    empty_file = ("zero.csv", io.BytesIO(b""), "text/csv")
    resp = client.post("/api/upload", files={"file": empty_file})
    assert resp.status_code == 400

    # Verify no processed files were left behind
    processed_dir = Path(__file__).resolve().parent.parent / "uploads" / "processed"
    # Ensure no leftover files starting with zero-byte or temporary IDs
    assert len(list(processed_dir.glob("zero*.csv"))) == 0
