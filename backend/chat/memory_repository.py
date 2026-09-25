"""Request-session-only chat repository for visitors who are not signed in."""
import json
import uuid
from typing import Any, Dict, List, Optional, Union

from .models import Conversation, Message, utc_now_iso
from .repository import BaseChatRepository


class MemoryChatRepository(BaseChatRepository):
    def __init__(self):
        self.conversations: dict[str, Conversation] = {}
        self.messages: dict[str, list[Message]] = {}
        self.files: dict[str, list[dict]] = {}

    def create_conversation(self, title="New Chat", dataset_id=None, conversation_id=None):
        cid = conversation_id or str(uuid.uuid4())
        if cid in self.conversations:
            return self.conversations[cid]
        now = utc_now_iso()
        conv = Conversation(id=cid, title=(title or "New Chat").strip()[:100], dataset_id=dataset_id, created_at=now, updated_at=now)
        self.conversations[cid] = conv
        self.messages[cid] = []
        self.files[cid] = []
        return conv

    def get_conversation(self, conversation_id):
        return self.conversations.get(conversation_id)

    def list_conversations(self, limit=100, offset=0):
        values = sorted(self.conversations.values(), key=lambda item: item.updated_at, reverse=True)
        return values[offset:offset + limit]

    def update_conversation(self, conversation_id, title=None, dataset_id=None):
        current = self.conversations.get(conversation_id)
        if not current: return None
        updated = current.model_copy(update={"title": title.strip()[:100] if title is not None else current.title,
            "dataset_id": dataset_id if dataset_id is not None else current.dataset_id, "updated_at": utc_now_iso()})
        self.conversations[conversation_id] = updated
        return updated

    def update_conversation_timestamp(self, conversation_id):
        return self.update_conversation(conversation_id) is not None

    def delete_conversation(self, conversation_id):
        existed = self.conversations.pop(conversation_id, None) is not None
        self.messages.pop(conversation_id, None)
        self.files.pop(conversation_id, None)
        return existed

    def create_message(self, conversation_id, role, content, result_json=None, visualization_json=None,
                       message_id=None, intent=None, query_spec=None, file_id=None):
        message = Message(id=message_id or str(uuid.uuid4()), conversation_id=conversation_id,
            role=role if role in ("user", "assistant", "system") else "user", content=content,
            result_json=result_json, visualization_json=visualization_json, intent=intent,
            query_spec=query_spec, file_id=file_id)
        self.messages.setdefault(conversation_id, []).append(message)
        self.update_conversation_timestamp(conversation_id)
        return message

    def get_messages(self, conversation_id, limit=None):
        messages = self.messages.get(conversation_id, [])
        return messages[-limit:] if limit and limit > 0 else list(messages)

    def delete_message(self, message_id):
        for messages in self.messages.values():
            for index, message in enumerate(messages):
                if message.id == message_id:
                    del messages[index]
                    return True
        return False

    def add_file(self, conversation_id, file_meta):
        files = self.files.setdefault(conversation_id, [])
        files[:] = [item for item in files if item.get("file_id") != file_meta.get("file_id")]
        files.append(dict(file_meta))
        self.update_conversation(conversation_id, dataset_id=file_meta.get("file_id"))
        return file_meta

    def get_files(self, conversation_id):
        return list(self.files.get(conversation_id, []))

    def delete_file(self, conversation_id, file_id):
        files = self.files.get(conversation_id, [])
        remaining = [item for item in files if item.get("file_id") != file_id]
        if len(remaining) == len(files): return False
        self.files[conversation_id] = remaining
        current = self.conversations.get(conversation_id)
        if current and current.dataset_id == file_id:
            self.update_conversation(conversation_id, dataset_id=remaining[-1].get("file_id") if remaining else None)
        return True

    def get_chat_json(self, conversation_id):
        conv = self.get_conversation(conversation_id)
        if not conv: return None
        return {**conv.to_dict(), "chat_id": conv.id, "files": self.get_files(conversation_id),
            "messages": [item.to_dict() for item in self.get_messages(conversation_id)]}
