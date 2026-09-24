"""
FastAPI REST Routes for Persistent Conversations and Message History.
Pure API layer calling ChatService with no direct database or SQL operations.
"""

import logging
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import JSONResponse

from chat.models import (
    CreateConversationRequest,
    UpdateConversationRequest,
    ConversationResponse,
    MessageResponse
)
from chat import get_chat_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/conversations", tags=["conversations"])


@router.post("", response_model=ConversationResponse, status_code=status.HTTP_201_CREATED)
@router.post("/", response_model=ConversationResponse, status_code=status.HTTP_201_CREATED)
async def create_new_conversation(payload: Optional[CreateConversationRequest] = None):
    """
    Creates a new conversation session.
    """
    try:
        service = get_chat_service()
        title = payload.title if payload and payload.title else "New Chat"
        dataset_id = payload.dataset_id if payload else None

        conv = service.create_conversation(title=title, dataset_id=dataset_id)
        return ConversationResponse(
            id=conv.id,
            title=conv.title,
            dataset_id=conv.dataset_id,
            created_at=conv.created_at,
            updated_at=conv.updated_at
        )
    except Exception as e:
        logger.error(f"Error creating conversation: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create conversation: {str(e)}"
        )


@router.get("", response_model=List[ConversationResponse])
@router.get("/", response_model=List[ConversationResponse])
async def list_all_conversations(
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0)
):
    """
    Lists conversations ordered by updated_at descending (newest activity first).
    """
    try:
        service = get_chat_service()
        conversations = service.list_conversations(limit=limit, offset=offset)
        return [
            ConversationResponse(
                id=c.id,
                title=c.title,
                dataset_id=c.dataset_id,
                created_at=c.created_at,
                updated_at=c.updated_at
            )
            for c in conversations
        ]
    except Exception as e:
        logger.error(f"Error listing conversations: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list conversations: {str(e)}"
        )


@router.get("/{conversation_id}", response_model=ConversationResponse)
async def get_conversation_details(conversation_id: str):
    """
    Retrieves metadata for a specific conversation.
    """
    service = get_chat_service()
    conv = service.get_conversation(conversation_id)
    if not conv:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conversation '{conversation_id}' not found"
        )

    return ConversationResponse(
        id=conv.id,
        title=conv.title,
        dataset_id=conv.dataset_id,
        created_at=conv.created_at,
        updated_at=conv.updated_at
    )


@router.patch("/{conversation_id}", response_model=ConversationResponse)
async def update_conversation(
    conversation_id: str,
    payload: UpdateConversationRequest
):
    """
    Updates conversation title and/or associated dataset_id.
    """
    service = get_chat_service()
    updated = service.update_conversation(
        conversation_id=conversation_id,
        title=payload.title,
        dataset_id=payload.dataset_id
    )
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conversation '{conversation_id}' not found"
        )

    return ConversationResponse(
        id=updated.id,
        title=updated.title,
        dataset_id=updated.dataset_id,
        created_at=updated.created_at,
        updated_at=updated.updated_at
    )


@router.delete("/{conversation_id}")
async def delete_conversation(conversation_id: str):
    """
    Deletes a conversation and all its messages.
    Does NOT delete dataset files in uploads/ storage.
    """
    service = get_chat_service()
    deleted = service.delete_conversation(conversation_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conversation '{conversation_id}' not found"
        )

    return {"success": True, "id": conversation_id, "message": "Conversation deleted"}


@router.get("/{conversation_id}/messages", response_model=List[MessageResponse])
async def get_conversation_messages(
    conversation_id: str,
    limit: Optional[int] = Query(default=None, ge=1, le=1000)
):
    """
    Retrieves messages for a conversation ordered chronologically (oldest to newest).
    """
    service = get_chat_service()
    # Check conversation exists
    conv = service.get_conversation(conversation_id)
    if not conv:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conversation '{conversation_id}' not found"
        )

    messages = service.get_messages(conversation_id, limit=limit)
    return [
        MessageResponse(
            id=m.id,
            conversation_id=m.conversation_id,
            role=m.role,
            content=m.content,
            result=m.result_json,
            visualization=m.visualization_json,
            created_at=m.created_at
        )
        for m in messages
    ]
