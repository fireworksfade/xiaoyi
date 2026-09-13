"""RunDispatcher 测试：认领、周期扫描兜底、优雅停止、取消收敛、重试 API。"""

import asyncio
import time
import uuid

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import SessionFactory
from app.main import app
from app.models import AgentRun, Conversation, Message, RunEvent, RunStatus, User, utc_now
from app.services.run_dispatcher import RunDispatcher
from app.services.run_state import claim_queued_run


async def _make_queued_run() -> AgentRun:
    async with SessionFactory() as db:
        conversation = Conversation(user_id="u1", title="调度测试")
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
            status=RunStatus.QUEUED,
            queued_at=utc_now(),
        )
        db.add(run)
        await db.commit()
        await db.refresh(run)
        return run


async def _get_run(run_id: str) -> AgentRun | None:
    async with SessionFactory() as db:
        return await db.get(AgentRun, run_id)


async def test_claim_is_single_use() -> None:
    run = await _make_queued_run()
    assert await claim_queued_run(run.id)
    refreshed = await _get_run(run.id)
    assert refreshed.status == RunStatus.RUNNING
    assert refreshed.started_at is not None
    assert refreshed.attempt_count == 1
    assert not await claim_queued_run(run.id)
    refreshed = await _get_run(run.id)
    assert refreshed.attempt_count == 1


async def test_poll_picks_up_run_without_notify() -> None:
    """notify 丢失时，周期扫描仍会执行任务。"""
    processed: list[str] = []

    async def fake_process(run_id: str) -> None:
        processed.append(run_id)

    dispatcher = RunDispatcher(fake_process, poll_interval_seconds=0.05)
    dispatcher.start()
    try:
        run = await _make_queued_run()
        for _ in range(50):
            if processed:
                break
            await asyncio.sleep(0.05)
        assert processed == [run.id]
    finally:
        await dispatcher.stop()


async def test_notify_executes_immediately() -> None:
    processed: list[str] = []

    async def fake_process(run_id: str) -> None:
        processed.append(run_id)

    dispatcher = RunDispatcher(fake_process, poll_interval_seconds=5)
    dispatcher.start()
    try:
        run = await _make_queued_run()
        dispatcher.notify(run.id)
        for _ in range(50):
            if processed:
                break
            await asyncio.sleep(0.05)
        assert processed == [run.id]
    finally:
        await dispatcher.stop()


async def test_execute_writes_terminal_state_on_exception() -> None:
    async def failing_process(run_id: str) -> None:
        raise ValueError("boom")

    dispatcher = RunDispatcher(failing_process, poll_interval_seconds=0.05)
    dispatcher.start()
    try:
        run = await _make_queued_run()
        for _ in range(50):
            refreshed = await _get_run(run.id)
            if refreshed.status == RunStatus.FAILED:
                break
            await asyncio.sleep(0.05)
        refreshed = await _get_run(run.id)
        assert refreshed.status == RunStatus.FAILED
        assert refreshed.error_code == "AGENT_RUN_FAILED"
        assert "ValueError: boom" in refreshed.error_message
        assert refreshed.finished_at is not None
    finally:
        await dispatcher.stop()


async def test_stop_grace_timeout_marks_interrupted() -> None:
    """优雅停止超时：当前任务被取消并收敛为 RUN_INTERRUPTED。"""
    started = asyncio.Event()

    async def slow_process(run_id: str) -> None:
        started.set()
        await asyncio.sleep(60)

    dispatcher = RunDispatcher(slow_process, poll_interval_seconds=0.05, shutdown_grace_seconds=0.2)
    dispatcher.start()
    run = await _make_queued_run()
    dispatcher.notify(run.id)
    await asyncio.wait_for(started.wait(), timeout=2)
    await asyncio.wait_for(dispatcher.stop(), timeout=5)
    refreshed = await _get_run(run.id)
    assert refreshed.status == RunStatus.FAILED
    assert refreshed.error_code == "RUN_INTERRUPTED"
    async with SessionFactory() as db:
        events = list((await db.scalars(select(RunEvent).where(RunEvent.run_id == run.id))).all())
    codes = {event.data["error"]["code"] for event in events}
    assert "RUN_INTERRUPTED" in codes


