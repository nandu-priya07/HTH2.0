"""
Comprehensive unit tests for persistent chat history, conversation management,
and SQLite data access layer according to specification.
"""

import os
import shutil
import tempfile
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from chat.database import initialize_database, get_db_connection
from chat.sqlite_repository import SqliteChatRepository
from chat.service import ChatService, generate_deterministic_title
from main import app


@pytest.fixture
def temp_db_env(tmp_path, monkeypatch):
    """
    Creates an isolated temporary SQLite database for testing.
    """
    db_file = tmp_path / "test_app.db"
    monkeypatch.setenv("CHAT_DATABASE_PATH", str(db_file))
    initialize_database(db_file)
    repo = SqliteChatRepository(db_path=db_file)
    service = ChatService(repository=repo)
    return {"db_file": db_file, "repo": repo, "service": service}


@pytest.fixture
def client(temp_db_env, monkeypatch):
    """
    FastAPI TestClient wired to the temporary test database.
    """
    import chat
    monkeypatch.setattr(chat, "_chat_service_instance", temp_db_env["service"])
    return TestClient(app)


# ----------------------------------------------------------------------
# UNIT TESTS: Deterministic Title Generation
# ----------------------------------------------------------------------

def test_deterministic_title_generation():
    assert "A Grade Count In Each Subject" in generate_deterministic_title("list the A grade count in each subject")
    assert "Sales By Region" in generate_deterministic_title("show me the sales by region?")
    assert "Average Score Per Department" in generate_deterministic_title("visualize the average score per department")
    assert generate_deterministic_title("") == "New Analysis"


# ----------------------------------------------------------------------
# TEST 1: Create conversation
# ----------------------------------------------------------------------

def test_1_create_conversation(client):
    response = client.post("/api/conversations", json={"title": "Sales Analysis"})
    assert response.status_code == 201
    data = response.json()
    assert "id" in data
    assert data["title"] == "Sales Analysis"
    assert data["dataset_id"] is None
    assert "created_at" in data
    assert "updated_at" in data


# ----------------------------------------------------------------------
# TEST 2: List conversations
# ----------------------------------------------------------------------

def test_2_list_conversations(client):
    # Create two conversations
    c1 = client.post("/api/conversations", json={"title": "First Conversation"}).json()
    c2 = client.post("/api/conversations", json={"title": "Second Conversation"}).json()

    response = client.get("/api/conversations")
    assert response.status_code == 200
    conversations = response.json()
    assert len(conversations) >= 2
    ids = [c["id"] for c in conversations]
    assert c1["id"] in ids
    assert c2["id"] in ids
    # Check newest updated first
    assert conversations[0]["id"] == c2["id"]


# ----------------------------------------------------------------------
# TEST 3: Create user message
# ----------------------------------------------------------------------

def test_3_create_user_message(temp_db_env):
    service: ChatService = temp_db_env["service"]
    conv = service.create_conversation("Test Chat")
    user_msg = service.add_user_message(conv.id, "What is the total revenue?")

    assert user_msg.id is not None
    assert user_msg.conversation_id == conv.id
    assert user_msg.role == "user"
    assert user_msg.content == "What is the total revenue?"

    messages = service.get_messages(conv.id)
    assert len(messages) == 1
    assert messages[0].content == "What is the total revenue?"


# ----------------------------------------------------------------------
# TEST 4: Create assistant message with result JSON & visualization
# ----------------------------------------------------------------------

def test_4_create_assistant_message_with_result_and_visualization(temp_db_env):
    service: ChatService = temp_db_env["service"]
    conv = service.create_conversation("Analytics Chat")

    result_payload = {
        "scalar": {"value": 150000, "formatted": "$150,000"},
        "table": {"columns": ["Region", "Sales"], "rows": [{"Region": "North", "Sales": 150000}]}
    }
    vis_payload = {
        "type": "bar",
        "title": "Sales by Region",
        "data": [{"Region": "North", "Sales": 150000}]
    }

    ast_msg = service.add_assistant_message(
        conversation_id=conv.id,
        content="Here is the breakdown of sales by region.",
        result_json=result_payload,
        visualization_json=vis_payload
    )

    assert ast_msg.role == "assistant"
    assert ast_msg.result_json == result_payload
    assert ast_msg.visualization_json == vis_payload

    # Retrieve from DB and verify serialization/deserialization
    messages = service.get_messages(conv.id)
    assert len(messages) == 1
    retrieved = messages[0]
    assert retrieved.result_json["scalar"]["value"] == 150000
    assert retrieved.visualization_json["type"] == "bar"


# ----------------------------------------------------------------------
# TEST 5: Retrieve messages in chronological order
# ----------------------------------------------------------------------

def test_5_retrieve_messages_chronological(client, temp_db_env):
    service: ChatService = temp_db_env["service"]
    conv = service.create_conversation("Timeline Chat")

    m1 = service.add_user_message(conv.id, "Query 1")
    m2 = service.add_assistant_message(conv.id, "Answer 1")
    m3 = service.add_user_message(conv.id, "Query 2")
    m4 = service.add_assistant_message(conv.id, "Answer 2")

    response = client.get(f"/api/conversations/{conv.id}/messages")
    assert response.status_code == 200
    msg_list = response.json()
    assert len(msg_list) == 4
    assert [m["content"] for m in msg_list] == ["Query 1", "Answer 1", "Query 2", "Answer 2"]
    assert [m["role"] for m in msg_list] == ["user", "assistant", "user", "assistant"]


