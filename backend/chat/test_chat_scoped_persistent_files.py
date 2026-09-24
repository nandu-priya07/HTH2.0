"""
Acceptance Tests for Chat-Scoped Persistent Files, JSON Conversation Context, and Follow-up Context Resolution.
Covers all 5 Section 20 Acceptance Tests.
"""

import os
import io
import shutil
import tempfile
from pathlib import Path
from typing import List, Dict, Any, Optional
import pytest
import pandas as pd
from fastapi.testclient import TestClient

from chat import get_chat_service, ChatService
from chat.json_repository import JsonChatRepository
from storage.dataset_manager import DATASET_REGISTRY, get_or_load_dataset
from main import app


@pytest.fixture
def test_storage_env(tmp_path, monkeypatch):
    """
    Sets up isolated temporary chat storage directory for testing.
    """
    storage_chats = tmp_path / "storage" / "chats"
    storage_chats.mkdir(parents=True, exist_ok=True)

    # Monkeypatch storage directories
    import chat.json_repository as jr
    import routes.upload as ru
    import storage.dataset_manager as dm

    monkeypatch.setattr(jr, "STORAGE_CHATS_DIR", storage_chats)
    monkeypatch.setattr(ru, "STORAGE_CHATS_DIR", storage_chats)
    monkeypatch.setattr(dm, "CHATS_DIR", storage_chats)

    # Reset in-memory cache
    DATASET_REGISTRY.clear()

    json_repo = JsonChatRepository(storage_dir=storage_chats)
    service = ChatService(repository=json_repo)

    import chat
    monkeypatch.setattr(chat, "_chat_service_instance", service)

    client = TestClient(app)
    return {
        "storage_dir": storage_chats,
        "repo": json_repo,
        "service": service,
        "client": client
    }


def create_csv_bytes(header: str, rows: List[str]) -> io.BytesIO:
    content = header + "\n" + "\n".join(rows)
    return io.BytesIO(content.encode("utf-8"))


# ----------------------------------------------------------------------
# TEST 1: File persistence across server restart
# ----------------------------------------------------------------------

def test_acceptance_1_file_persistence(test_storage_env):
    client = test_storage_env["client"]
    service = test_storage_env["service"]
    storage_dir = test_storage_env["storage_dir"]

    # 1. Create Chat A
    create_res = client.post("/chats", json={"title": "Chat A - Grades"})
    assert create_res.status_code == 201
    chat_a_id = create_res.json()["id"]

    # 2. Upload SEM_V.csv to Chat A
    csv_bytes = create_csv_bytes(
        "regular,regular_1,regular_2,regular_3",
        ["O,B,A,O", "B,O,O,A", "A,B,B,O", "O,A,O,B"]
    )
    upload_res = client.post(
        f"/chats/{chat_a_id}/files",
        files={"file": ("SEM_V.csv", csv_bytes, "text/csv")}
    )
    assert upload_res.status_code == 200
    file_id = upload_res.json()["file_id"]

    # 3. Ask first question
    q1_res = client.post(
        f"/chats/{chat_a_id}/messages",
        json={"question": "visualize the O grade count in each subject"}
    )
    assert q1_res.status_code == 200
    assert q1_res.json()["status"] == "success"

    # 4. SIMULATE SERVER RESTART
    # Clear in-memory dictionary
    DATASET_REGISTRY.clear()
    assert len(DATASET_REGISTRY) == 0

    # Re-initialize ChatService from disk files
    new_repo = JsonChatRepository(storage_dir=storage_dir)
    new_service = ChatService(repository=new_repo)
    import chat
    chat._chat_service_instance = new_service

    # 5. Open Chat A
    get_chat_res = client.get(f"/chats/{chat_a_id}")
    assert get_chat_res.status_code == 200
    chat_data = get_chat_res.json()
    assert len(chat_data["files"]) == 1
    assert chat_data["files"][0]["file_id"] == file_id

    # 6. Ask another question after restart -> File must still be available
    q2_res = client.post(
        f"/chats/{chat_a_id}/messages",
        json={"question": "similarly for B grade"}
    )
    assert q2_res.status_code == 200
    assert q2_res.json()["status"] == "success"
    assert q2_res.json().get("dataset_id") == file_id


# ----------------------------------------------------------------------
# TEST 2: Follow-up query context resolution
# ----------------------------------------------------------------------

def test_acceptance_2_follow_up_query(test_storage_env):
    client = test_storage_env["client"]

    # Create Chat
    create_res = client.post("/chats", json={"title": "Grade Follow-up Test"})
    chat_id = create_res.json()["id"]

    # Upload file
    csv_bytes = create_csv_bytes(
        "regular,regular_1,regular_2,regular_3",
        ["O,B,A,O", "B,O,O,A", "A,B,B,O", "O,A,O,B"]
    )
    client.post(f"/chats/{chat_id}/files", files={"file": ("SEM_V.csv", csv_bytes, "text/csv")})

    # Query 1: visualize O grade count in each subject
    res1 = client.post(f"/chats/{chat_id}/messages", json={"question": "visualize the O grade count in each subject"})
    assert res1.status_code == 200
    d1 = res1.json()
    assert d1["status"] == "success"
    assert d1["intent"]["condition"]["value"] == "O"

    # Query 2: similarly for B grade
    res2 = client.post(f"/chats/{chat_id}/messages", json={"question": "similarly for B grade"})
    assert res2.status_code == 200
    d2 = res2.json()

    # Must automatically inherit conditional_count operation, subject columns scope, and change grade to B
    assert d2["status"] == "success"
    assert d2["intent"]["operation"] == "conditional_count"
    assert d2["intent"]["condition"]["value"] == "B"
    assert "clarification" not in d2["type"]


