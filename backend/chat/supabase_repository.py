"""
Supabase PostgreSQL implementation of BaseChatRepository.
Provides persistent, parameterized conversation, message, and file storage in Supabase PostgreSQL.
"""

import uuid
import json
import logging
from typing import Any, Dict, List, Optional, Union
from datetime import datetime, timezone
from psycopg2.extras import RealDictCursor, Json

from .models import Conversation, Message, utc_now_iso
from .repository import BaseChatRepository
from core.supabase import get_supabase_connection, initialize_supabase_database

logger = logging.getLogger(__name__)


def _parse_json_field(val: Any) -> Any:
    if val is None:
        return None
    if isinstance(val, (dict, list)):
        return val
    if isinstance(val, str):
        try:
            return json.loads(val)
        except Exception:
            return None
    return val


class SupabaseChatRepository(BaseChatRepository):
    """
    Supabase PostgreSQL repository for persistent conversation and message management.
    """

    def __init__(self, owner_id: Optional[str] = None):
        self.owner_id = owner_id
        # Ensure database and tables exist
        initialize_supabase_database()

    def create_conversation(
        self,
        title: str = "New Chat",
        dataset_id: Optional[str] = None,
        conversation_id: Optional[str] = None
    ) -> Conversation:
        cid = conversation_id or str(uuid.uuid4())
        now = utc_now_iso()
        title_clean = (title or "New Chat").strip()[:100]

        with get_supabase_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    INSERT INTO public.conversations (id, title, dataset_id, owner_id, created_at, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (id) DO UPDATE SET
                        title = EXCLUDED.title,
                        dataset_id = COALESCE(EXCLUDED.dataset_id, public.conversations.dataset_id),
                        updated_at = EXCLUDED.updated_at;
                    """,
                    (cid, title_clean, dataset_id, self.owner_id, now, now)
                )

        return Conversation(
            id=cid,
            title=title_clean,
            dataset_id=dataset_id,
            created_at=now,
            updated_at=now
        )

    def get_conversation(self, conversation_id: str) -> Optional[Conversation]:
        with get_supabase_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                sql = "SELECT id, title, dataset_id, created_at, updated_at FROM public.conversations WHERE id = %s"
                params = [conversation_id]
                if self.owner_id is not None:
                    sql += " AND (owner_id = %s OR owner_id IS NULL)"
                    params.append(self.owner_id)

                cur.execute(sql, params)
                row = cur.fetchone()
                if not row:
                    return None

                created_str = row["created_at"].isoformat() if isinstance(row["created_at"], datetime) else str(row["created_at"])
                updated_str = row["updated_at"].isoformat() if isinstance(row["updated_at"], datetime) else str(row["updated_at"])

                return Conversation(
                    id=row["id"],
                    title=row["title"],
                    dataset_id=row["dataset_id"],
                    created_at=created_str,
                    updated_at=updated_str
                )

    def list_conversations(self, limit: int = 100, offset: int = 0) -> List[Conversation]:
        with get_supabase_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                sql = "SELECT id, title, dataset_id, created_at, updated_at FROM public.conversations"
                params = []
                if self.owner_id is not None:
                    sql += " WHERE (owner_id = %s OR owner_id IS NULL)"
                    params.append(self.owner_id)

                sql += " ORDER BY updated_at DESC LIMIT %s OFFSET %s"
                params.extend([limit, offset])

                cur.execute(sql, params)
                rows = cur.fetchall()

                conversations = []
                for row in rows:
                    created_str = row["created_at"].isoformat() if isinstance(row["created_at"], datetime) else str(row["created_at"])
                    updated_str = row["updated_at"].isoformat() if isinstance(row["updated_at"], datetime) else str(row["updated_at"])
                    conversations.append(
                        Conversation(
                            id=row["id"],
                            title=row["title"],
                            dataset_id=row["dataset_id"],
                            created_at=created_str,
                            updated_at=updated_str
                        )
                    )
                return conversations

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

        with get_supabase_connection() as conn:
            with conn.cursor() as cur:
                sql = "UPDATE public.conversations SET title = %s, dataset_id = %s, updated_at = %s WHERE id = %s"
                params = [new_title, new_dataset_id, now, conversation_id]
                if self.owner_id is not None:
                    sql += " AND (owner_id = %s OR owner_id IS NULL)"
                    params.append(self.owner_id)

                cur.execute(sql, params)

        return Conversation(
            id=conversation_id,
            title=new_title,
            dataset_id=new_dataset_id,
            created_at=existing.created_at,
            updated_at=now
        )

    def update_conversation_timestamp(self, conversation_id: str) -> bool:
        now = utc_now_iso()
        with get_supabase_connection() as conn:
            with conn.cursor() as cur:
                sql = "UPDATE public.conversations SET updated_at = %s WHERE id = %s"
                params = [now, conversation_id]
                if self.owner_id is not None:
                    sql += " AND (owner_id = %s OR owner_id IS NULL)"
                    params.append(self.owner_id)

                cur.execute(sql, params)
                return cur.rowcount > 0

    def delete_conversation(self, conversation_id: str) -> bool:
        with get_supabase_connection() as conn:
            with conn.cursor() as cur:
                if self.owner_id is not None and not self.get_conversation(conversation_id):
                    return False

                cur.execute("DELETE FROM public.messages WHERE conversation_id = %s", (conversation_id,))
                cur.execute("DELETE FROM public.chat_files WHERE conversation_id = %s", (conversation_id,))

                sql = "DELETE FROM public.conversations WHERE id = %s"
                params = [conversation_id]
                if self.owner_id is not None:
                    sql += " AND (owner_id = %s OR owner_id IS NULL)"
                    params.append(self.owner_id)

                cur.execute(sql, params)
                return cur.rowcount > 0

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

        res_val = Json(result_json) if result_json is not None else None
        vis_val = Json(visualization_json) if visualization_json is not None else None
        intent_val = Json(intent) if intent is not None else None
        query_spec_val = Json(query_spec) if query_spec is not None else None

        with get_supabase_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO public.messages (id, conversation_id, role, content, result_json, visualization_json, intent_json, query_spec_json, file_id, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (mid, conversation_id, role_clean, content, res_val, vis_val, intent_val, query_spec_val, file_id, now)
                )
                cur.execute(
                    """
                    UPDATE public.conversations
                    SET updated_at = %s
                    WHERE id = %s
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
        with get_supabase_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                if limit and limit > 0:
                    cur.execute(
                        """
                        SELECT id, conversation_id, role, content, result_json, visualization_json, intent_json, query_spec_json, file_id, created_at
                        FROM (
                            SELECT id, conversation_id, role, content, result_json, visualization_json, intent_json, query_spec_json, file_id, created_at
                            FROM public.messages
                            WHERE conversation_id = %s
                            ORDER BY created_at DESC
                            LIMIT %s
                        ) sub
                        ORDER BY created_at ASC;
                        """,
                        (conversation_id, limit)
                    )
                else:
                    cur.execute(
                        """
                        SELECT id, conversation_id, role, content, result_json, visualization_json, intent_json, query_spec_json, file_id, created_at
                        FROM public.messages
                        WHERE conversation_id = %s
                        ORDER BY created_at ASC;
                        """,
                        (conversation_id,)
                    )

                rows = cur.fetchall()
                messages = []
                for row in rows:
                    created_str = row["created_at"].isoformat() if isinstance(row["created_at"], datetime) else str(row["created_at"])
                    messages.append(
                        Message(
                            id=row["id"],
                            conversation_id=row["conversation_id"],
                            role=row["role"],
                            content=row["content"],
                            result_json=_parse_json_field(row["result_json"]),
                            visualization_json=_parse_json_field(row["visualization_json"]),
                            intent=_parse_json_field(row["intent_json"]),
                            query_spec=_parse_json_field(row["query_spec_json"]),
                            file_id=row.get("file_id"),
                            created_at=created_str
                        )
                    )
                return messages

    def delete_message(self, message_id: str) -> bool:
        with get_supabase_connection() as conn:
            with conn.cursor() as cur:
                if self.owner_id is None:
                    cur.execute("DELETE FROM public.messages WHERE id = %s", (message_id,))
                else:
                    cur.execute(
                        """
                        DELETE FROM public.messages 
                        WHERE id = %s 
                        AND conversation_id IN (SELECT id FROM public.conversations WHERE owner_id = %s OR owner_id IS NULL)
                        """,
                        (message_id, self.owner_id)
                    )
                return cur.rowcount > 0

    def add_file(self, conversation_id: str, file_meta: Dict[str, Any]) -> Dict[str, Any]:
        metadata = dict(file_meta)
        now = metadata.get("created_at") or utc_now_iso()

        with get_supabase_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO public.chat_files (file_id, conversation_id, metadata_json, created_at)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (conversation_id, file_id) DO UPDATE SET
                        metadata_json = EXCLUDED.metadata_json,
                        created_at = EXCLUDED.created_at;
                    """,
                    (metadata["file_id"], conversation_id, Json(metadata), now)
                )
        return metadata

    def get_files(self, conversation_id: str) -> List[Dict[str, Any]]:
        with get_supabase_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    "SELECT metadata_json FROM public.chat_files WHERE conversation_id = %s ORDER BY created_at ASC;",
                    (conversation_id,)
                )
                rows = cur.fetchall()

        files = []
        for row in rows:
            parsed = _parse_json_field(row["metadata_json"])
            if parsed and isinstance(parsed, dict):
                files.append(parsed)
        return files

    def delete_file(self, conversation_id: str, file_id: str) -> bool:
        if not self.get_conversation(conversation_id):
            return False

        with get_supabase_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM public.chat_files WHERE conversation_id = %s AND file_id = %s;",
                    (conversation_id, file_id)
                )
                return cur.rowcount > 0

    def get_chat_json(self, conversation_id: str):
        conversation = self.get_conversation(conversation_id)
        if not conversation:
            return None
        return {
            **conversation.to_dict(),
            "chat_id": conversation.id,
            "files": self.get_files(conversation_id),
            "messages": [m.to_dict() for m in self.get_messages(conversation_id)]
        }
