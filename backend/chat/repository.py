"""
Abstract repository interface for chat conversations and messages.
Defines persistence operations to allow seamless migration between storage backends (SQLite, Supabase, PostgreSQL).
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Union
from .models import Conversation, Message


class BaseChatRepository(ABC):
    """
    Abstract interface for conversation and message data access.
    """

    @abstractmethod
    def create_conversation(
        self,
        title: str = "New Chat",
        dataset_id: Optional[str] = None,
        conversation_id: Optional[str] = None
    ) -> Conversation:
        """Create a new conversation."""
        pass

    @abstractmethod
    def get_conversation(self, conversation_id: str) -> Optional[Conversation]:
        """Retrieve a conversation by ID."""
        pass

    @abstractmethod
    def list_conversations(self, limit: int = 100, offset: int = 0) -> List[Conversation]:
        """List all conversations ordered by updated_at descending."""
        pass

    @abstractmethod
    def update_conversation(
        self,
        conversation_id: str,
        title: Optional[str] = None,
        dataset_id: Optional[str] = None
    ) -> Optional[Conversation]:
        """Update conversation title and/or associated dataset_id."""
        pass

    @abstractmethod
    def update_conversation_timestamp(self, conversation_id: str) -> bool:
        """Update the conversation's updated_at timestamp to now."""
        pass

    @abstractmethod
    def delete_conversation(self, conversation_id: str) -> bool:
        """Delete a conversation and all its associated messages."""
        pass

    @abstractmethod
    def create_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        result_json: Optional[Dict[str, Any]] = None,
        visualization_json: Optional[Union[Dict[str, Any], List[Dict[str, Any]]]] = None,
        message_id: Optional[str] = None
    ) -> Message:
        """Create and persist a message in a conversation."""
        pass

    @abstractmethod
    def get_messages(self, conversation_id: str, limit: Optional[int] = None) -> List[Message]:
        """Retrieve messages for a conversation ordered chronologically (oldest to newest)."""
        pass

    @abstractmethod
    def delete_message(self, message_id: str) -> bool:
        """Delete an individual message."""
        pass
