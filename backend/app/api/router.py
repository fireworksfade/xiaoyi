import asyncio
import json
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response, status
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select, tuple_

from app.api.attachments import router as attachments_router
from app.api.deps import CsrfProtected, CurrentUser, Db, current_session
from app.api.diagnosis import router as diagnosis_router
from app.api.fault_cases import router as fault_cases_router
from app.api.knowledge import router as knowledge_router
from app.api.mcp import router as mcp_router
from app.api.model_config import router as model_config_router
from app.api.remediation import router as remediation_router
from app.config import Settings, get_settings
from app.db import SessionFactory
from app.models import (
    AgentRun,
    Attachment,
    Conversation,
    MCPServer,
    MCPTool,
    Message,
    RunEvent,
    RunStatus,
    Session,
    ToolRiskPolicy,
    User,
)
from app.pagination import decode_cursor, encode_cursor
from app.schemas import ConversationCreate, ConversationUpdate, LoginRequest, MessageCreate
from app.security import opaque_token, token_hash, verify_password
from app.services.run_state import is_retryable
from app.services.runs import process_agent_run

router = APIRouter(prefix="/api/v1")
router.include_router(mcp_router)
router.include_router(diagnosis_router)
router.include_router(model_config_router)
router.include_router(attachments_router)
router.include_router(knowledge_router)
router.include_router(fault_cases_router)
router.include_router(remediation_router)
SettingsDep = Annotated[Settings, Depends(get_settings)]


def envelope(request: Request, data: object) -> dict[str, object]:
    return {"data": data, "request_id": request.state.request_id}


def user_view(user: User) -> dict[str, str]:
    return {"id": user.id, "username": user.username, "role": user.role.value}


def conversation_view(item: Conversation) -> dict[str, object]:
    return {
        "id": item.id,
        "title": item.title,
        "created_at": item.created_at.isoformat(),
        "updated_at": item.updated_at.isoformat(),
    }


def message_view(item: Message) -> dict[str, object]:
    return {
        "id": item.id,
        "role": item.role,
        "content": item.content,
        "metadata": item.metadata_json,
        "created_at": item.created_at.isoformat(),
    }


def run_view(item: AgentRun) -> dict[str, object]:
    error = None
    if item.error_code:
        error = {
            "code": item.error_code,
            "message": item.error_message,
            "retryable": is_retryable(item.error_code),
        }
    return {
        "id": item.id,
        "conversation_id": item.conversation_id,
        "status": item.status.value,
        "final_message_id": item.final_message_id,
        "error": error,
        "interruption_reason": item.interruption_reason,
        "created_at": item.created_at.isoformat(),
        "updated_at": item.updated_at.isoformat(),
    }


async def owned_conversation(db: Db, conversation_id: str, user: User) -> Conversation:
    conversation = await db.scalar(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.user_id == user.id,
            Conversation.deleted_at.is_(None),
        )
    )
    if not conversation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="CONVERSATION_NOT_FOUND")
    return conversation


@router.post("/auth/login")
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: Db,
    settings: SettingsDep,
) -> dict[str, object]:
    user = await db.scalar(select(User).where(User.username == payload.username))
    if not user or not user.is_active or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="INVALID_CREDENTIALS")
    session_token = opaque_token()
    csrf_token = opaque_token()
    record = Session(
        user_id=user.id,
        token_hash=token_hash(session_token),
        csrf_hash=token_hash(csrf_token),
        expires_at=datetime.now(timezone.utc) + timedelta(hours=settings.session_ttl_hours),
    )
    db.add(record)
    await db.commit()
    response.set_cookie(
        settings.session_cookie_name,
        session_token,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite=settings.session_cookie_samesite,
        max_age=settings.session_ttl_hours * 3600,
    )
    return envelope(request, {"user": user_view(user), "csrf_token": csrf_token})


@router.get("/auth/me")
async def me(request: Request, user: CurrentUser) -> dict[str, object]:
    return envelope(request, user_view(user))


@router.post("/auth/logout")
async def logout(
    request: Request,
    response: Response,
    db: Db,
    settings: SettingsDep,
    session: Annotated[Session, Depends(current_session)],
    _: CsrfProtected,
) -> dict[str, object]:
    await db.delete(session)
    await db.commit()
    response.delete_cookie(
        settings.session_cookie_name,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite=settings.session_cookie_samesite,
    )
    return envelope(request, {"logged_out": True})


