"""
Business logic service for conversations and chat history management.
Orchestrates title generation, context window retrieval, and dataset associations.
"""

import re
import logging
from typing import Any, Dict, List, Optional, Union

from .models import Conversation, Message
from .repository import BaseChatRepository
from .json_repository import JsonChatRepository
from .sqlite_repository import SqliteChatRepository
from .context_resolver import ContextResolver

logger = logging.getLogger(__name__)

# Default limit for historical context messages sent to LLM/processor
DEFAULT_CONTEXT_MESSAGE_LIMIT = 10


def generate_deterministic_title(first_message: str) -> str:
    """
    Generates a clean, deterministic conversation title from the first user query.
    No LLM call needed for V1.
    
    Examples:
    - 'list the A grade count in each subject' -> 'A Grade Count in Each Subject'
    - 'show sales by region' -> 'Sales by Region'
    - 'visualize the average score per department' -> 'Average Score per Department'
    """
    if not first_message or not first_message.strip():
        return "New Analysis"

    text = first_message.strip()
    # Remove leading command phrases (case-insensitive)
    command_prefixes = [
        r"^(?:please\s+)?(?:can\s+you\s+)?(?:could\s+you\s+)?",
        r"^(?:list\s+(?:all\s+)?(?:the\s+)?|show\s+(?:me\s+)?(?:the\s+)?|give\s+(?:me\s+)?(?:the\s+)?|display\s+(?:the\s+)?|find\s+(?:the\s+)?|get\s+(?:the\s+)?|visualize\s+(?:the\s+)?|plot\s+(?:the\s+)?|chart\s+(?:the\s+)?|what\s+is\s+(?:the\s+)?|what\s+are\s+(?:the\s+)?|tell\s+me\s+(?:about\s+)?(?:the\s+)?|calculate\s+(?:the\s+)?|count\s+(?:the\s+)?)"
    ]

    cleaned = text
    for prefix in command_prefixes:
        cleaned = re.sub(prefix, "", cleaned, flags=re.IGNORECASE).strip()

    # Clean special characters at the end (like question marks, periods)
    cleaned = re.sub(r"[?!.,:;]+$", "", cleaned).strip()

    if not cleaned:
        cleaned = text[:40]

    # Convert to Title Case words
    words = cleaned.split()
    if not words:
        return "New Analysis"

    # Limit to first 7 words or 45 chars
    shortened = " ".join(words[:7])
    if len(shortened) > 45:
        shortened = shortened[:42].rstrip() + "..."

    # Capitalize appropriately
    title = shortened.title()
    return title if len(title) >= 3 else "New Analysis"


