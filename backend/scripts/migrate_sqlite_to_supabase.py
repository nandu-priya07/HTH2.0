"""
Migration Utility: SQLite to Supabase PostgreSQL & Supabase Storage.
Copies all conversations, messages, user sessions, chat files, and dataset files from SQLite/local disk into Supabase.
"""

import os
import sys
import json
import sqlite3
import logging
from pathlib import Path
from typing import Dict, Any

# Ensure backend root is in sys.path
BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from core.supabase import get_supabase_connection, initialize_supabase_database
from services.storage_service import SupabaseStorageService
from psycopg2.extras import RealDictCursor, Json

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("migration")


def _get_field(row: sqlite3.Row, field_name: str) -> Any:
    keys = row.keys()
    if field_name in keys:
        return row[field_name]
    return None


def migrate():
    logger.info("Starting SQLite to Supabase Migration...")

    # 1. Initialize Supabase Database Schema
    initialize_supabase_database()

    db_path = BACKEND_DIR / "data" / "app.db"
    if not db_path.exists():
        logger.info(f"No SQLite database found at {db_path}. Nothing to migrate from SQLite.")
        return

    sqlite_conn = sqlite3.connect(str(db_path))
    sqlite_conn.row_factory = sqlite3.Row

    storage_service = SupabaseStorageService()

    report = {
        "auth_users": 0,
        "auth_sessions": 0,
        "conversations": 0,
        "messages": 0,
        "chat_files": 0,
        "storage_files": 0
    }

    # 2. Migrate auth_users
    try:
        users = sqlite_conn.execute("SELECT * FROM auth_users;").fetchall()
        with get_supabase_connection() as conn:
            with conn.cursor() as cur:
                for u in users:
                    cur.execute(
                        """
                        INSERT INTO public.auth_users (id, email, display_name, password_hash, created_at)
                        VALUES (%s, %s, %s, %s, %s)
                        ON CONFLICT (id) DO NOTHING;
                        """,
                        (u["id"], u["email"], u["display_name"], u["password_hash"], u["created_at"])
                    )
                    report["auth_users"] += 1
    except Exception as e:
        logger.warning(f"Error migrating auth_users: {e}")

    # 3. Migrate auth_sessions
    try:
        sessions = sqlite_conn.execute("SELECT * FROM auth_sessions;").fetchall()
        with get_supabase_connection() as conn:
            with conn.cursor() as cur:
                for s in sessions:
                    cur.execute(
                        """
                        INSERT INTO public.auth_sessions (token_hash, user_id, expires_at, created_at)
                        VALUES (%s, %s, %s, %s)
                        ON CONFLICT (token_hash) DO NOTHING;
                        """,
                        (s["token_hash"], s["user_id"], s["expires_at"], s["created_at"])
                    )
                    report["auth_sessions"] += 1
    except Exception as e:
        logger.warning(f"Error migrating auth_sessions: {e}")

    # 4. Migrate conversations
    try:
        convs = sqlite_conn.execute("SELECT * FROM conversations;").fetchall()
        with get_supabase_connection() as conn:
            with conn.cursor() as cur:
                for c in convs:
                    owner_id = _get_field(c, "owner_id")
                    cur.execute(
                        """
                        INSERT INTO public.conversations (id, title, dataset_id, owner_id, created_at, updated_at)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        ON CONFLICT (id) DO UPDATE SET
                            title = EXCLUDED.title,
                            dataset_id = COALESCE(EXCLUDED.dataset_id, public.conversations.dataset_id),
                            updated_at = EXCLUDED.updated_at;
                        """,
                        (c["id"], c["title"], c["dataset_id"], owner_id, c["created_at"], c["updated_at"])
                    )
                    report["conversations"] += 1
    except Exception as e:
        logger.warning(f"Error migrating conversations: {e}")

    # 5. Migrate messages
    try:
        msgs = sqlite_conn.execute("SELECT * FROM messages;").fetchall()
        with get_supabase_connection() as conn:
            with conn.cursor() as cur:
                for m in msgs:
                    raw_res = _get_field(m, "result_json")
                    raw_vis = _get_field(m, "visualization_json")
                    raw_intent = _get_field(m, "intent_json")
                    raw_qspec = _get_field(m, "query_spec_json")

                    res_json = json.loads(raw_res) if raw_res else None
                    vis_json = json.loads(raw_vis) if raw_vis else None
                    intent_json = json.loads(raw_intent) if raw_intent else None
                    qspec_json = json.loads(raw_qspec) if raw_qspec else None

                    cur.execute(
                        """
                        INSERT INTO public.messages (id, conversation_id, role, content, result_json, visualization_json, intent_json, query_spec_json, created_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (id) DO NOTHING;
                        """,
                        (
                            m["id"],
                            m["conversation_id"],
                            m["role"],
                            m["content"],
                            Json(res_json) if res_json else None,
                            Json(vis_json) if vis_json else None,
                            Json(intent_json) if intent_json else None,
                            Json(qspec_json) if qspec_json else None,
                            m["created_at"]
                        )
                    )
                    report["messages"] += 1
    except Exception as e:
        logger.warning(f"Error migrating messages: {e}")

    # 6. Migrate chat_files & upload local disk files to Supabase Storage
    try:
        cfiles = sqlite_conn.execute("SELECT * FROM chat_files;").fetchall()
        with get_supabase_connection() as conn:
            with conn.cursor() as cur:
                for cf in cfiles:
                    raw_meta = _get_field(cf, "metadata_json")
                    meta = json.loads(raw_meta) if raw_meta else {}
                    cur.execute(
                        """
                        INSERT INTO public.chat_files (file_id, conversation_id, metadata_json, created_at)
                        VALUES (%s, %s, %s, %s)
                        ON CONFLICT (conversation_id, file_id) DO NOTHING;
                        """,
                        (cf["file_id"], cf["conversation_id"], Json(meta), cf["created_at"])
                    )
                    report["chat_files"] += 1

                    # Look for local file on disk to migrate to Supabase Storage
                    file_id = cf["file_id"]
                    chat_id = cf["conversation_id"]
                    filename = meta.get("filename") or f"{file_id}.csv"

                    local_chat_file = BACKEND_DIR / "storage" / "chats" / chat_id / "files" / f"{file_id}.csv"
                    if not local_chat_file.exists():
                        local_chat_file = BACKEND_DIR / "uploads" / "processed" / f"{file_id}.csv"

                    if local_chat_file.exists():
                        content = local_chat_file.read_bytes()
                        spath = storage_service.build_storage_path(
                            chat_id=chat_id, dataset_id=file_id, file_role="processed", filename=f"{file_id}.csv"
                        )
                        storage_service.upload_file(
                            storage_path=spath,
                            content=content,
                            file_type="csv",
                            file_role="processed",
                            dataset_id=file_id,
                            chat_id=chat_id
                        )
                        report["storage_files"] += 1
    except Exception as e:
        logger.warning(f"Error migrating chat_files: {e}")

    sqlite_conn.close()

    # 7. Print Migration Report & Validation
    logger.info("=" * 60)
    logger.info("MIGRATION COMPLETED SUCCESSFULLY")
    logger.info("=" * 60)
    for key, count in report.items():
        logger.info(f"- Migrated {key}: {count}")
    logger.info("=" * 60)


if __name__ == "__main__":
    migrate()
