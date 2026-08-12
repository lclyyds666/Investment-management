"""Authenticated user APIs for AI assistant conversations."""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.api.deps import get_current_user, require_superuser
from app.db.session import get_db
from app.models.ai_assistant import AiConversation, AiMessage
from app.models.user import User
from app.schemas.ai_assistant import (
    AiConversationCreate,
    AiConversationOut,
    AiConversationSummaryOut,
    AiConversationUpdate,
    AiDeletionAuditOut,
    AdminAiConversationOut,
    AdminDeleteRequest,
    AiMessageCreate,
)
from app.schemas.common import Response
from app.services.ai_conversations import (
    begin_generation,
    create_conversation,
    delete_admin_conversation,
    delete_owned_conversation,
    get_admin_conversation,
    get_owned_conversation,
    list_owned_conversations,
    list_admin_conversations,
    list_deletion_audits,
    rename_owned_conversation,
    suggestions_for_user,
    stream_generation_in_session,
)
from app.services.ai_runtime import request_stop

router = APIRouter()


@router.get("/admin/conversations", response_model=Response[dict], summary="AI 会话审计列表")
def list_admin_conversation_records(
    user_id: int | None = None,
    started_at: datetime | None = None,
    ended_at: datetime | None = None,
    status_filter: str | None = Query(default=None, alias="status", max_length=24),
    keyword: str | None = Query(default=None, max_length=200),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=50),
    db: Session = Depends(get_db),
    _: User = Depends(require_superuser),
):
    rows, total = list_admin_conversations(
        db,
        user_id=user_id,
        started_at=started_at,
        ended_at=ended_at,
        conversation_status=status_filter,
        keyword=keyword,
        page=page,
        size=size,
    )
    return Response.ok({
        "items": [AiConversationSummaryOut.model_validate(row) for row in rows],
        "total": total,
        "page": page,
        "size": size,
    })


@router.get(
    "/admin/conversations/{conversation_id}",
    response_model=Response[AdminAiConversationOut],
    summary="AI 会话审计详情",
)
def get_admin_conversation_record(
    conversation_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_superuser),
):
    return Response.ok(AdminAiConversationOut.model_validate(
        get_admin_conversation(db, conversation_id)
    ))


@router.delete(
    "/admin/conversations/{conversation_id}",
    response_model=Response[AiDeletionAuditOut],
    summary="管理员删除 AI 会话",
)
def delete_admin_conversation_record(
    conversation_id: int,
    payload: AdminDeleteRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superuser),
):
    receipt = delete_admin_conversation(
        db, conversation_id, current_user.id, payload.reason
    )
    return Response.ok(AiDeletionAuditOut.model_validate(receipt), message="会话已删除")


@router.get(
    "/admin/deletion-audits",
    response_model=Response[dict],
    summary="AI 会话删除审计",
)
def get_deletion_audit_records(
    user_id: int | None = None,
    mode: str | None = Query(default=None, max_length=24),
    started_at: datetime | None = None,
    ended_at: datetime | None = None,
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=50),
    db: Session = Depends(get_db),
    _: User = Depends(require_superuser),
):
    rows, total = list_deletion_audits(
        db,
        user_id=user_id,
        mode=mode,
        started_at=started_at,
        ended_at=ended_at,
        page=page,
        size=size,
    )
    return Response.ok({
        "items": [AiDeletionAuditOut.model_validate(row) for row in rows],
        "total": total,
        "page": page,
        "size": size,
    })


@router.post(
    "/conversations/{conversation_id}/messages",
    summary="发送 AI 消息",
)
async def stream_message(
    conversation_id: int,
    payload: AiMessageCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    conversation = get_owned_conversation(db, conversation_id, current_user.id)
    user_message, assistant_message, lease, request_id = begin_generation(
        db,
        conversation,
        current_user.id,
        payload.content,
        payload.client_message_id,
    )
    stream_session_factory = sessionmaker(bind=db.get_bind())
    iterator = stream_generation_in_session(
        session_factory=stream_session_factory,
        conversation_id=conversation.id,
        user_message_id=user_message.id,
        assistant_message_id=assistant_message.id,
        lease=lease,
        request_id=request_id,
        request=request,
        user_id=current_user.id,
        is_superuser=current_user.is_superuser,
    )
    return StreamingResponse(
        iterator,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "X-Request-ID": request_id,
        },
    )


@router.post("/messages/{message_id}/stop", response_model=Response[dict], summary="停止 AI 生成")
def stop_message(
    message_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    message = db.scalar(
        select(AiMessage)
        .join(AiConversation, AiMessage.conversation_id == AiConversation.id)
        .where(AiMessage.id == message_id, AiConversation.owner_id == current_user.id)
    )
    if message is None or message.role != "assistant":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="消息不存在")
    if message.status == "generating":
        request_stop(message.id)
    return Response.ok({"id": message.id, "status": message.status})


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
