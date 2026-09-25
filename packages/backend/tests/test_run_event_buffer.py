"""RunEventBuffer 测试（specs WP-11 / §9.4、§15.4、§15.6、§20）。"""

import asyncio
import hashlib
import json
import uuid

from sqlalchemy import select

from app.agent.runtime import RuntimeEvent
from app.db import SessionFactory
from app.models import (
    AgentRun,
    Conversation,
    Message,
    RunEvent,
    RunStatus,
    User,
    UserRole,
)
from app.services.run_event_buffer import RunEventBuffer, summarize_tool_output


async def _seed_run() -> str:
    async with SessionFactory() as db:
        user = User(username=f"buf-{uuid.uuid4().hex[:10]}", password_hash="x", role=UserRole.ADMIN)
        db.add(user)
        await db.flush()
        conversation = Conversation(user_id=user.id, title="缓冲测试")
        db.add(conversation)
        await db.flush()
        message = Message(conversation_id=conversation.id, role="user", content="hi")
        db.add(message)
        await db.flush()
        run = AgentRun(
            user_id=user.id,
            conversation_id=conversation.id,
            user_message_id=message.id,
            status=RunStatus.RUNNING,
        )
        db.add(run)
        await db.commit()
        return run.id


async def _event_rows(run_id: str) -> list[RunEvent]:
    async with SessionFactory() as db:
        return list(
            (
                await db.scalars(
                    select(RunEvent).where(RunEvent.run_id == run_id).order_by(RunEvent.id)
                )
            ).all()
        )


def test_small_deltas_merge_into_single_batch_transaction(monkeypatch) -> None:
    """2,000 个小 delta → 合并后一批写完，事务数远低于 delta 数（≤100）。"""
    run_id = asyncio.run(_seed_run())
    buffer = RunEventBuffer(run_id, max_delta_chars=256, flush_after_seconds=0.2)
    write_calls: list[int] = []
    original = RunEventBuffer._write_batch

    async def counting(self, rows):
        write_calls.append(len(rows))
        return await original(self, rows)

    monkeypatch.setattr(RunEventBuffer, "_write_batch", counting)
    for _ in range(2000):
        buffer.append(RuntimeEvent("answer.delta", {"delta": "x" * 10}))
    written = asyncio.run(buffer.flush())

    assert write_calls == [written]  # 单次事务
    assert write_calls[0] <= 100
    rows = asyncio.run(_event_rows(run_id))
    total = sum(len(row.data.get("delta", "")) for row in rows)
    assert total == 20_000  # 内容无损


def test_semantic_events_flush_pending_delta_and_keep_order() -> None:
    run_id = asyncio.run(_seed_run())
    buffer = RunEventBuffer(run_id, max_delta_chars=256, flush_after_seconds=0.2)
    buffer.append(RuntimeEvent("answer.delta", {"delta": "a"}))
    buffer.append(RuntimeEvent("tool.started", {"tool_name": "t1"}))
    buffer.append(RuntimeEvent("answer.delta", {"delta": "b"}))
    buffer.append(RuntimeEvent("tool.finished", {"tool_name": "t1", "output": {"ok": True}}))
    asyncio.run(buffer.flush())

    rows = asyncio.run(_event_rows(run_id))
    assert [(row.event_type, row.data.get("delta", row.data.get("tool_name"))) for row in rows] == [
        ("answer.delta", "a"),
        ("tool.started", "t1"),
        ("answer.delta", "b"),
        ("tool.finished", "t1"),
    ]


def test_time_window_flush_writes_pending_delta() -> None:
    run_id = asyncio.run(_seed_run())
    buffer = RunEventBuffer(run_id, max_delta_chars=1000, flush_after_seconds=0.0)
    buffer.append(RuntimeEvent("answer.delta", {"delta": "a"}))
    written = asyncio.run(buffer.flush_due())

    assert written == 1  # 时间窗到期立即落盘，不等终态
    rows = asyncio.run(_event_rows(run_id))
    assert [row.event_type for row in rows] == ["answer.delta"]


def test_oversized_tool_output_is_summarized_with_stable_hash() -> None:
    run_id = asyncio.run(_seed_run())
    buffer = RunEventBuffer(run_id, max_delta_chars=256, tool_output_max_bytes=1024)
    big_output = {"rows": ["r" * 64] * 64}  # 序列化后 > 1 KiB
    raw = json.dumps(big_output, ensure_ascii=False).encode("utf-8")
    buffer.append(RuntimeEvent("tool.finished", {"tool_name": "t1", "output": big_output}))
    buffer.append(RuntimeEvent("tool.finished", {"tool_name": "t2", "output": {"ok": True}}))
    asyncio.run(buffer.flush())

    rows = asyncio.run(_event_rows(run_id))
    summarized = rows[0].data["output"]
    assert summarized["truncated"] is True
    assert summarized["original_bytes"] == len(raw)
    assert summarized["sha256"] == hashlib.sha256(raw).hexdigest()
    assert rows[1].data["output"] == {"ok": True}  # 小输出原样保留


def test_summarize_tool_output_is_deterministic() -> None:
    payload = {"k": "v" * 5000}
    first = summarize_tool_output(payload, max_bytes=1024)
    second = summarize_tool_output(payload, max_bytes=1024)
    assert first == second
    assert first["sha256"] == second["sha256"]


def test_flush_without_events_is_noop() -> None:
    run_id = asyncio.run(_seed_run())
    buffer = RunEventBuffer(run_id)
    assert asyncio.run(buffer.flush()) == 0
    assert asyncio.run(_event_rows(run_id)) == []
