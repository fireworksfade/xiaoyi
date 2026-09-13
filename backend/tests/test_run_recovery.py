"""启动恢复扫描测试。"""

import uuid

from sqlalchemy import select

from app.db import SessionFactory
from app.models import AgentRun, Conversation, Message, RunEvent, RunStatus, utc_now
from app.services.run_recovery import recover_interrupted_runs
from app.services.run_state import claim_queued_run


async def _make_run(status: RunStatus, *, with_terminal_event: bool = False) -> AgentRun:
    async with SessionFactory() as db:
        conversation = Conversation(user_id="u1", title="恢复测试")
        db.add(conversation)
        await db.flush()
        message = Message(
            conversation_id=conversation.id,
            role="user",
            content="测试输入",
            client_message_id=f"cmid-{uuid.uuid4().hex[:8]}",
            metadata_json={},
        )
        db.add(message)
        await db.flush()
        run = AgentRun(
            user_id="u1",
            conversation_id=conversation.id,
            user_message_id=message.id,
            status=status,
            queued_at=utc_now(),
            started_at=utc_now() if status == RunStatus.RUNNING else None,
        )
        db.add(run)
        await db.flush()
        if with_terminal_event:
            db.add(
                RunEvent(
                    run_id=run.id,
                    event_type="run.completed",
                    data={"message_id": "m-fake"},
                )
            )
        await db.commit()
        await db.refresh(run)
        return run


async def _events_of(run_id: str) -> list[RunEvent]:
    async with SessionFactory() as db:
        return list((await db.scalars(select(RunEvent).where(RunEvent.run_id == run_id))).all())


async def test_running_run_becomes_failed_run_interrupted() -> None:
    run = await _make_run(RunStatus.RUNNING)
    report = await recover_interrupted_runs()
    assert report.interrupted == 1

    async with SessionFactory() as db:
        refreshed = await db.get(AgentRun, run.id)
    assert refreshed.status == RunStatus.FAILED
    assert refreshed.error_code == "RUN_INTERRUPTED"
    assert refreshed.interruption_reason == "RUN_INTERRUPTED"
    assert refreshed.finished_at is not None
    events = await _events_of(run.id)
    assert len(events) == 1
    assert events[0].event_type == "run.failed"
    assert events[0].data["error"]["code"] == "RUN_INTERRUPTED"
    assert events[0].data["error"]["retryable"] is True


async def test_queued_run_is_preserved_for_redispatch() -> None:
    run = await _make_run(RunStatus.QUEUED)
    report = await recover_interrupted_runs()
    assert report.requeued == 1
    assert report.interrupted == 0
    async with SessionFactory() as db:
        refreshed = await db.get(AgentRun, run.id)
    assert refreshed.status == RunStatus.QUEUED


async def test_terminal_runs_untouched() -> None:
    # 共享测试库中可能存在其他用例遗留的 QUEUED/RUNNING，因此只断言本 run 不受影响
    run = await _make_run(RunStatus.COMPLETED, with_terminal_event=True)
    await recover_interrupted_runs()
    async with SessionFactory() as db:
        refreshed = await db.get(AgentRun, run.id)
    assert refreshed.status == RunStatus.COMPLETED
    assert refreshed.finished_at is None  # 未被恢复扫描改写
    assert refreshed.error_code is None


async def test_terminal_run_missing_event_repaired() -> None:
    run = await _make_run(RunStatus.FAILED)
    report = await recover_interrupted_runs()
    assert report.repaired == 1
    events = await _events_of(run.id)
    assert len(events) == 1
    assert events[0].event_type == "run.failed"
    assert events[0].data.get("repaired_at") is not None


async def test_recovery_then_claim_is_executable() -> None:
    """恢复后 QUEUED 任务可被 Dispatcher 认领，且二次认领失败。"""
    run = await _make_run(RunStatus.QUEUED)
    await recover_interrupted_runs()
    assert await claim_queued_run(run.id)
    assert not await claim_queued_run(run.id)