# ----------------------------------------------------------------------
# TEST 6: Rename conversation
# ----------------------------------------------------------------------

def test_6_rename_conversation(client):
    conv = client.post("/api/conversations", json={"title": "Old Name"}).json()
    cid = conv["id"]

    patch_res = client.patch(f"/api/conversations/{cid}", json={"title": "Student Grade Analysis"})
    assert patch_res.status_code == 200
    updated = patch_res.json()
    assert updated["title"] == "Student Grade Analysis"

    # Verify retrieval
    get_res = client.get(f"/api/conversations/{cid}")
    assert get_res.json()["title"] == "Student Grade Analysis"


# ----------------------------------------------------------------------
# TEST 7: Delete conversation (and cascade messages)
# ----------------------------------------------------------------------

def test_7_delete_conversation(client, temp_db_env):
    service: ChatService = temp_db_env["service"]
    conv = service.create_conversation("To Be Deleted")
    service.add_user_message(conv.id, "Hello")
    service.add_assistant_message(conv.id, "Hi there")

    del_res = client.delete(f"/api/conversations/{conv.id}")
    assert del_res.status_code == 200
    assert del_res.json()["success"] is True

    # Verify conversation is gone
    get_res = client.get(f"/api/conversations/{conv.id}")
    assert get_res.status_code == 404

    # Verify messages are gone
    msg_res = client.get(f"/api/conversations/{conv.id}/messages")
    assert msg_res.status_code == 404


# ----------------------------------------------------------------------
# TEST 8: Verify deleting conversation does NOT delete dataset files
# ----------------------------------------------------------------------

def test_8_delete_conversation_preserves_dataset_files(tmp_path, client, temp_db_env):
    service: ChatService = temp_db_env["service"]

    # Create dummy dataset raw and processed files
    dummy_dataset_id = "dataset-test-uuid-12345"
    raw_dir = tmp_path / "raw"
    processed_dir = tmp_path / "processed"
    raw_dir.mkdir(parents=True, exist_ok=True)
    processed_dir.mkdir(parents=True, exist_ok=True)

    dummy_raw_file = raw_dir / f"{dummy_dataset_id}.csv"
    dummy_raw_file.write_text("col1,col2\n1,2\n3,4")
    dummy_proc_file = processed_dir / f"{dummy_dataset_id}_cleaned.parquet"
    dummy_proc_file.write_text("binary-data")

    # Create conversation associated with dataset
    conv = service.create_conversation(title="Dataset Attached Chat", dataset_id=dummy_dataset_id)
    service.add_user_message(conv.id, "Analyze dataset")

    # Delete conversation
    del_res = client.delete(f"/api/conversations/{conv.id}")
    assert del_res.status_code == 200

    # Assert dataset files STILL EXIST intact
    assert dummy_raw_file.exists()
    assert dummy_proc_file.exists()


# ----------------------------------------------------------------------
# TEST 9: Send chat query without conversation_id -> Auto create
# ----------------------------------------------------------------------

def test_9_chat_query_auto_creates_conversation(client):
    # Calling /api/query with no active dataset returns conversational response, but creates conversation
    res = client.post("/api/query", json={"question": "list the A grade count in each subject", "dataset_id": "nonexistent_mock_id"})
    assert res.status_code == 200
    data = res.json()
    assert "conversation_id" in data
    assert data["conversation_id"] is not None
    assert "user_message" in data
    assert data["user_message"]["content"] == "list the A grade count in each subject"
    assert "assistant_message" in data

    cid = data["conversation_id"]

    # Verify the conversation exists in listing
    convs = client.get("/api/conversations").json()
    matching = [c for c in convs if c["id"] == cid]
    assert len(matching) == 1
    # Check title was deterministically derived
    assert "A Grade Count In Each Subject" in matching[0]["title"]


# ----------------------------------------------------------------------
# TEST 10: Send another message with returned conversation_id -> Appended
# ----------------------------------------------------------------------

def test_10_chat_query_appends_to_existing_conversation(client):
    # Step 1: Initial query
    res1 = client.post("/api/query", json={"question": "show sales by region", "dataset_id": "nonexistent_mock_id"})
    assert res1.status_code == 200
    cid = res1.json()["conversation_id"]

    # Step 2: Follow-up query in same conversation
    res2 = client.post("/api/query", json={"question": "now filter to top 5", "conversation_id": cid, "dataset_id": "nonexistent_mock_id"})
    assert res2.status_code == 200
    assert res2.json()["conversation_id"] == cid

    # Step 3: Fetch messages
    msg_res = client.get(f"/api/conversations/{cid}/messages")
    assert msg_res.status_code == 200
    messages = msg_res.json()
    assert len(messages) == 4  # 2 user msgs + 2 assistant msgs
    assert messages[0]["content"] == "show sales by region"
    assert messages[2]["content"] == "now filter to top 5"
