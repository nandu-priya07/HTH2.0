"""
Data models and schemas for Chat History and Conversation Management.
Designed for persistence neutrality (SQLite today, Supabase/PostgreSQL ready).
"""

from typing import Any, Dict, List, Optional, Union
from datetime import datetime, timezone
from pydantic import BaseModel, Field


def utc_now_iso() -> str:
    """Returns current UTC timestamp in ISO 8601 string format."""
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------
# DOMAIN ENTITY MODELS
# ---------------------------------------------------------

class Conversation(BaseModel):
    """
    Core conversation entity representing a user's chat session.
    """
    id: str
    title: str = "New Chat"
    dataset_id: Optional[str] = None
    created_at: str = Field(default_factory=utc_now_iso)
    updated_at: str = Field(default_factory=utc_now_iso)

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump()


class Message(BaseModel):
    """
    Individual message in a conversation.
    Supports storing unstructured text as well as structured analytical results and visualization metadata.
    """
    id: str
    conversation_id: str
    role: str  # "user" | "assistant" | "system"
    content: str
    result_json: Optional[Dict[str, Any]] = None  # Structured analytical results (table, scalar, scalars, list)
    visualization_json: Optional[Union[Dict[str, Any], List[Dict[str, Any]]]] = None  # Chart / KPI configuration
    created_at: str = Field(default_factory=utc_now_iso)

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump()


# ---------------------------------------------------------
# API REQUEST & RESPONSE SCHEMAS
# ---------------------------------------------------------

class CreateConversationRequest(BaseModel):
    title: Optional[str] = "New Chat"
    dataset_id: Optional[str] = None


class UpdateConversationRequest(BaseModel):
    title: Optional[str] = None
    dataset_id: Optional[str] = None


class ConversationResponse(BaseModel):
    id: str
    title: str
    dataset_id: Optional[str] = None
    created_at: str
    updated_at: str
    message_count: Optional[int] = None
    last_message: Optional[str] = None


class MessageResponse(BaseModel):
    id: str
    conversation_id: str
    role: str
    content: str
    result: Optional[Dict[str, Any]] = None
    visualization: Optional[Union[Dict[str, Any], List[Dict[str, Any]]]] = None
    created_at: str


class ChatResponse(BaseModel):
    conversation_id: str
    user_message: MessageResponse
    assistant_message: MessageResponse
    dataset_id: Optional[str] = None
