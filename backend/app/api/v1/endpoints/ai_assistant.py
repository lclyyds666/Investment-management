"""Authenticated user APIs for AI assistant conversations."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.ai_assistant import AiConversationCreate, AiConversationOut, AiConversationUpdate
from app.schemas.common import Response
from app.services.ai_conversations import (
    create_conversation,
    delete_owned_conversation,
    get_owned_conversation,
    list_owned_conversations,
    rename_owned_conversation,
    suggestions_for_user,
)

router = APIRouter()


@router.get("/suggestions", response_model=Response[list[str]], summary="AI 助手建议问题")
def get_suggestions(
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
):
    return Response.ok(suggestions_for_user(db, current_user))


@router.get("/conversations", response_model=Response[dict], summary="AI 会话列表")
def list_conversations(
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=50),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rows, total = list_owned_conversations(db, current_user.id, page=page, size=size)
    return Response.ok({
        "items": [AiConversationOut.model_validate(row) for row in rows],
        "total": total,
        "page": page,
        "size": size,
    })


@router.post("/conversations", response_model=Response[AiConversationOut], summary="新建 AI 会话")
def create_new_conversation(
    payload: AiConversationCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    conversation = create_conversation(db, current_user.id, payload.title)
    return Response.ok(AiConversationOut.model_validate(conversation), message="会话已创建")


@router.get("/conversations/{conversation_id}", response_model=Response[AiConversationOut], summary="AI 会话详情")
def get_conversation(
    conversation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    conversation = get_owned_conversation(
        db,
        conversation_id,
        current_user.id,
        with_messages=True,
        is_information_maintainer=current_user.is_superuser,
    )
    return Response.ok(AiConversationOut.model_validate(conversation))


@router.patch("/conversations/{conversation_id}", response_model=Response[AiConversationOut], summary="重命名 AI 会话")
def rename_conversation(
    conversation_id: int,
    payload: AiConversationUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    conversation = rename_owned_conversation(db, conversation_id, current_user.id, payload.title)
    return Response.ok(AiConversationOut.model_validate(conversation), message="会话已重命名")


@router.delete("/conversations/{conversation_id}", response_model=Response[dict], summary="删除 AI 会话")
def delete_conversation(
    conversation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    receipt = delete_owned_conversation(db, conversation_id, current_user.id)
    return Response.ok(
        {"id": conversation_id, "deleted_message_count": receipt.deleted_message_count},
        message="会话已删除",
    )
