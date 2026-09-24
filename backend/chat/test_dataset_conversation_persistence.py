"""
Unit & Integration Tests for Persistent Conversation-Dataset Association
and Restart Resilience according to Specification.
"""

import os
import io
import shutil
import tempfile
from pathlib import Path
import pytest
import pandas as pd
from fastapi.testclient import TestClient

from chat.database import initialize_database, get_db_connection
from chat.sqlite_repository import SqliteChatRepository
from chat.service import ChatService
from storage.dataset_manager import DATASET_REGISTRY, get_or_load_dataset, register_dataset
import main
from main import app


@pytest.fixture
def isolated_env(tmp_path, monkeypatch):
    """
    Sets up isolated SQLite DB, raw upload directory, and processed upload directory.
    """
    db_file = tmp_path / "test_app.db"
    raw_dir = tmp_path / "raw"
    proc_dir = tmp_path / "processed"
    raw_dir.mkdir(parents=True, exist_ok=True)
    proc_dir.mkdir(parents=True, exist_ok=True)

    # Monkeypatch storage paths
    import storage.dataset_manager as dm
    import routes.upload as ru
    import file_processing.pipeline as fpp

    monkeypatch.setattr(dm, "RAW_DIR", raw_dir)
    monkeypatch.setattr(dm, "PROCESSED_DIR", proc_dir)
    monkeypatch.setattr(ru, "RAW_DIR", raw_dir)
    monkeypatch.setattr(ru, "UPLOAD_DIR", raw_dir)
    monkeypatch.setattr(ru, "PROCESSED_DIR", proc_dir)
    monkeypatch.setenv("CHAT_DATABASE_PATH", str(db_file))

    # Clear in-memory registry
    dm.DATASET_REGISTRY.clear()

    initialize_database(db_file)
    repo = SqliteChatRepository(db_path=db_file)
    service = ChatService(repository=repo)

    import routes.query as rq
    from analyst.models import LLMResponse

    def mock_process_query(question, schema, profile, df, dataset_id):
        return LLMResponse(
            type="direct_answer",
            answer=f"Processed query on dataset {dataset_id}"
        )

    monkeypatch.setattr(rq, "process_query_with_llm", mock_process_query)

    import chat
    monkeypatch.setattr(chat, "_chat_service_instance", service)

    client = TestClient(app)
    return {
        "db_file": db_file,
        "raw_dir": raw_dir,
        "proc_dir": proc_dir,
        "repo": repo,
        "service": service,
        "client": client,
        "dm": dm
    }


def create_mock_csv_file(name: str, content: str = "subject,grade,score\nMath,A,95\nPhysics,B,82\nChemistry,A,91"):
    """Helper creating an in-memory file for multipart upload."""
    return io.BytesIO(content.encode("utf-8"))


# ----------------------------------------------------------------------
# TEST 1 & 2: Upload file in conversation -> Dataset associated & queried
# ----------------------------------------------------------------------

def test_1_and_2_upload_and_query_with_associated_dataset(isolated_env):
    client = isolated_env["client"]
    service = isolated_env["service"]

    # 1. Create Conversation
    conv = client.post("/api/conversations", json={"title": "Grade Study"}).json()
    cid = conv["id"]
    assert conv["dataset_id"] is None

    # 2. Upload file associated with conversation
    file_bytes = create_mock_csv_file("students.csv")
    upload_res = client.post(
        "/api/upload",
        files={"file": ("students.csv", file_bytes, "text/csv")},
        data={"conversation_id": cid}
    )
    assert upload_res.status_code == 200
    upload_data = upload_res.json()
    assert upload_data["success"] is True
    ds_id = upload_data["dataset_id"]

    # Verify conversation now permanently references dataset_id
    updated_conv = client.get(f"/api/conversations/{cid}").json()
    assert updated_conv["dataset_id"] == ds_id

    # 3. Query conversation WITHOUT passing dataset_id in the payload
    # Backend must automatically resolve dataset_id from conversation.dataset_id
    query_res = client.post(
        "/api/query",
        json={"question": "list the A grade count in each subject", "conversation_id": cid}
    )
    assert query_res.status_code == 200
    query_data = query_res.json()
    assert query_data["conversation_id"] == cid
    assert query_data["status"] != "no_dataset"
    assert query_data.get("dataset_id") == ds_id


# ----------------------------------------------------------------------
# TEST 3 & 4: Application restart simulation -> Dataset auto-restored from disk
# ----------------------------------------------------------------------

