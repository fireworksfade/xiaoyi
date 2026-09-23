import asyncio
import json
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select

from app.api.common import envelope, run_view
from app.api.deps import CsrfProtected, CurrentUser, Db
from app.db import SessionFactory
from app.models import (
    AgentRun,
    Conversation,
    Message,
    OperationWorkflowStep,
    RunEvent,
    RunStatus,
)
from app.observability.metrics import SSE_CONNECTIONS
from app.services.run_state import is_retryable
from app.services.runs import process_agent_run
from app.services.workflows import get_workflow_for_run, sync_workflow_from_control, workflow_view

router = APIRouter(prefix="/agent-runs", tags=["agent-runs"])


@router.post("/{run_id}/retry", status_code=status.HTTP_202_ACCEPTED)
async def retry_run(
    run_id: str,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Db,
    user: CurrentUser,
    _: CsrfProtected,
) -> dict[str, object]:
    original = await db.scalar(
        select(AgentRun).where(AgentRun.id == run_id, AgentRun.user_id == user.id)
    )
    if not original:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="RUN_NOT_FOUND")
    if original.status != RunStatus.FAILED or not is_retryable(original.error_code):
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
        metadata_json={**source_message.metadata_json, "retried_run_id": original.id},
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


@router.get("")
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


@router.get("/{run_id}")
async def get_run(run_id: str, request: Request, db: Db, user: CurrentUser) -> dict[str, object]:
    run = await db.scalar(
        select(AgentRun).where(AgentRun.id == run_id, AgentRun.user_id == user.id)
    )
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="RUN_NOT_FOUND")
    return envelope(request, run_view(run))


@router.get("/{run_id}/workflow")
async def get_run_workflow(
    run_id: str, request: Request, db: Db, user: CurrentUser
) -> dict[str, object]:
    run = await db.scalar(
        select(AgentRun).where(AgentRun.id == run_id, AgentRun.user_id == user.id)
    )
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="RUN_NOT_FOUND")
    workflow, steps = await get_workflow_for_run(db, run_id)
    if workflow is not None:
        await sync_workflow_from_control(db, workflow)
        steps = list(
            (
                await db.scalars(
                    select(OperationWorkflowStep)
                    .where(OperationWorkflowStep.workflow_id == workflow.id)
                    .order_by(OperationWorkflowStep.sequence)
                )
            ).all()
        )
    return envelope(request, workflow_view(workflow, steps) if workflow else None)


@router.get("/{run_id}/events")
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
    try:
        cursor = max(int(request.headers.get("Last-Event-ID", "0")), 0)
    except ValueError:
        cursor = 0

    async def stream_events(event_cursor: int):
        idle_ticks = 0
        while True:
            async with SessionFactory() as event_db:
                events = list(
                    (
                        await event_db.scalars(
                            select(RunEvent)
                            .where(RunEvent.run_id == run_id, RunEvent.id > event_cursor)
                            .order_by(RunEvent.id)
                        )
                    ).all()
                )
                current_run = await event_db.get(AgentRun, run_id)
            if events:
                idle_ticks = 0
                for event in events:
                    event_cursor = event.id
                    payload = {
                        "id": event.id,
                        "run_id": run_id,
                        "timestamp": event.created_at.isoformat(),
                        "data": event.data,
                    }
                    yield (
                        f"id: {event.id}\nevent: {event.event_type}\n"
                        f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
                    )
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

    async def event_source():
        SSE_CONNECTIONS.inc()
        try:
            async for chunk in stream_events(cursor):
                yield chunk
        finally:
            SSE_CONNECTIONS.dec()

    return StreamingResponse(
        event_source(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
