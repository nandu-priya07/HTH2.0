"""
JSON File-Based Repository for Chat Conversations, File Storage Metadata, and Message History.
Implements BaseChatRepository with permanent disk storage under storage/chats/{chat_id}/conversation.json.
"""

import os
import json
import shutil
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from .models import Conversation, Message, utc_now_iso
from .repository import BaseChatRepository

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent
STORAGE_CHATS_DIR = BASE_DIR / "storage" / "chats"


class JsonChatRepository(BaseChatRepository):
    """
    JSON File-Based Persistence Engine.
    Stores chat metadata, uploaded file references, dataset schema metadata, and structured message history
    in storage/chats/{chat_id}/conversation.json.
    """

    def __init__(self, storage_dir: Optional[Path] = None):
        self.storage_dir = storage_dir or STORAGE_CHATS_DIR
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def _get_chat_dir(self, conversation_id: str) -> Path:
        chat_dir = self.storage_dir / str(conversation_id)
        chat_dir.mkdir(parents=True, exist_ok=True)
        (chat_dir / "files").mkdir(parents=True, exist_ok=True)
        return chat_dir

    def _get_json_path(self, conversation_id: str) -> Path:
        return self._get_chat_dir(conversation_id) / "conversation.json"

    def _load_json(self, conversation_id: str) -> Optional[Dict[str, Any]]:
        path = self._get_json_path(conversation_id)
        if not path.exists():
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading conversation.json for {conversation_id}: {e}")
            return None

    def _save_json(self, conversation_id: str, data: Dict[str, Any]) -> None:
        path = self._get_json_path(conversation_id)
        try:
            temp_path = path.with_suffix(".tmp")
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            temp_path.replace(path)
        except Exception as e:
            logger.error(f"Error saving conversation.json for {conversation_id}: {e}")

    # ---------------------------------------------------------
    # BaseChatRepository Implementations
    # ---------------------------------------------------------

    def create_conversation(
        self,
        title: str = "New Chat",
        dataset_id: Optional[str] = None,
        conversation_id: Optional[str] = None
    ) -> Conversation:
        import uuid
        cid = conversation_id or f"chat_{uuid.uuid4().hex[:8]}"
        now = utc_now_iso()

        data = {
            "chat_id": cid,
            "title": title or "New Chat",
            "dataset_id": dataset_id,
            "created_at": now,
            "updated_at": now,
            "files": [],
            "messages": []
        }
        self._save_json(cid, data)
        return Conversation(
            id=cid,
            title=data["title"],
            dataset_id=dataset_id,
            created_at=now,
            updated_at=now
        )

    def get_conversation(self, conversation_id: str) -> Optional[Conversation]:
        data = self._load_json(conversation_id)
        if not data:
            return None
        return Conversation(
            id=data.get("chat_id") or conversation_id,
            title=data.get("title", "New Chat"),
            dataset_id=data.get("dataset_id"),
            created_at=data.get("created_at", utc_now_iso()),
            updated_at=data.get("updated_at", utc_now_iso())
        )

    def list_conversations(self, limit: int = 100, offset: int = 0) -> List[Conversation]:
        conversations: List[Dict[str, Any]] = []

        if not self.storage_dir.exists():
            return []

        for chat_folder in self.storage_dir.iterdir():
            if chat_folder.is_dir():
                json_file = chat_folder / "conversation.json"
                if json_file.exists():
                    try:
                        with open(json_file, "r", encoding="utf-8") as f:
                            data = json.load(f)
                            conversations.append(data)
                    except Exception:
                        continue

        # Sort by updated_at descending
        conversations.sort(key=lambda c: c.get("updated_at", ""), reverse=True)

        sliced = conversations[offset : offset + limit]
        return [
            Conversation(
                id=c.get("chat_id") or c.get("id"),
                title=c.get("title", "New Chat"),
                dataset_id=c.get("dataset_id"),
                created_at=c.get("created_at", utc_now_iso()),
                updated_at=c.get("updated_at", utc_now_iso())
            )
            for c in sliced
        ]

    def update_conversation(
        self,
        conversation_id: str,
        title: Optional[str] = None,
        dataset_id: Optional[str] = None
    ) -> Optional[Conversation]:
        data = self._load_json(conversation_id)
        if not data:
            return None

        now = utc_now_iso()
        if title is not None:
            data["title"] = title
        if dataset_id is not None:
            data["dataset_id"] = dataset_id

        data["updated_at"] = now
        self._save_json(conversation_id, data)

        return Conversation(
            id=conversation_id,
            title=data.get("title", "New Chat"),
            dataset_id=data.get("dataset_id"),
            created_at=data.get("created_at", now),
            updated_at=now
        )

    def update_conversation_timestamp(self, conversation_id: str) -> bool:
        data = self._load_json(conversation_id)
        if not data:
            return False
        data["updated_at"] = utc_now_iso()
        self._save_json(conversation_id, data)
        return True

    def delete_conversation(self, conversation_id: str) -> bool:
        chat_dir = self.storage_dir / str(conversation_id)
        if chat_dir.exists():
            try:
                shutil.rmtree(chat_dir)
                return True
            except Exception as e:
                logger.error(f"Failed to delete chat directory {chat_dir}: {e}")
                return False
        return False

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
        import uuid
        data = self._load_json(conversation_id)
        if not data:
            self.create_conversation(conversation_id=conversation_id)
            data = self._load_json(conversation_id) or {
                "chat_id": conversation_id,
                "title": "New Chat",
                "files": [],
                "messages": []
            }

        mid = message_id or f"msg_{uuid.uuid4().hex[:8]}"
        now = utc_now_iso()

        msg_entry = {
            "message_id": mid,
            "id": mid,
            "conversation_id": conversation_id,
            "role": role,
            "content": content,
            "created_at": now,
            "result_json": result_json,
            "visualization_json": visualization_json,
            "intent": intent,
            "query_spec": query_spec,
            "file_id": file_id
        }

        data.setdefault("messages", []).append(msg_entry)
        data["updated_at"] = now
        self._save_json(conversation_id, data)

        return Message(
            id=mid,
            conversation_id=conversation_id,
            role=role,
            content=content,
            result_json=result_json,
            visualization_json=visualization_json,
            created_at=now,
            intent=intent,
            query_spec=query_spec,
            file_id=file_id
        )

    def get_messages(self, conversation_id: str, limit: Optional[int] = None) -> List[Message]:
        data = self._load_json(conversation_id)
        if not data:
            return []

        raw_msgs = data.get("messages", [])
        if limit is not None and limit > 0:
            raw_msgs = raw_msgs[-limit:]

        return [
            Message(
                id=m.get("message_id") or m.get("id", ""),
                conversation_id=conversation_id,
                role=m.get("role", "user"),
                content=m.get("content", ""),
                result_json=m.get("result_json") or m.get("result"),
                visualization_json=m.get("visualization_json") or m.get("visualization"),
                created_at=m.get("created_at", utc_now_iso()),
                intent=m.get("intent"),
                query_spec=m.get("query_spec"),
                file_id=m.get("file_id")
            )
            for m in raw_msgs
        ]

    def delete_message(self, message_id: str) -> bool:
        # Search all chats for this message_id
        for chat_folder in self.storage_dir.iterdir():
            if chat_folder.is_dir():
                cid = chat_folder.name
                data = self._load_json(cid)
                if data and "messages" in data:
                    msgs = data["messages"]
                    filtered = [m for m in msgs if (m.get("message_id") != message_id and m.get("id") != message_id)]
                    if len(filtered) < len(msgs):
                        data["messages"] = filtered
                        data["updated_at"] = utc_now_iso()
                        self._save_json(cid, data)
                        return True
        return False

    # ---------------------------------------------------------
    # Chat-Scoped File Storage Extensions
    # ---------------------------------------------------------

    def add_file(self, conversation_id: str, file_meta: Dict[str, Any]) -> Dict[str, Any]:
        """
        Appends file metadata to conversation.json's files array.
        """
        data = self._load_json(conversation_id)
        if not data:
            self.create_conversation(conversation_id=conversation_id)
            data = self._load_json(conversation_id)

        files = data.setdefault("files", [])
        fid = file_meta.get("file_id")

        # Replace existing entry if same file_id, else append
        existing_idx = next((i for i, f in enumerate(files) if f.get("file_id") == fid), None)
        if existing_idx is not None:
            files[existing_idx] = file_meta
        else:
            files.append(file_meta)

        data["dataset_id"] = fid
        data["updated_at"] = utc_now_iso()
        self._save_json(conversation_id, data)
        return file_meta

    def get_files(self, conversation_id: str) -> List[Dict[str, Any]]:
        """Retrieves files associated with a specific chat_id."""
        data = self._load_json(conversation_id)
        if not data:
            return []
        return data.get("files", [])

    def delete_file(self, conversation_id: str, file_id: str) -> bool:
        """Deletes a file entry from conversation.json and removes file from disk."""
        data = self._load_json(conversation_id)
        if not data:
            return False

        files = data.get("files", [])
        target_file = next((f for f in files if f.get("file_id") == file_id), None)
        if not target_file:
            return False

        # Remove from json list
        data["files"] = [f for f in files if f.get("file_id") != file_id]
        if data.get("dataset_id") == file_id:
            data["dataset_id"] = data["files"][-1].get("file_id") if data["files"] else None

        data["updated_at"] = utc_now_iso()
        self._save_json(conversation_id, data)

        # Remove disk files
        chat_files_dir = self._get_chat_dir(conversation_id) / "files"
        for p_file in chat_files_dir.glob(f"{file_id}.*"):
            try:
                p_file.unlink()
            except Exception as e:
                logger.warning(f"Could not remove chat file {p_file}: {e}")

        return True

    def get_chat_json(self, conversation_id: str) -> Optional[Dict[str, Any]]:
        """Returns complete conversation.json dictionary."""
        return self._load_json(conversation_id)
