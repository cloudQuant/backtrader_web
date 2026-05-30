"""KB chat API routes for iteration 129."""

from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import get_current_user
from app.schemas.auth import TokenPayload
from app.schemas.kb_chat import (
    ChatHistoryResponse,
    ChatMessageResponse,
    ConversationCreate,
    ConversationListResponse,
    ConversationResponse,
    KBChatRequest,
    KBChatResponse,
)
from app.services.kb_chat_service import KBChatService

router = APIRouter()


@lru_cache
def get_kb_chat_service() -> KBChatService:
    return KBChatService()


@router.get("/conversations", response_model=ConversationListResponse, summary="List conversations")
async def list_conversations(
    knowledge_base_id: str = Query(...),
    current_user: TokenPayload = Depends(get_current_user),
    service: KBChatService = Depends(get_kb_chat_service),
):
    items = await service.list_conversations(knowledge_base_id, current_user.sub)
    if items is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge base not found"
        )
    return ConversationListResponse(
        total=len(items),
        items=[ConversationResponse.model_validate(item) for item in items],
    )


@router.post(
    "/conversations",
    response_model=ConversationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create conversation",
)
async def create_conversation(
    data: ConversationCreate,
    current_user: TokenPayload = Depends(get_current_user),
    service: KBChatService = Depends(get_kb_chat_service),
):
    conversation = await service.create_conversation(current_user.sub, data)
    if conversation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge base not found"
        )
    return ConversationResponse.model_validate(conversation)


@router.get("/history/{conversation_id}", response_model=ChatHistoryResponse, summary="Get history")
async def get_history(
    conversation_id: str,
    current_user: TokenPayload = Depends(get_current_user),
    service: KBChatService = Depends(get_kb_chat_service),
):
    result = await service.get_history(conversation_id, current_user.sub)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
    conv_id, messages = result
    return ChatHistoryResponse(
        conversation_id=conv_id,
        messages=[ChatMessageResponse.model_validate(item) for item in messages],
    )


@router.delete("/conversations/{conversation_id}", summary="Delete conversation")
async def delete_conversation(
    conversation_id: str,
    current_user: TokenPayload = Depends(get_current_user),
    service: KBChatService = Depends(get_kb_chat_service),
):
    success = await service.delete_conversation(conversation_id, current_user.sub)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
    return {"message": "Conversation deleted"}


@router.post("/send", response_model=KBChatResponse, summary="Send message")
async def send_message(
    data: KBChatRequest,
    current_user: TokenPayload = Depends(get_current_user),
    service: KBChatService = Depends(get_kb_chat_service),
):
    result = await service.send(current_user.sub, data)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge base or conversation not found"
        )
    return KBChatResponse(**result)
