from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, status
from sqlalchemy import and_, func, or_, select

from app.api.common import SettingsDep, envelope, message_view, owned_conversation
from app.api.deps import CsrfProtected, CurrentUser, Db
from app.models import AgentRun, Attachment, Message, RunStatus
from app.pagination import decode_cursor, encode_cursor
from app.schemas import MessageCreate
from app.services.runs import process_agent_run

router = APIRouter(tags=["messages"])


@router.get("/conversations/{conversation_id}/messages")
async def list_messages(
    conversation_id: str,
    request: Request,
    db: Db,
    user: CurrentUser,
    settings: SettingsDep,
    limit: int | None = None,
    before: str = "",
) -> dict[str, object]:
    """游标分页：默认返回最近一页（升序）；before 读取更早消息。"""
    await owned_conversation(db, conversation_id, user)
    if settings.message_pagination_legacy_default and limit is None and not before:
        items = list(
            (
                await db.scalars(
                    select(Message)
                    .where(Message.conversation_id == conversation_id)
                    .order_by(Message.created_at, Message.id)
                )
            ).all()
        )
        return envelope(
            request,
            {
                "items": [message_view(item) for item in items],
                "next_cursor": None,
                "has_more": False,
            },
        )

    page_size = min(
        max(limit if limit is not None else settings.message_pagination_default_limit, 1),
        settings.message_pagination_max_limit,
    )
    conditions = [Message.conversation_id == conversation_id]
    cursor = decode_cursor(before or None)
    if cursor:
        cursor_time, cursor_id = cursor
        cursor_time = cursor_time.replace(tzinfo=None)
        conditions.append(
            or_(
                Message.created_at < cursor_time,
                and_(Message.created_at == cursor_time, Message.id < cursor_id),
            )
        )
    rows = list(
        (
            await db.scalars(
                select(Message)
                .where(*conditions)
                .order_by(Message.created_at.desc(), Message.id.desc())
                .limit(page_size)
            )
        ).all()
    )
    rows.reverse()
    has_more = False
    next_cursor = None
    if rows:
        has_more = (
            await db.scalar(
                select(func.count())
                .select_from(Message)
                .where(
                    Message.conversation_id == conversation_id,
                    or_(
                        Message.created_at
                        < (
                            rows[0].created_at.replace(tzinfo=None)
                            if rows[0].created_at.tzinfo
                            else rows[0].created_at
                        ),
                        and_(
                            Message.created_at
                            == (
                                rows[0].created_at.replace(tzinfo=None)
                                if rows[0].created_at.tzinfo
                                else rows[0].created_at
                            ),
                            Message.id < rows[0].id,
                        ),
                    ),
                )
            )
            or 0
        ) > 0
        next_cursor = encode_cursor(rows[0].created_at, rows[0].id)
    return envelope(
        request,
        {
            "items": [message_view(item) for item in rows],
            "next_cursor": next_cursor if has_more else None,
            "has_more": has_more,
        },
    )


@router.post("/conversations/{conversation_id}/messages", status_code=status.HTTP_202_ACCEPTED)
async def submit_message(
    conversation_id: str,
    payload: MessageCreate,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Db,
    user: CurrentUser,
    _: CsrfProtected,
) -> dict[str, object]:
    conversation = await owned_conversation(db, conversation_id, user)
    existing_message = await db.scalar(
        select(Message).where(
            Message.conversation_id == conversation_id,
            Message.client_message_id == payload.client_message_id,
        )
    )
    if existing_message:
        existing_run = await db.scalar(
            select(AgentRun).where(AgentRun.user_message_id == existing_message.id)
        )
        if existing_run:
            return envelope(request, {"run_id": existing_run.id, "idempotent_replay": True})

    message = Message(
        conversation_id=conversation_id,
        role="user",
        content=payload.content,
        client_message_id=payload.client_message_id,
        metadata_json={"tool_mode": payload.tool_mode, "mcp_server_ids": payload.mcp_server_ids},
    )
    db.add(message)
    await db.flush()
    if payload.tool_mode == "selected" and not payload.mcp_server_ids:
        raise HTTPException(status_code=422, detail="MCP_SERVER_SELECTION_REQUIRED")
    if payload.attachment_ids:
        attachments = list(
            (
                await db.scalars(
                    select(Attachment).where(
                        Attachment.id.in_(set(payload.attachment_ids)),
                        Attachment.user_id == user.id,
                        Attachment.message_id.is_(None),
                    )
                )
            ).all()
        )
        if len(attachments) != len(set(payload.attachment_ids)):
            raise HTTPException(status_code=422, detail="ATTACHMENT_INVALID")
        for attachment in attachments:
            attachment.message_id = message.id
    run = AgentRun(
        user_id=user.id,
        conversation_id=conversation_id,
        user_message_id=message.id,
        status=RunStatus.QUEUED,
        queued_at=datetime.now(timezone.utc),
    )
    db.add(run)
    if conversation.title == "新对话":
        conversation.title = payload.content.strip().replace("\n", " ")[:40]
    conversation.updated_at = datetime.now(timezone.utc)
    await db.commit()

    dispatcher = getattr(request.app.state, "run_dispatcher", None)
    if dispatcher is not None:
        dispatcher.notify(run.id)
    else:
        background_tasks.add_task(process_agent_run, run.id)
    return envelope(request, {"run_id": run.id, "idempotent_replay": False})
