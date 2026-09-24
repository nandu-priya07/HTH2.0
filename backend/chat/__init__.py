"""
Chat and conversation persistence module.
Provides domain models, repositories, and services for persistent chat history.
"""

from typing import Optional
from .models import (
    Conversation,
    Message,
    CreateConversationRequest,
    UpdateConversationRequest,
    ConversationResponse,
    MessageResponse,
    ChatResponse
)
from .repository import BaseChatRepository
from .sqlite_repository import SqliteChatRepository
from .service import ChatService, generate_deterministic_title
from .database import initialize_database, get_database_path, get_db_connection

# Global singleton service instance
_chat_service_instance: Optional[ChatService] = None


def get_chat_service() -> ChatService:
    """
    Factory / Dependency provider for ChatService.
    Can be configured via environment or swapped for test mocks.
    """
    global _chat_service_instance
    if _chat_service_instance is None:
        repository = SqliteChatRepository()
        _chat_service_instance = ChatService(repository=repository)
    return _chat_service_instance


__all__ = [
    "Conversation",
    "Message",
    "CreateConversationRequest",
    "UpdateConversationRequest",
    "ConversationResponse",
    "MessageResponse",
    "ChatResponse",
    "BaseChatRepository",
    "SqliteChatRepository",
    "ChatService",
    "generate_deterministic_title",
    "initialize_database",
    "get_database_path",
    "get_db_connection",
    "get_chat_service"
]