def test_submit_message_runs_via_dispatcher() -> None:
    """API 提交消息后由 Dispatcher 执行到终态（mock runtime）。"""
    with TestClient(app) as client:
        login = client.post(
            "/api/v1/auth/login", json={"username": "admin", "password": "admin123"}
        )
        csrf = login.json()["data"]["csrf_token"]
        conversation = client.post(
            "/api/v1/conversations",
            json={"title": "调度链路"},
            headers={"X-CSRF-Token": csrf},
        ).json()["data"]
        submit = client.post(
            f"/api/v1/conversations/{conversation['id']}/messages",
            json={"content": "你好", "client_message_id": uuid.uuid4().hex},
            headers={"X-CSRF-Token": csrf},
        )
        assert submit.status_code == 202
        run_id = submit.json()["data"]["run_id"]
        final_status = None
        for _ in range(100):
            detail = client.get(f"/api/v1/agent-runs/{run_id}").json()["data"]
            final_status = detail["status"]
            if final_status in {"COMPLETED", "FAILED"}:
                break
            time.sleep(0.1)
        assert final_status == "completed"


def test_retry_creates_new_run_and_keeps_original() -> None:
    """中断的 run 可重试：生成新 run，旧 run 保持 FAILED 不可变。"""
    with TestClient(app) as client:
        login = client.post(
            "/api/v1/auth/login", json={"username": "admin", "password": "admin123"}
        )
        csrf = login.json()["data"]["csrf_token"]
        conversation = client.post(
            "/api/v1/conversations",
            json={"title": "重试链路"},
            headers={"X-CSRF-Token": csrf},
        ).json()["data"]

        # 直接注入一个 RUN_INTERRUPTED 的旧 run
        async def seed_interrupted() -> tuple[str, str]:
            async with SessionFactory() as db:
                admin_id = await db.scalar(select(User.id).where(User.username == "admin"))
                message = Message(
                    conversation_id=conversation["id"],
                    role="user",
                    content="需要重试的内容",
                    client_message_id=f"cmid-{uuid.uuid4().hex[:8]}",
                    metadata_json={"tool_mode": "auto", "mcp_server_ids": []},
                )
                db.add(message)
                await db.flush()
                run = AgentRun(
                    user_id=admin_id,
                    conversation_id=conversation["id"],
                    user_message_id=message.id,
                    status=RunStatus.FAILED,
                    error_code="RUN_INTERRUPTED",
                    error_message="服务重启导致运行中断，可重试",
                    interruption_reason="RUN_INTERRUPTED",
                    queued_at=utc_now(),
                )
                db.add(run)
                await db.commit()
                await db.refresh(run)
                return run.id, message.id

        original_id, original_message_id = asyncio.run(seed_interrupted())

        retry = client.post(
            f"/api/v1/agent-runs/{original_id}/retry",
            headers={"X-CSRF-Token": csrf},
        )
        assert retry.status_code == 202
        retried_id = retry.json()["data"]["run_id"]
        assert retried_id != original_id

        original = client.get(f"/api/v1/agent-runs/{original_id}").json()["data"]
        assert original["status"] == "failed"
        assert original["error"]["retryable"] is True

        # 重试 run 被调度执行到终态（mock runtime）
        for _ in range(100):
            detail = client.get(f"/api/v1/agent-runs/{retried_id}").json()["data"]
            if detail["status"] in {"COMPLETED", "FAILED"}:
                break
            time.sleep(0.1)
        detail = client.get(f"/api/v1/agent-runs/{retried_id}").json()["data"]
        assert detail["status"] == "completed"


def test_retry_rejects_non_retryable() -> None:
    with TestClient(app) as client:
        login = client.post(
            "/api/v1/auth/login", json={"username": "admin", "password": "admin123"}
        )
        csrf = login.json()["data"]["csrf_token"]

        async def seed_failed() -> str:
            async with SessionFactory() as db:
                admin_id = await db.scalar(select(User.id).where(User.username == "admin"))
                conversation = Conversation(user_id=admin_id, title="不可重试")
                db.add(conversation)
                await db.flush()
                message = Message(
                    conversation_id=conversation.id,
                    role="user",
                    content="x",
                    client_message_id=f"cmid-{uuid.uuid4().hex[:8]}",
                    metadata_json={},
                )
                db.add(message)
                await db.flush()
                run = AgentRun(
                    user_id=admin_id,
                    conversation_id=conversation.id,
                    user_message_id=message.id,
                    status=RunStatus.FAILED,
                    error_code="AGENT_RUN_FAILED",
                    error_message="普通失败",
                    queued_at=utc_now(),
                )
                db.add(run)
                await db.commit()
                await db.refresh(run)
                return run.id

        run_id = asyncio.run(seed_failed())
        response = client.post(f"/api/v1/agent-runs/{run_id}/retry", headers={"X-CSRF-Token": csrf})
        assert response.status_code == 422
