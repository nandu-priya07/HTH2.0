"""
SQLite implementation of the BaseChatRepository.
Handles parameterized queries, transaction safety, and JSON serialization.
"""

import json
import uuid
import logging
from typing import Any, Dict, List, Optional, Union
from pathlib import Path

from .models import Conversation, Message, utc_now_iso
from .repository import BaseChatRepository
from .database import get_db_connection, initialize_database

logger = logging.getLogger(__name__)


class SqliteChatRepository(BaseChatRepository):
    """
    SQLite-backed repository for conversation and message persistence.
    """

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path
        # Ensure database and tables are created on startup
        initialize_database(self.db_path)

    def create_conversation(
        self,
        title: str = "New Chat",
        dataset_id: Optional[str] = None,
        conversation_id: Optional[str] = None
    ) -> Conversation:
        cid = conversation_id or str(uuid.uuid4())
        now = utc_now_iso()
        title_clean = (title or "New Chat").strip()[:100]

        with get_db_connection(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO conversations (id, title, dataset_id, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (cid, title_clean, dataset_id, now, now)
            )

        return Conversation(
            id=cid,
            title=title_clean,
            dataset_id=dataset_id,
            created_at=now,
            updated_at=now
        )

    def get_conversation(self, conversation_id: str) -> Optional[Conversation]:
        with get_db_connection(self.db_path) as conn:
            cursor = conn.execute(
                """
                SELECT id, title, dataset_id, created_at, updated_at
                FROM conversations
                WHERE id = ?
                """,
                (conversation_id,)
            )
            row = cursor.fetchone()
            if not row:
                return None

            return Conversation(
                id=row["id"],
                title=row["title"],
                dataset_id=row["dataset_id"],
                created_at=row["created_at"],
                updated_at=row["updated_at"]
            )

    def list_conversations(self, limit: int = 100, offset: int = 0) -> List[Conversation]:
        with get_db_connection(self.db_path) as conn:
            cursor = conn.execute(
                """
                SELECT id, title, dataset_id, created_at, updated_at
                FROM conversations
                ORDER BY updated_at DESC
                LIMIT ? OFFSET ?
                """,
                (limit, offset)
            )
            rows = cursor.fetchall()
            return [
                Conversation(
                    id=row["id"],
                    title=row["title"],
                    dataset_id=row["dataset_id"],
                    created_at=row["created_at"],
                    updated_at=row["updated_at"]
                )
                for row in rows
            ]

    def update_conversation(
        self,
        conversation_id: str,
        title: Optional[str] = None,
        dataset_id: Optional[str] = None
    ) -> Optional[Conversation]:
        existing = self.get_conversation(conversation_id)
        if not existing:
            return None

        new_title = title.strip()[:100] if title is not None else existing.title
        new_dataset_id = dataset_id if dataset_id is not None else existing.dataset_id
        now = utc_now_iso()

        with get_db_connection(self.db_path) as conn:
            conn.execute(
                """
                UPDATE conversations
                SET title = ?, dataset_id = ?, updated_at = ?
                WHERE id = ?
                """,
                (new_title, new_dataset_id, now, conversation_id)
            )

        return Conversation(
            id=conversation_id,
            title=new_title,
            dataset_id=new_dataset_id,
            created_at=existing.created_at,
            updated_at=now
        )

    def update_conversation_timestamp(self, conversation_id: str) -> bool:
        now = utc_now_iso()
        with get_db_connection(self.db_path) as conn:
            cursor = conn.execute(
                """
                UPDATE conversations
                SET updated_at = ?
                WHERE id = ?
                """,
                (now, conversation_id)
            )
            return cursor.rowcount > 0

    def delete_conversation(self, conversation_id: str) -> bool:
        with get_db_connection(self.db_path) as conn:
            # Delete messages first (or rely on foreign key cascade)
            conn.execute("DELETE FROM messages WHERE conversation_id = ?", (conversation_id,))
            cursor = conn.execute("DELETE FROM conversations WHERE id = ?", (conversation_id,))
            return cursor.rowcount > 0

    def create_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        result_json: Optional[Dict[str, Any]] = None,
        visualization_json: Optional[Union[Dict[str, Any], List[Dict[str, Any]]]] = None,
        message_id: Optional[str] = None,
        intent: Optional[Dict[str, Any]] = None,
        query_spec: Optional[Dict[str, Any]] = None,
        file_id: Optional[str] = None
    ) -> Message:
        mid = message_id or str(uuid.uuid4())
        now = utc_now_iso()
        role_clean = (role or "user").strip().lower()
        if role_clean not in ("user", "assistant", "system"):
            role_clean = "user"

        res_str = json.dumps(result_json) if result_json is not None else None
        vis_str = json.dumps(visualization_json) if visualization_json is not None else None

        with get_db_connection(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO messages (id, conversation_id, role, content, result_json, visualization_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (mid, conversation_id, role_clean, content, res_str, vis_str, now)
            )
            # Update parent conversation updated_at
            conn.execute(
                """
                UPDATE conversations
                SET updated_at = ?
                WHERE id = ?
                """,
                (now, conversation_id)
            )

        return Message(
            id=mid,
            conversation_id=conversation_id,
            role=role_clean,
            content=content,
            result_json=result_json,
            visualization_json=visualization_json,
            intent=intent,
            query_spec=query_spec,
            file_id=file_id,
            created_at=now
        )

    def get_messages(self, conversation_id: str, limit: Optional[int] = None) -> List[Message]:
        with get_db_connection(self.db_path) as conn:
            if limit and limit > 0:
                # Fetch latest `limit` messages in chronological order
                cursor = conn.execute(
                    """
                    SELECT id, conversation_id, role, content, result_json, visualization_json, created_at
                    FROM (
                        SELECT id, conversation_id, role, content, result_json, visualization_json, created_at
                        FROM messages
                        WHERE conversation_id = ?
                        ORDER BY created_at DESC
                        LIMIT ?
                    ) sub
                    ORDER BY created_at ASC
                    """,
                    (conversation_id, limit)
                )
            else:
                cursor = conn.execute(
                    """
                    SELECT id, conversation_id, role, content, result_json, visualization_json, created_at
                    FROM messages
                    WHERE conversation_id = ?
                    ORDER BY created_at ASC
                    """,
                    (conversation_id,)
                )

            rows = cursor.fetchall()
            messages = []
            for row in rows:
                res_val = None
                if row["result_json"]:
                    try:
                        res_val = json.loads(row["result_json"])
                    except Exception:
                        res_val = None

                vis_val = None
                if row["visualization_json"]:
                    try:
                        vis_val = json.loads(row["visualization_json"])
                    except Exception:
                        vis_val = None

                messages.append(
                    Message(
                        id=row["id"],
                        conversation_id=row["conversation_id"],
                        role=row["role"],
                        content=row["content"],
                        result_json=res_val,
                        visualization_json=vis_val,
                        created_at=row["created_at"]
                    )
                )
            return messages

    def delete_message(self, message_id: str) -> bool:
        with get_db_connection(self.db_path) as conn:
            cursor = conn.execute("DELETE FROM messages WHERE id = ?", (message_id,))
            return cursor.rowcount > 0
