import os
import sys
import tempfile
from pathlib import Path
import pandas as pd
import pytest

# Ensure backend root is in sys.path for relative package imports
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from file_processing.file_loader import load_file, FileLoaderError

def test_load_csv():
    """Test 1 — Valid CSV file loading"""
    content = "id,name,sales\n1,Alice,100\n2,Bob,200\n3,Charlie,300\n"
    with tempfile.NamedTemporaryFile(suffix=".csv", mode="w", delete=False, encoding="utf-8") as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    try:
        df = load_file(tmp_path)
        assert isinstance(df, pd.DataFrame)
        assert df.shape == (3, 3)
        assert list(df.columns) == ["id", "name", "sales"]
        assert df.iloc[0]["name"] == "Alice"
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

def test_load_xlsx():
    """Test 2 — Valid XLSX Excel file loading"""
    data = {
        "id": [1, 2, 3],
        "name": ["Alice", "Bob", "Charlie"],
        "sales": [100, 200, 300]
    }
    sample_df = pd.DataFrame(data)
    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        sample_df.to_excel(tmp_path, index=False)
        df = load_file(tmp_path)
        assert isinstance(df, pd.DataFrame)
        assert df.shape == (3, 3)
        assert list(df.columns) == ["id", "name", "sales"]
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

def test_unsupported_extension():
    """Test 3 — Unsupported file format (.pdf)"""
    with tempfile.NamedTemporaryFile(suffix=".pdf", mode="w", delete=False) as tmp:
        tmp.write("dummy pdf content")
        tmp_path = tmp.name

    try:
        with pytest.raises(FileLoaderError) as exc_info:
            load_file(tmp_path)
        assert "Unsupported file type" in str(exc_info.value)
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

def test_missing_file():
    """Test 4 — Nonexistent file path"""
    missing_path = "nonexistent_file_path_12345.csv"
    with pytest.raises(FileLoaderError) as exc_info:
        load_file(missing_path)
    assert "File does not exist" in str(exc_info.value)

def test_empty_file():
    """Test 5 — Zero-byte empty file"""
    with tempfile.NamedTemporaryFile(suffix=".csv", mode="w", delete=False) as tmp:
        tmp_path = tmp.name  # Empty file 0 bytes

    try:
        with pytest.raises(FileLoaderError) as exc_info:
            load_file(tmp_path)
        assert "The uploaded file is empty" in str(exc_info.value)
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

def test_arbitrary_columns():
    """Test 6 — Dataset with arbitrary custom columns"""
    content = "product_code,region,revenue,transaction_date\nP001,South,1000,2026-01-01\nP002,North,2000,2026-01-02\n"
    with tempfile.NamedTemporaryFile(suffix=".csv", mode="w", delete=False, encoding="utf-8") as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    try:
        df = load_file(tmp_path)
        assert df.shape == (2, 4)
        assert list(df.columns) == ["product_code", "region", "revenue", "transaction_date"]
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

def test_uploaded_raw_file_if_exists():
    """Test 7 — Load existing raw file in backend/uploads/raw/ if present"""
    raw_dir = Path(__file__).parent.parent / "uploads" / "raw"
    if raw_dir.exists():
        raw_files = list(raw_dir.glob("*"))
        for f in raw_files:
            if f.suffix.lower() in [".csv", ".xlsx", ".xls"] and f.stat().st_size > 0:
                print(f"\nTesting actual uploaded raw file: {f.name}")
                df = load_file(f)
                assert isinstance(df, pd.DataFrame)
                print(f"Loaded {f.name}: shape={df.shape}, columns={list(df.columns)[:5]}")

if __name__ == "__main__":
    test_load_csv()
    test_load_xlsx()
    test_unsupported_extension()
    test_missing_file()
    test_empty_file()
    test_arbitrary_columns()
    test_uploaded_raw_file_if_exists()
    print("\n✅ ALL FILE LOADER TESTS PASSED SUCCESSFULLY!")
