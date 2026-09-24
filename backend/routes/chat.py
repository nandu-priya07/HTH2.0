"""
FastAPI REST Routes for Persistent Conversations, Chat Scoped Storage, and JSON Context.
"""

import logging
from typing import List, Optional, Dict, Any
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

router = APIRouter(tags=["conversations"])


@router.post("/chats", response_model=ConversationResponse, status_code=status.HTTP_201_CREATED)
@router.post("/api/chats", response_model=ConversationResponse, status_code=status.HTTP_201_CREATED)
@router.post("/api/conversations", response_model=ConversationResponse, status_code=status.HTTP_201_CREATED)
@router.post("/api/conversations/", response_model=ConversationResponse, status_code=status.HTTP_201_CREATED)
async def create_new_conversation(payload: Optional[CreateConversationRequest] = None):
    """
    Creates a new chat session with chat_id, conversation.json, and files/ storage directory.
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


@router.get("/chats")
@router.get("/api/chats")
@router.get("/api/conversations")
@router.get("/api/conversations/")
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
        res_list = []
        for c in conversations:
            files = service.get_files(c.id)
            res_list.append({
                "id": c.id,
                "chat_id": c.id,
                "title": c.title,
                "dataset_id": c.dataset_id,
                "created_at": c.created_at,
                "updated_at": c.updated_at,
                "files": files
            })
        return res_list
    except Exception as e:
        logger.error(f"Error listing conversations: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list conversations: {str(e)}"
        )


@router.get("/chats/{chat_id}")
@router.get("/api/chats/{chat_id}")
@router.get("/api/conversations/{chat_id}")
async def get_conversation_details(chat_id: str):
    """
    Requirement 4: Existing Chat Reopening.
    Returns full chat state from conversation.json:
    {
      "chat_id": "chat_001",
      "title": "SEM_V Analysis",
      "files": [...],
      "messages": [...]
    }
    """
    service = get_chat_service()
    detail = service.get_chat_detail(chat_id)
    if not detail:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Chat '{chat_id}' not found"
        )

    # Maintain backward compatibility for callers expecting ConversationResponse keys
    detail["id"] = detail["chat_id"]
    return JSONResponse(status_code=status.HTTP_200_OK, content=detail)


@router.patch("/chats/{chat_id}")
@router.patch("/api/chats/{chat_id}")
@router.patch("/api/conversations/{chat_id}")
async def update_conversation(
    chat_id: str,
    payload: UpdateConversationRequest
):
    """
    Updates conversation title and/or associated dataset_id.
    """
    service = get_chat_service()
    updated = service.update_conversation(
        conversation_id=chat_id,
        title=payload.title,
        dataset_id=payload.dataset_id
    )
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Chat '{chat_id}' not found"
        )

    return ConversationResponse(
        id=updated.id,
        title=updated.title,
        dataset_id=updated.dataset_id,
        created_at=updated.created_at,
        updated_at=updated.updated_at
    )


@router.delete("/chats/{chat_id}")
@router.delete("/api/chats/{chat_id}")
@router.delete("/api/conversations/{chat_id}")
async def delete_conversation(chat_id: str):
    """
    Deletes a conversation directory and all its files/messages.
    """
    service = get_chat_service()
    deleted = service.delete_conversation(chat_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Chat '{chat_id}' not found"
        )

    return {"success": True, "id": chat_id, "chat_id": chat_id, "message": "Conversation deleted"}


@router.get("/chats/{chat_id}/messages")
@router.get("/api/chats/{chat_id}/messages")
@router.get("/api/conversations/{chat_id}/messages")
async def get_conversation_messages(
    chat_id: str,
    limit: Optional[int] = Query(default=None, ge=1, le=1000)
):
    """
    Retrieves messages for a conversation ordered chronologically (oldest to newest).
    """
    service = get_chat_service()
    conv = service.get_conversation(chat_id)
    if not conv:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Chat '{chat_id}' not found"
        )

    messages = service.get_messages(chat_id, limit=limit)
    return [
        MessageResponse(
            id=m.id,
            conversation_id=m.conversation_id,
            role=m.role,
            content=m.content,
            result=m.result_json,
            visualization=m.visualization_json,
            intent=m.intent,
            query_spec=m.query_spec,
            file_id=m.file_id,
            created_at=m.created_at
        )
        for m in messages
    ]
