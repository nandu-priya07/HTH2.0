"""
Chat and conversation persistence module.
Provides domain models, repositories, and services for persistent chat history.
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
from .sqlite_repository import SqliteChatRepository
from .service import ChatService, generate_deterministic_title
from .database import initialize_database, get_database_path, get_db_connection
from .memory_repository import MemoryChatRepository
from auth import current_guest_id, current_user

# Global singleton service instance
_chat_service_instance: Optional[ChatService] = None
_user_services: dict[str, ChatService] = {}
_guest_services: dict[str, tuple[float, ChatService]] = {}
_GUEST_TTL_SECONDS = 8 * 60 * 60


def get_chat_service() -> ChatService:
    """
    Factory / Dependency provider for ChatService.
    Can be configured via environment or swapped for test mocks.
    """
    global _chat_service_instance
    user = current_user()
    if user:
        user_id = user["id"]
        if user_id not in _user_services:
            _user_services[user_id] = ChatService(repository=SqliteChatRepository(owner_id=user_id))
        return _user_services[user_id]

    guest_id = current_guest_id()
    if guest_id:
        now = monotonic()
        expired = [key for key, (last_seen, _) in _guest_services.items() if now - last_seen > _GUEST_TTL_SECONDS]
        for key in expired:
            _, expired_service = _guest_services.pop(key, (now, None))
            if expired_service:
                try:
                    from storage.dataset_manager import DATASET_REGISTRY
                    for conversation in expired_service.list_conversations(limit=500):
                        if conversation.dataset_id:
                            DATASET_REGISTRY.pop(conversation.dataset_id, None)
                        for file_meta in expired_service.get_files(conversation.id):
                            DATASET_REGISTRY.pop(file_meta.get("file_id"), None)
                except Exception:
                    pass
        entry = _guest_services.get(guest_id)
        if entry:
            service = entry[1]
        else:
            service = ChatService(repository=MemoryChatRepository())
        _guest_services[guest_id] = (now, service)
        return service

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