@router.get("/conversations")
async def list_conversations(
    request: Request,
    db: Db,
    user: CurrentUser,
    page: int = 1,
    page_size: int = 20,
) -> dict[str, object]:
    page = max(page, 1)
    page_size = min(max(page_size, 1), 100)
    criteria = (
        Conversation.user_id == user.id,
        Conversation.deleted_at.is_(None),
    )
    total = await db.scalar(select(func.count()).select_from(Conversation).where(*criteria))
    items = list(
        (
            await db.scalars(
                select(Conversation)
                .where(*criteria)
                .order_by(Conversation.updated_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).all()
    )
    return envelope(
        request,
        {
            "items": [conversation_view(item) for item in items],
            "page": page,
            "page_size": page_size,
            "total": total or 0,
        },
    )


@router.get("/agent-tools")
async def list_agent_tools(
    request: Request,
    db: Db,
    _: CurrentUser,
) -> dict[str, object]:
    servers = list(
        (
            await db.scalars(
                select(MCPServer).where(
                    MCPServer.enabled.is_(True),
                    MCPServer.connection_status == "connected",
                    MCPServer.deleted_at.is_(None),
                )
            )
        ).all()
    )
    items = []
    for server in servers:
        count = await db.scalar(
            select(func.count())
            .select_from(MCPTool)
            .where(
                MCPTool.server_id == server.id,
                MCPTool.enabled.is_(True),
                MCPTool.risk_policy.in_([ToolRiskPolicy.READ_ONLY, ToolRiskPolicy.PROPOSAL_ONLY]),
            )
        )
        if count:
            items.append(
                {
                    "id": server.id,
                    "server_key": server.server_key,
                    "name": server.name,
                    "tool_count": count,
                }
            )
    return envelope(request, {"items": items})


@router.post("/conversations", status_code=status.HTTP_201_CREATED)
async def create_conversation(
    payload: ConversationCreate,
    request: Request,
    db: Db,
    user: CurrentUser,
    _: CsrfProtected,
) -> dict[str, object]:
    conversation = Conversation(user_id=user.id, title=payload.title)
    db.add(conversation)
    await db.commit()
    await db.refresh(conversation)
    return envelope(request, conversation_view(conversation))


@router.patch("/conversations/{conversation_id}")
async def update_conversation(
    conversation_id: str,
    payload: ConversationUpdate,
    request: Request,
    db: Db,
    user: CurrentUser,
    _: CsrfProtected,
) -> dict[str, object]:
    conversation = await owned_conversation(db, conversation_id, user)
    title = payload.title.strip()
    if not title:
        raise HTTPException(status_code=422, detail="CONVERSATION_TITLE_REQUIRED")
    conversation.title = title
    conversation.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(conversation)
    return envelope(request, conversation_view(conversation))


@router.delete("/conversations/{conversation_id}")
async def delete_conversation(
    conversation_id: str,
    request: Request,
    db: Db,
    user: CurrentUser,
    _: CsrfProtected,
) -> dict[str, object]:
    conversation = await owned_conversation(db, conversation_id, user)
    conversation.deleted_at = datetime.now(timezone.utc)
    conversation.updated_at = conversation.deleted_at
    await db.commit()
    return envelope(request, {"deleted": True})


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
            {"items": [message_view(item) for item in items], "next_cursor": None, "has_more": False},
        )

    page_size = min(
        max(limit if limit is not None else settings.message_pagination_default_limit, 1),
        settings.message_pagination_max_limit,
    )
    conditions = [Message.conversation_id == conversation_id]
    cursor = decode_cursor(before or None)
    if cursor:
        cursor_time, cursor_id = cursor
        # SQLite DateTime 存储为 naive 字符串；比较前去掉 tzinfo 保证一致
        conditions.append(
            tuple_(Message.created_at, Message.id)
            < tuple_(cursor_time.replace(tzinfo=None), cursor_id)
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
    rows.reverse()  # 页内升序
    has_more = False
    next_cursor = None
    if rows:
        has_more = (
            await db.scalar(
                select(func.count())
                .select_from(Message)
                .where(
                    Message.conversation_id == conversation_id,
                    tuple_(Message.created_at, Message.id)
                    < tuple_(
                        rows[0].created_at.replace(tzinfo=None)
                        if rows[0].created_at.tzinfo
                        else rows[0].created_at,
                        rows[0].id,
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
        metadata_json={
            "tool_mode": payload.tool_mode,
            "mcp_server_ids": payload.mcp_server_ids,
        },
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

    # 202 只表示任务已持久化；notify 是降低延迟的快速通道，周期扫描兜底
    dispatcher = getattr(request.app.state, "run_dispatcher", None)
    if dispatcher is not None:
        dispatcher.notify(run.id)
    else:
        background_tasks.add_task(process_agent_run, run.id)
    return envelope(request, {"run_id": run.id, "idempotent_replay": False})


@router.post("/agent-runs/{run_id}/retry", status_code=status.HTTP_202_ACCEPTED)
async def retry_run(
    run_id: str,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Db,
    user: CurrentUser,
    _: CsrfProtected,
) -> dict[str, object]:
    """重试可中断的失败任务：创建新 user message + 新 run；旧 run 保持不可变。"""
    original = await db.scalar(
        select(AgentRun).where(AgentRun.id == run_id, AgentRun.user_id == user.id)
    )
    if not original:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="RUN_NOT_FOUND")
    if original.status != RunStatus.FAILED:
        raise HTTPException(status_code=422, detail="RUN_NOT_RETRYABLE")
    if not is_retryable(original.error_code):
        raise HTTPException(status_code=422, detail="RUN_NOT_RETRYABLE")
    source_message = await db.get(Message, original.user_message_id)
    if not source_message:
        raise HTTPException(status_code=422, detail="RUN_NOT_RETRYABLE")

    now = datetime.now(timezone.utc)
    message = Message(
        conversation_id=original.conversation_id,
        role="user",
        content=source_message.content,
        client_message_id=None,
        metadata_json={
            **source_message.metadata_json,
            "retried_run_id": original.id,
        },
    )
    db.add(message)
    await db.flush()
    retried = AgentRun(
        user_id=user.id,
        conversation_id=original.conversation_id,
        user_message_id=message.id,
        status=RunStatus.QUEUED,
        queued_at=now,
    )
    db.add(retried)
    conversation = await db.get(Conversation, original.conversation_id)
    if conversation:
        conversation.updated_at = now
    await db.commit()

    dispatcher = getattr(request.app.state, "run_dispatcher", None)
    if dispatcher is not None:
        dispatcher.notify(retried.id)
    else:
        background_tasks.add_task(process_agent_run, retried.id)
    return envelope(request, {"run_id": retried.id, "message_id": message.id})


@router.get("/agent-runs")
async def list_agent_runs(
    request: Request,
    db: Db,
    user: CurrentUser,
    page: int = 1,
    page_size: int = 20,
) -> dict[str, object]:
    page = max(page, 1)
    page_size = min(max(page_size, 1), 100)
    total = await db.scalar(
        select(func.count()).select_from(AgentRun).where(AgentRun.user_id == user.id)
    )
    runs = (
        await db.scalars(
            select(AgentRun)
            .where(AgentRun.user_id == user.id)
            .order_by(AgentRun.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()
    return envelope(
        request,
        {
            "items": [run_view(run) for run in runs],
            "page": page,
            "page_size": page_size,
            "total": total or 0,
        },
    )


@router.get("/agent-runs/{run_id}")
async def get_run(run_id: str, request: Request, db: Db, user: CurrentUser) -> dict[str, object]:
    run = await db.scalar(
        select(AgentRun).where(AgentRun.id == run_id, AgentRun.user_id == user.id)
    )
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="RUN_NOT_FOUND")
    return envelope(request, run_view(run))


@router.get("/agent-runs/{run_id}/events")
async def stream_run_events(
    run_id: str,
    request: Request,
    db: Db,
    user: CurrentUser,
) -> StreamingResponse:
    run = await db.scalar(
        select(AgentRun).where(AgentRun.id == run_id, AgentRun.user_id == user.id)
    )
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="RUN_NOT_FOUND")
    header_value = request.headers.get("Last-Event-ID", "0")
    try:
        cursor = max(int(header_value), 0)
    except ValueError:
        cursor = 0

    async def event_source():
        nonlocal cursor
        idle_ticks = 0
        while True:
            async with SessionFactory() as event_db:
                events = list(
                    (
                        await event_db.scalars(
                            select(RunEvent)
                            .where(RunEvent.run_id == run_id, RunEvent.id > cursor)
                            .order_by(RunEvent.id)
                        )
                    ).all()
                )
                current_run = await event_db.get(AgentRun, run_id)
            if events:
                idle_ticks = 0
                for event in events:
                    cursor = event.id
                    payload = {
                        "id": event.id,
                        "run_id": run_id,
                        "timestamp": event.created_at.isoformat(),
                        "data": event.data,
                    }
                    yield f"id: {event.id}\nevent: {event.event_type}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
            else:
                idle_ticks += 1
                if idle_ticks >= 40:
                    idle_ticks = 0
                    yield ": keep-alive\n\n"
            if (
                current_run
                and current_run.status in {RunStatus.COMPLETED, RunStatus.FAILED}
                and not events
            ):
                break
            if await request.is_disconnected():
                break
            await asyncio.sleep(0.25)

    return StreamingResponse(
        event_source(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
