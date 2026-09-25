"""
Chat and conversation persistence module.
Provides domain models, repositories, and services for persistent chat history using Supabase PostgreSQL.
"""

from typing import Optional
from time import monotonic
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
from .supabase_repository import SupabaseChatRepository
from .service import ChatService, generate_deterministic_title
from .memory_repository import MemoryChatRepository
from auth import current_guest_id, current_user

# Global singleton service instance
_chat_service_instance: Optional[ChatService] = None
_user_services: dict[str, ChatService] = {}
_guest_services: dict[str, tuple[float, ChatService]] = {}
_GUEST_TTL_SECONDS = 8 * 60 * 60


def get_chat_service() -> ChatService:
    """
    Factory / Dependency provider for ChatService backed by Supabase PostgreSQL.
    """
    global _chat_service_instance
    user = current_user()
    if user:
        user_id = str(user["id"])
        if user_id not in _user_services:
            _user_services[user_id] = ChatService(repository=SupabaseChatRepository(owner_id=user_id))
        return _user_services[user_id]

    guest_id = current_guest_id()
    if guest_id:
        if guest_id not in _user_services:
            _user_services[guest_id] = ChatService(repository=SupabaseChatRepository(owner_id=guest_id))
        return _user_services[guest_id]

    if _chat_service_instance is None:
        repository = SupabaseChatRepository()
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
    "SupabaseChatRepository",
    "ChatService",
    "generate_deterministic_title",
    "get_chat_service"
]
