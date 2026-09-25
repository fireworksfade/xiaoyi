"""数据保留策略测试（specs WP-11 / §9.3、§15.2、§15.3、§15.5、§15.6）。"""

import asyncio
import uuid
from datetime import timedelta
from types import SimpleNamespace

from sqlalchemy import func, select

from app.db import SessionFactory
from app.models import (
    AgentRun,
    Attachment,
    Conversation,
    Message,
    RunEvent,
    RunStatus,
    Session,
    User,
    UserRole,
    utc_now,
)
from app.services.retention import run_retention


def _settings(**overrides):
    from app.config import Settings

    base = Settings(_env_file=None)
    values = {
        "retention_batch_size": base.retention_batch_size,
        "unbound_attachment_retention_hours": base.unbound_attachment_retention_hours,
        "expired_session_grace_days": base.expired_session_grace_days,
        "run_events_compact_after_hours": base.run_events_compact_after_hours,
        "run_events_failed_retention_hours": base.run_events_failed_retention_hours,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


async def _seed_user() -> User:
    async with SessionFactory() as db:
        user = User(username=f"ret-{uuid.uuid4().hex[:10]}", password_hash="x", role=UserRole.ADMIN)
        db.add(user)
        await db.commit()
        await db.refresh(user)
        return user


def _run_retention(delete_enabled: bool, **overrides):
    return asyncio.run(
        run_retention(delete_enabled=delete_enabled, settings=_settings(**overrides))
    )


def test_dry_run_reports_candidates_without_deleting() -> None:
    user_id = asyncio.run(_seed_user()).id
    cutoff_hours = _settings().unbound_attachment_retention_hours

    async def seed():
        async with SessionFactory() as db:
            db.add(
                Attachment(
                    user_id=user_id,
                    filename="old.txt",
                    media_type="text/plain",
                    size_bytes=10,
                    extracted_text="旧附件",
                    created_at=utc_now() - timedelta(hours=cutoff_hours + 5),
                )
            )
            db.add(
                Attachment(
                    user_id=user_id,
                    filename="fresh.txt",
                    media_type="text/plain",
                    size_bytes=5,
                    extracted_text="新附件",
                )
            )
            await db.commit()

    asyncio.run(seed())
    report = _run_retention(delete_enabled=False)

    assert report["attachments"]["scanned"] >= 1
    assert report["attachments"]["deleted"] == 0
    assert report["attachments"]["dry_run"] is True

    async def remaining():
        async with SessionFactory() as db:
            return await db.scalar(
                select(func.count()).select_from(Attachment).where(Attachment.user_id == user_id)
            )

    assert asyncio.run(remaining()) == 2  # dry-run 不修改任何行


def test_execute_deletes_only_unbound_attachments_past_retention() -> None:
    user_id = asyncio.run(_seed_user()).id
    cutoff_hours = _settings().unbound_attachment_retention_hours

    async def seed():
        async with SessionFactory() as db:
            conversation = Conversation(user_id=user_id, title="绑定")
            db.add(conversation)
            await db.flush()
            message = Message(conversation_id=conversation.id, role="user", content="m")
            db.add(message)
            await db.flush()
            db.add(
                Attachment(
                    user_id=user_id,
                    filename="old-unbound.txt",
                    media_type="text/plain",
                    size_bytes=1,
                    extracted_text="a",
                    created_at=utc_now() - timedelta(hours=cutoff_hours + 1),
                )
            )
            db.add(
                Attachment(
                    user_id=user_id,
                    filename="bound-old.txt",
                    media_type="text/plain",
                    size_bytes=1,
                    extracted_text="b",
                    message_id=message.id,
                    created_at=utc_now() - timedelta(hours=cutoff_hours + 1),
                )
            )
            await db.commit()

    asyncio.run(seed())
    report = _run_retention(delete_enabled=True)

    # 共享测试库中此前 dry-run 测试遗留的旧未绑定附件也会一并回收
    assert report["attachments"]["deleted"] >= 1  # 已绑定附件不回收

    async def names():
        async with SessionFactory() as db:
            return set(
                (
                    await db.scalars(
                        select(Attachment.filename).where(Attachment.user_id == user_id)
                    )
                ).all()
            )

    remaining = asyncio.run(names())
    assert "bound-old.txt" in remaining  # 已绑定附件保留
    assert "old-unbound.txt" not in remaining  # 超期未绑定附件被删除


def test_expired_sessions_removed_only_after_grace() -> None:
    user_id = asyncio.run(_seed_user()).id
    grace_days = _settings().expired_session_grace_days

    async def seed():
        async with SessionFactory() as db:
            db.add(
                Session(
                    user_id=user_id,
                    token_hash=f"old-{uuid.uuid4().hex}",
                    csrf_hash=f"old-{uuid.uuid4().hex}",
                    expires_at=utc_now() - timedelta(days=grace_days + 1),
                )
            )
            db.add(
                Session(
                    user_id=user_id,
                    token_hash=f"recent-{uuid.uuid4().hex}",
                    csrf_hash=f"recent-{uuid.uuid4().hex}",
                    expires_at=utc_now() - timedelta(days=1),
                )
            )
            await db.commit()

    asyncio.run(seed())
    report = _run_retention(delete_enabled=True)

    assert report["sessions"]["deleted"] == 1

    async def token_hashes():
        async with SessionFactory() as db:
            return set((await db.scalars(select(Session.token_hash))).all())

    hashes = asyncio.run(token_hashes())
    assert not any(h.startswith("old-") for h in hashes)  # 超期 Session 已删除
    assert any(h.startswith("recent-") for h in hashes)  # 宽限期内保留


def _seed_run_with_events() -> str:
    """已完成 run：assistant 消息已持久化 + 旧 delta 与工具事件。"""

    async def seed():
        async with SessionFactory() as db:
            user = User(
                username=f"comp-{uuid.uuid4().hex[:10]}", password_hash="x", role=UserRole.ADMIN
            )
            db.add(user)
            await db.flush()
            conversation = Conversation(user_id=user.id, title="压缩")
            db.add(conversation)
            await db.flush()
            user_message = Message(conversation_id=conversation.id, role="user", content="q")
            db.add(user_message)
            await db.flush()
            final_message = Message(conversation_id=conversation.id, role="assistant", content="a")
            db.add(final_message)
            await db.flush()
            finished = utc_now() - timedelta(hours=25)
            run = AgentRun(
                user_id=user.id,
                conversation_id=conversation.id,
                user_message_id=user_message.id,
                final_message_id=final_message.id,
                status=RunStatus.COMPLETED,
                finished_at=finished,
            )
            db.add(run)
            await db.flush()
            for _ in range(3):
                db.add(RunEvent(run_id=run.id, event_type="answer.delta", data={"delta": "x"}))
            db.add(
                RunEvent(run_id=run.id, event_type="run.started", data={}),
            )
            db.add(
                RunEvent(
                    run_id=run.id,
                    event_type="run.completed",
                    data={"message_id": final_message.id},
                )
            )
            await db.commit()
            return run.id

    return asyncio.run(seed())


def test_completed_run_deltas_compacted_after_window() -> None:
    run_id = _seed_run_with_events()
    report = _run_retention(delete_enabled=True)

    assert report["run_events"]["deleted"] >= 3
    assert report["run_events"]["compacted_runs"] >= 1

    async def verify():
        async with SessionFactory() as db:
            run = await db.get(AgentRun, run_id)
            events = list(
                (
                    await db.scalars(select(RunEvent.event_type).where(RunEvent.run_id == run_id))
                ).all()
            )
            return run, events

    run, event_types = asyncio.run(verify())
    assert "answer.delta" not in event_types
    assert set(event_types) == {"run.started", "run.completed"}  # 终态与起点事件保留
    assert run.runtime_state.get("events_compacted_at") is not None


def test_recent_completed_run_deltas_are_kept() -> None:
    _seed_run_with_events()
    # completed_after_hours 调大，使 25h 前完成的 run 仍处于保留窗口内
    report = _run_retention(delete_enabled=True, run_events_compact_after_hours=48)

    assert report["run_events"]["deleted"] == 0
    assert report["run_events"]["candidate_runs"] == 0


def test_failed_run_deltas_kept_within_diagnostic_period() -> None:
    async def seed():
        async with SessionFactory() as db:
            user = User(
                username=f"fail-{uuid.uuid4().hex[:10]}", password_hash="x", role=UserRole.ADMIN
            )
            db.add(user)
            await db.flush()
            conversation = Conversation(user_id=user.id, title="失败")
            db.add(conversation)
            await db.flush()
            message = Message(conversation_id=conversation.id, role="user", content="q")
            db.add(message)
            await db.flush()
            run = AgentRun(
                user_id=user.id,
                conversation_id=conversation.id,
                user_message_id=message.id,
                status=RunStatus.FAILED,
                finished_at=utc_now() - timedelta(hours=48),
            )
            db.add(run)
            await db.flush()
            db.add(RunEvent(run_id=run.id, event_type="answer.delta", data={"delta": "partial"}))
            await db.commit()
            return run.id

    run_id = asyncio.run(seed())
    # 失败 run 的 delta 在 7 天诊断期内保留（48h < 168h）
    report = _run_retention(delete_enabled=True)

    assert report["run_events"]["deleted"] == 0

    async def count():
        async with SessionFactory() as db:
            return await db.scalar(
                select(func.count()).select_from(RunEvent).where(RunEvent.run_id == run_id)
            )

    assert asyncio.run(count()) == 1


def test_failed_run_deltas_removed_after_diagnostic_period() -> None:
    async def seed():
        async with SessionFactory() as db:
            user = User(
                username=f"fail2-{uuid.uuid4().hex[:10]}", password_hash="x", role=UserRole.ADMIN
            )
            db.add(user)
            await db.flush()
            conversation = Conversation(user_id=user.id, title="失败超期")
            db.add(conversation)
            await db.flush()
            message = Message(conversation_id=conversation.id, role="user", content="q")
            db.add(message)
            await db.flush()
            run = AgentRun(
                user_id=user.id,
                conversation_id=conversation.id,
                user_message_id=message.id,
                status=RunStatus.FAILED,
                finished_at=utc_now() - timedelta(hours=200),
            )
            db.add(run)
            await db.flush()
            db.add(RunEvent(run_id=run.id, event_type="answer.delta", data={"delta": "old"}))
            await db.commit()
            return run.id

    asyncio.run(seed())
    report = _run_retention(delete_enabled=True)

    assert report["run_events"]["deleted"] >= 1


def test_batched_deletion_removes_all_candidates() -> None:
    user_id = asyncio.run(_seed_user()).id
    cutoff_hours = _settings().unbound_attachment_retention_hours

    async def seed():
        async with SessionFactory() as db:
            for i in range(5):
                db.add(
                    Attachment(
                        user_id=user_id,
                        filename=f"batch-{i}.txt",
                        media_type="text/plain",
                        size_bytes=1,
                        extracted_text=f"t{i}",
                        created_at=utc_now() - timedelta(hours=cutoff_hours + 1),
                    )
                )
            await db.commit()

    asyncio.run(seed())
    report = _run_retention(delete_enabled=True, retention_batch_size=2)

    assert report["attachments"]["scanned"] == 5
    assert report["attachments"]["deleted"] == 5  # 分批（3 批）后全部收敛