def test_3_and_4_restart_persistence_and_subsequent_query(isolated_env, monkeypatch):
    client = isolated_env["client"]
    service = isolated_env["service"]
    dm = isolated_env["dm"]

    # Step 1: Create chat and upload dataset
    conv = client.post("/api/conversations", json={"title": "Sales Chat"}).json()
    cid = conv["id"]

    csv_data = "region,sales,profit\nNorth,500,50\nSouth,700,70\nEast,400,40"
    file_bytes = create_mock_csv_file("sales_data.csv", csv_data)
    upload_res = client.post(
        "/api/upload",
        files={"file": ("sales_data.csv", file_bytes, "text/csv")},
        data={"conversation_id": cid}
    )
    ds_id = upload_res.json()["dataset_id"]

    # Step 2: SIMULATE APPLICATION RESTART
    # Clear in-memory cache completely
    dm.DATASET_REGISTRY.clear()
    assert len(dm.DATASET_REGISTRY) == 0

    # Verify dataset exists on disk in processed folder
    processed_file = isolated_env["proc_dir"] / f"{ds_id}.csv"
    assert processed_file.exists()

    # Step 3: Re-query the conversation after restart without passing dataset_id
    query_res = client.post(
        "/api/query",
        json={"question": "what is the total sales?", "conversation_id": cid}
    )
    assert query_res.status_code == 200
    query_data = query_res.json()

    # Must NOT ask to upload a dataset; must have auto-loaded sales_data from disk
    assert query_data["status"] != "no_dataset"
    assert query_data.get("dataset_id") == ds_id
    assert ds_id in dm.DATASET_REGISTRY  # Cache re-populated from disk


# ----------------------------------------------------------------------
# TEST 5: Multiple conversations maintain independent datasets
# ----------------------------------------------------------------------

def test_5_multiple_conversations_independent_datasets(isolated_env):
    client = isolated_env["client"]

    # Create Chat A with Dataset A
    conv_a = client.post("/api/conversations", json={"title": "Chat A - Students"}).json()
    cid_a = conv_a["id"]
    file_a = create_mock_csv_file("students.csv", "student_name,score\nAlice,90\nBob,80")
    ds_a = client.post("/api/upload", files={"file": ("students.csv", file_a, "text/csv")}, data={"conversation_id": cid_a}).json()["dataset_id"]

    # Create Chat B with Dataset B
    conv_b = client.post("/api/conversations", json={"title": "Chat B - Products"}).json()
    cid_b = conv_b["id"]
    file_b = create_mock_csv_file("products.csv", "product_name,price\nLaptop,1200\nPhone,800")
    ds_b = client.post("/api/upload", files={"file": ("products.csv", file_b, "text/csv")}, data={"conversation_id": cid_b}).json()["dataset_id"]

    assert ds_a != ds_b

    # Verify Chat A uses Dataset A
    res_a = client.post("/api/query", json={"question": "show scores", "conversation_id": cid_a})
    assert res_a.json().get("dataset_id") == ds_a

    # Verify Chat B uses Dataset B
    res_b = client.post("/api/query", json={"question": "show prices", "conversation_id": cid_b})
    assert res_b.json().get("dataset_id") == ds_b


# ----------------------------------------------------------------------
# TEST 6: Dataset replacement inside same conversation
# ----------------------------------------------------------------------

def test_6_dataset_replacement_in_conversation(isolated_env):
    client = isolated_env["client"]

    conv = client.post("/api/conversations", json={"title": "Evolving Chat"}).json()
    cid = conv["id"]

    # Attach Dataset 1
    f1 = create_mock_csv_file("v1.csv", "col1,val\nA,10")
    ds1_id = client.post("/api/upload", files={"file": ("v1.csv", f1, "text/csv")}, data={"conversation_id": cid}).json()["dataset_id"]

    # Replace with Dataset 2
    f2 = create_mock_csv_file("v2.csv", "col2,val\nB,20")
    ds2_id = client.post("/api/upload", files={"file": ("v2.csv", f2, "text/csv")}, data={"conversation_id": cid}).json()["dataset_id"]

    assert ds1_id != ds2_id

    # Verify conversation updated to Dataset 2
    conv_updated = client.get(f"/api/conversations/{cid}").json()
    assert conv_updated["dataset_id"] == ds2_id

    # Verify Dataset 1 was NOT deleted
    assert (isolated_env["proc_dir"] / f"{ds1_id}.csv").exists()
    assert (isolated_env["proc_dir"] / f"{ds2_id}.csv").exists()


# ----------------------------------------------------------------------
# TEST 7: Conversation without dataset -> Requests dataset upload
# ----------------------------------------------------------------------

def test_7_conversation_without_dataset_requests_upload(isolated_env):
    client = isolated_env["client"]

    # Create empty conversation with no dataset
    conv = client.post("/api/conversations", json={"title": "Empty Chat"}).json()
    cid = conv["id"]
    assert conv["dataset_id"] is None

    # Query without dataset
    res = client.post("/api/query", json={"question": "What is the average sales?", "conversation_id": cid})
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "no_dataset"
    assert "upload a CSV or Excel dataset first" in data["text"]
    assert data["dataset_id"] is None