class ChatService:
    """
    High-level service coordinating conversation management, chat-scoped file storage, messaging, and context resolution.
    """

    def __init__(self, repository: Optional[BaseChatRepository] = None):
        self.repository = repository or JsonChatRepository()
        self.context_resolver = ContextResolver()

    def create_conversation(
        self,
        title: Optional[str] = "New Chat",
        dataset_id: Optional[str] = None,
        conversation_id: Optional[str] = None
    ) -> Conversation:
        return self.repository.create_conversation(
            title=title or "New Chat",
            dataset_id=dataset_id,
            conversation_id=conversation_id
        )

    def get_conversation(self, conversation_id: str) -> Optional[Conversation]:
        return self.repository.get_conversation(conversation_id)

    def list_conversations(self, limit: int = 100, offset: int = 0) -> List[Conversation]:
        return self.repository.list_conversations(limit=limit, offset=offset)

    def update_conversation(
        self,
        conversation_id: str,
        title: Optional[str] = None,
        dataset_id: Optional[str] = None
    ) -> Optional[Conversation]:
        return self.repository.update_conversation(
            conversation_id=conversation_id,
            title=title,
            dataset_id=dataset_id
        )

    def delete_conversation(self, conversation_id: str) -> bool:
        return self.repository.delete_conversation(conversation_id)

    def associate_dataset(self, conversation_id: str, dataset_id: str) -> Optional[Conversation]:
        """Associates a dataset with an existing conversation."""
        return self.repository.update_conversation(
            conversation_id=conversation_id,
            dataset_id=dataset_id
        )

    def add_user_message(
        self,
        conversation_id: str,
        content: str,
        file_id: Optional[str] = None
    ) -> Message:
        return self.repository.create_message(
            conversation_id=conversation_id,
            role="user",
            content=content,
            file_id=file_id
        )

    def add_assistant_message(
        self,
        conversation_id: str,
        content: str,
        result_json: Optional[Dict[str, Any]] = None,
        visualization_json: Optional[Union[Dict[str, Any], List[Dict[str, Any]]]] = None,
        intent: Optional[Dict[str, Any]] = None,
        query_spec: Optional[Dict[str, Any]] = None,
        file_id: Optional[str] = None
    ) -> Message:
        return self.repository.create_message(
            conversation_id=conversation_id,
            role="assistant",
            content=content,
            result_json=result_json,
            visualization_json=visualization_json,
            intent=intent,
            query_spec=query_spec,
            file_id=file_id
        )

    def get_messages(self, conversation_id: str, limit: Optional[int] = None) -> List[Message]:
        return self.repository.get_messages(conversation_id, limit=limit)

    def add_file(self, conversation_id: str, file_meta: Dict[str, Any]) -> Dict[str, Any]:
        """Adds file metadata to chat storage."""
        if hasattr(self.repository, "add_file"):
            return self.repository.add_file(conversation_id, file_meta)
        return file_meta

    def get_files(self, conversation_id: str) -> List[Dict[str, Any]]:
        """Gets all files associated with a specific chat_id."""
        if hasattr(self.repository, "get_files"):
            return self.repository.get_files(conversation_id)
        return []

    def delete_file(self, conversation_id: str, file_id: str) -> bool:
        """Deletes a file entry and raw/processed files from chat storage."""
        if hasattr(self.repository, "delete_file"):
            return self.repository.delete_file(conversation_id, file_id)
        return False

    def get_chat_detail(self, conversation_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieves full chat state including files and messages from conversation.json.
        """
        if hasattr(self.repository, "get_chat_json"):
            raw_data = self.repository.get_chat_json(conversation_id)
            if raw_data:
                return {
                    "chat_id": raw_data.get("chat_id") or conversation_id,
                    "title": raw_data.get("title", "New Chat"),
                    "dataset_id": raw_data.get("dataset_id"),
                    "created_at": raw_data.get("created_at"),
                    "updated_at": raw_data.get("updated_at"),
                    "files": raw_data.get("files", []),
                    "messages": raw_data.get("messages", [])
                }
        conv = self.get_conversation(conversation_id)
        if not conv:
            return None
        messages = [m.to_dict() for m in self.get_messages(conversation_id)]
        return {
            "chat_id": conv.id,
            "title": conv.title,
            "dataset_id": conv.dataset_id,
            "created_at": conv.created_at,
            "updated_at": conv.updated_at,
            "files": [],
            "messages": messages
        }

    def resolve_query_context(
        self,
        conversation_id: str,
        user_query: str
    ):
        """
        Invokes ContextResolver to handle follow-up query context and compact LLM payload.
        """
        files = self.get_files(conversation_id)
        messages_raw = [m.to_dict() for m in self.get_messages(conversation_id)]
        return self.context_resolver.resolve_context(
            chat_id=conversation_id,
            current_query=user_query,
            messages=messages_raw,
            files=files
        )

    def get_context_history(
        self,
        conversation_id: str,
        limit: int = DEFAULT_CONTEXT_MESSAGE_LIMIT
    ) -> List[Dict[str, str]]:
        """
        Retrieves recent conversation messages formatted for LLM context.
        Bounded by limit to prevent overflowing prompt limits.
        """
        messages = self.repository.get_messages(conversation_id, limit=limit)
        return [
            {
                "role": msg.role,
                "content": msg.content
            }
            for msg in messages
        ]

    def handle_query_session(
        self,
        conversation_id: Optional[str],
        user_message_text: str,
        dataset_id: Optional[str] = None
    ) -> Conversation:
        """
        Ensures a conversation exists, associates dataset if present,
        and auto-generates a useful title on the first user message.
        """
        conversation = None

        if conversation_id:
            conversation = self.get_conversation(conversation_id)

        if not conversation:
            # Create a new conversation
            initial_title = generate_deterministic_title(user_message_text)
            conversation = self.create_conversation(
                title=initial_title,
                dataset_id=dataset_id,
                conversation_id=conversation_id
            )
        else:
            # Check if conversation needs title update or dataset update
            updates = {}
            if conversation.title in ("New Chat", "New Analysis", ""):
                updates["title"] = generate_deterministic_title(user_message_text)
            if dataset_id and conversation.dataset_id != dataset_id:
                updates["dataset_id"] = dataset_id

            if updates:
                updated_conv = self.update_conversation(
                    conversation_id=conversation.id,
                    title=updates.get("title"),
                    dataset_id=updates.get("dataset_id")
                )
                if updated_conv:
                    conversation = updated_conv

        return conversation