# ----------------------------------------------------------------------
# TEST 3: Separate chats maintain independent file storage (No cross-chat leakage)
# ----------------------------------------------------------------------

def test_acceptance_3_separate_chats_isolation(test_storage_env):
    client = test_storage_env["client"]

    # Chat A -> SEM_V
    chat_a = client.post("/chats", json={"title": "Chat A"}).json()["id"]
    csv_a = create_csv_bytes("subject,score\nMath,95\nPhysics,88", [])
    client.post(f"/chats/{chat_a}/files", files={"file": ("SEM_V.csv", csv_a, "text/csv")})

    # Chat B -> SEM_IV
    chat_b = client.post("/chats", json={"title": "Chat B"}).json()["id"]
    csv_b = create_csv_bytes("subject,score\nBiology,75\nChemistry,82", [])
    client.post(f"/chats/{chat_b}/files", files={"file": ("SEM_IV.csv", csv_b, "text/csv")})

    # Query Chat A
    res_a = client.post(f"/chats/{chat_a}/messages", json={"question": "what is the max score?"})
    assert res_a.status_code == 200

    # Query Chat B
    res_b = client.post(f"/chats/{chat_b}/messages", json={"question": "what is the max score?"})
    assert res_b.status_code == 200

    # Verify Chat A files != Chat B files
    files_a = client.get(f"/chats/{chat_a}/files").json()["files"]
    files_b = client.get(f"/chats/{chat_b}/files").json()["files"]

    assert files_a[0]["filename"] == "SEM_V.csv"
    assert files_b[0]["filename"] == "SEM_IV.csv"
    assert files_a[0]["file_id"] != files_b[0]["file_id"]


# ----------------------------------------------------------------------
# TEST 4: Multiple files in single chat retained and distinguished
# ----------------------------------------------------------------------

def test_acceptance_4_multiple_files_per_chat(test_storage_env):
    client = test_storage_env["client"]

    chat_id = client.post("/chats", json={"title": "Multi File Chat"}).json()["id"]

    # Upload File 1: SEM_V.csv
    csv1 = create_csv_bytes("regular,regular_1\nO,B\nA,O", [])
    f1_res = client.post(f"/chats/{chat_id}/files", files={"file": ("SEM_V.csv", csv1, "text/csv")}).json()

    # Upload File 2: attendance.csv
    csv2 = create_csv_bytes("student,attendance_pct\nAlice,95\nBob,82", [])
    f2_res = client.post(f"/chats/{chat_id}/files", files={"file": ("attendance.csv", csv2, "text/csv")}).json()

    # Verify chat contains both files
    chat_files = client.get(f"/chats/{chat_id}/files").json()["files"]
    assert len(chat_files) == 2
    fnames = [f["filename"] for f in chat_files]
    assert "SEM_V.csv" in fnames
    assert "attendance.csv" in fnames

    # Query about attendance -> Should distinguish attendance.csv
    att_res = client.post(f"/chats/{chat_id}/messages", json={"question": "what is the average attendance_pct in attendance.csv?"})
    assert att_res.status_code == 200
    assert att_res.json()["status"] == "success"


# ----------------------------------------------------------------------
# TEST 5: Server restart resilience
# ----------------------------------------------------------------------

def test_acceptance_5_server_restart_resilience(test_storage_env):
    client = test_storage_env["client"]
    storage_dir = test_storage_env["storage_dir"]

    # Step 1: Create chat, upload file, execute query
    chat_id = client.post("/chats", json={"title": "Restart Resilience Test"}).json()["id"]
    csv_bytes = create_csv_bytes("regular,regular_1\nO,A\nB,O", [])
    client.post(f"/chats/{chat_id}/files", files={"file": ("grades.csv", csv_bytes, "text/csv")})

    client.post(f"/chats/{chat_id}/messages", json={"question": "visualize the O grade count in each subject"})

    # Step 2: SIMULATE APPLICATION RESTART
    DATASET_REGISTRY.clear()

    # Load fresh repository & service from disk
    fresh_repo = JsonChatRepository(storage_dir=storage_dir)
    fresh_service = ChatService(repository=fresh_repo)
    import chat
    chat._chat_service_instance = fresh_service

    # Step 3: Verify chat history remains
    chat_detail = client.get(f"/chats/{chat_id}").json()
    assert chat_detail["chat_id"] == chat_id
    assert len(chat_detail["files"]) == 1
    assert len(chat_detail["messages"]) >= 2  # user + assistant

    # Step 4: Verify follow-up query continues working post-restart
    fu_res = client.post(f"/chats/{chat_id}/messages", json={"question": "similarly for A grade"})
    assert fu_res.status_code == 200
    assert fu_res.json()["status"] == "success"
    assert fu_res.json()["intent"]["condition"]["value"] == "A"
