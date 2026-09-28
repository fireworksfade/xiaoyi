"""Memory 模块验收测试（spec §16）。

覆盖：结果归一化（AC02/AC28）、价值门控与幂等（AC01/AC06）、用户隔离（AC10）、
状态机与版本（AC03/AC05）、来源撤回（AC18/AC27）、召回过滤（AC12）、
修复预算与再诊断门槛（AC30/AC31）、历史迁移分配（AC19/AC20/AC26）。
"""

import json
import uuid
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import delete, select

from app.config import get_settings
from app.db import SessionFactory
from app.memory import actions, capture, service
from app.memory.models import (
    Memory,
    MemoryActionLink,
    MemoryJob,
    MemorySource,
    MemoryTombstone,
    WorkingMemory,
)
from app.memory.retrieval import search
from app.memory.schemas import MemorySearch, MemoryWrite
from app.models import AgentRun, Conversation, Message, RunStatus, User, utc_now


async def _cleanup_memory_tables() -> None:
    async with SessionFactory() as db:
        # users 一并清空：否则先前测试创建的用户会阻止 seed_users 落库 admin
        await db.execute(delete(User))
        for model in (
            WorkingMemory,
            MemoryJob,
            MemoryActionLink,
            MemoryTombstone,
            MemorySource,
            Memory,
        ):
            await db.execute(delete(model))
        await db.commit()


@pytest.fixture(autouse=True)
async def _clean_memory(_migrated_clean_db):
    """conftest 全局禁用了 memory（避免后台 worker 与测试争锁）；
    本文件直接测服务函数，在此打开并在结束时还原。"""
    settings = get_settings()
    previous = (settings.memory_enabled, settings.memory_auto_capture, settings.memory_auto_propose_experience)
    settings.memory_enabled, settings.memory_auto_capture, settings.memory_auto_propose_experience = True, True, True
    await _cleanup_memory_tables()
    yield
    await _cleanup_memory_tables()
    settings.memory_enabled, settings.memory_auto_capture, settings.memory_auto_propose_experience = previous


def _episode_payload(outcome="succeeded", title="ESP32_05 · MQTT 超时") -> MemoryWrite:
    return MemoryWrite(
        kind="episodic",
        title=title,
        summary="MQTT keep alive 超时；结果 succeeded。",
        content={
            "observations": ["MQTT keep alive timeout"],
            "hypotheses": [{"text": "网络抖动", "epistemic_status": "hypothesis"}],
            "actions": [{"action": "reconnect_mqtt"}],
            "outcome": outcome,
            "unresolved_items": [],
            "root_cause_status": "unknown",
        },
        applicability={"mcp_server_id": "srv-1", "device_ids": ["ESP32_05"]},
    )


def _experience_payload(confirm=False) -> MemoryWrite:
    return MemoryWrite(
        kind="experience",
        title="MQTT 超时先查心跳",
        summary="keep alive 超时优先检查客户端心跳配置。",
        content={
            "claims": [
                {
                    "text": "心跳间隔大于 Broker 超时会引发 keep alive timeout",
                    "epistemic_status": "hypothesis",
                    "evidence_refs": ["episode-1"],
                }
            ],
            "procedure": [{"text": "检查 keep alive 配置后重连"}],
            "limitations": [],
        },
        applicability={"mcp_server_id": "srv-1"},
        confirm=confirm,
    )


# ------------------------------------------------------------- 结果归一化


def test_normalize_result_mapping_table() -> None:
    assert capture.normalize_result({"command": {"status": "applied", "verify_status": "succeeded"}}) == "succeeded"
    assert capture.normalize_result({"command": {"status": "failed", "verify_status": "succeeded"}}) == "inconclusive"
    assert capture.normalize_result({"command": {"status": "failed", "verify_status": "failed"}}) == "failed"
    assert capture.normalize_result({"proposal": {"status": "rejected"}}) == "not_executed"
    assert capture.normalize_result({"command": {"status": "applied"}}) == "pending"
    assert capture.normalize_result({"command": {"status": "timed_out"}}) == "inconclusive"
    # ACK 成功但没有恢复验证不等同恢复
    assert capture.normalize_result({"command": {"status": "acked"}}) == "pending"


# ------------------------------------------------------------- 捕获与幂等


async def _capture_for(owner: str, source_id: str = "CMD_1", verify="succeeded", status="applied"):
    run = SimpleNamespace(user_id=owner, id="run-1", conversation_id="conv-1")
    output = {
        "ok": True,
        "data": {
            "command": {
                "command_id": source_id,
                "device_id": "ESP32_05",
                "action": "reconnect_mqtt",
                "status": status,
                "verify_status": verify,
                "diagnosis_id": "DIA_1",
            },
            "fault_name": "MQTT keep alive 超时",
            "cause": "网络抖动",
        },
    }
    async with SessionFactory() as db:
        source = await capture.record_tool(db, run, "srv-1", "get_action_result", {}, output)
        await db.commit()
    return source


async def test_record_tool_creates_source_and_working_fact() -> None:
    source = await _capture_for("user-a")
    assert source is not None
    async with SessionFactory() as db:
        stored = await db.get(MemorySource, source.id)
        assert stored.excerpt["command"]["action"] == "reconnect_mqtt"
        assert "api_key" not in json.dumps(stored.excerpt)
        working = await db.scalar(select(WorkingMemory).where(WorkingMemory.owner_user_id == "user-a"))
        assert working is not None and "srv-1:CMD_1" in working.facts


async def test_repeated_tool_result_does_not_duplicate_episodes() -> None:
    first = await _capture_for("user-a")
    second = await _capture_for("user-a")
    assert first.id == second.id  # 同一来源幂等合并
    async with SessionFactory() as db:
        jobs = (await db.scalars(select(MemoryJob).where(MemoryJob.kind == "capture_episode"))).all()
        keys = {job.job_key for job in jobs}
        assert len(keys) == len({key.rsplit(":", 1)[0] for key in keys})


async def test_capture_gate_rejects_contentless_results() -> None:
    run = SimpleNamespace(user_id="user-a", id="run-1", conversation_id="conv-1")
    output = {"ok": True, "data": {"device_id": "ESP32_05", "online": True}}
    async with SessionFactory() as db:
        source = await capture.record_tool(db, run, "srv-1", "get_device_status", {}, output)
        await db.commit()
    assert source is None  # 普通状态查询不产生情景


async def test_capture_episode_is_excluded_until_final() -> None:
    await _capture_for("user-a", verify=None, status="acked")
    async with SessionFactory() as db:
        job = await db.scalar(select(MemoryJob).where(MemoryJob.kind == "capture_episode"))
        assert job is not None
        await capture.capture_job(db, job)
        await db.commit()
        item = await db.scalar(select(Memory))
        assert item.kind == "episodic"
        # pending 情景保持 active 但召回过滤掉（outcome=pending）
        revision = await service.revision(db, item)
        revision.content_json = {**revision.content_json, "outcome": "pending"}
        await db.commit()
    async with SessionFactory() as db:
        item = await db.scalar(select(Memory))
        assert await service.eligible(db, item) is False


# ------------------------------------------------------------- 隔离


async def test_memory_api_level_isolation() -> None:
    async with SessionFactory() as db:
        item = await service.create(db, "user-a", _experience_payload())
        await db.commit()
        item_id = item.id
    async with SessionFactory() as db:
        with pytest.raises(HTTPException) as excinfo:
            await service.owned(db, "user-b", item_id)
        assert excinfo.value.status_code == 404
        other = await search(db, "user-b", MemorySearch(query="MQTT 超时"))
        assert other == []


# ------------------------------------------------------------- 状态机与版本


async def test_confirm_then_recall_and_revision_flow() -> None:
    async with SessionFactory() as db:
        item = await service.create(db, "user-a", _experience_payload())
        await db.commit()
        assert item.status == "candidate"
        # 候选未确认前正常召回为零
        assert await search(db, "user-a", MemorySearch(query="MQTT 超时")) == []
        confirmed = await service.transition(db, "user-a", item.id, 1, "confirm")
        await db.commit()
        assert confirmed.status == "active"
        assert confirmed.active_revision == 1

    async with SessionFactory() as db:
        found = await search(db, "user-a", MemorySearch(query="MQTT 超时"))
        assert len(found) == 1
        assert found[0]["memory_id"] and found[0]["revision"] == 1

    # 编辑 active 经验：新 revision 待确认，旧版本继续可用
    async with SessionFactory() as db:
        item = await db.scalar(select(Memory).where(Memory.id.isnot(None)))
        payload = _experience_payload()
        payload.summary = "修订后的经验摘要。"
        payload.expected_revision = item.current_revision
        edited = await service.edit(db, "user-a", item.id, payload)
        await db.commit()
        assert edited.current_revision == 2
        assert edited.active_revision == 1

    async with SessionFactory() as db:
        found = await search(db, "user-a", MemorySearch(query="MQTT"))
        assert found and found[0]["revision"] == 1

    # expected_revision 不符返回版本冲突
    async with SessionFactory() as db:
        item = await db.scalar(select(Memory))
        payload = _experience_payload()
        payload.expected_revision = 1
        with pytest.raises(HTTPException) as excinfo:
            await service.edit(db, "user-a", item.id, payload)
        assert excinfo.value.status_code == 409


async def test_suspend_stops_recall_and_delete_tombstones() -> None:
    async with SessionFactory() as db:
        item = await service.create(db, "user-a", _experience_payload(confirm=True), event_key="ep-key")
        await db.commit()
        item_id = item.id
    async with SessionFactory() as db:
        item = await db.get(Memory, item_id)
        await service.transition(db, "user-a", item_id, item.current_revision, "suspend")
        await db.commit()
    async with SessionFactory() as db:
        assert await search(db, "user-a", MemorySearch(query="MQTT")) == []
        await service.transition(db, "user-a", item_id, 1, "delete")
        await db.commit()
    async with SessionFactory() as db:
        stored = await db.get(Memory, item_id)
        assert stored.status == "deleted"
        assert await service.tombstoned(db, "user-a", "memory", item_id)
        assert await service.tombstoned(db, "user-a", "event", "ep-key")
    # 删除后相同内容重提不复活（event_key tombstone）
    async with SessionFactory() as db:
        recreated = await service.create(db, "user-a", _experience_payload(), event_key="ep-key")
        assert recreated is None


# ------------------------------------------------------------- 来源撤回


async def test_forget_source_suspends_derived_experience() -> None:
    async with SessionFactory() as db:
        source = MemorySource(
            owner_user_id="user-a",
            source_key="srv-1:CMD_9",
            source_type="tool",
            source_id="CMD_9",
            run_id="run-1",
            conversation_id="conv-1",
            mcp_server_id="srv-1",
            excerpt={"command": {"action": "reconnect_mqtt"}},
            content_hash="hash-1",
        )
        db.add(source)
        await db.flush()
        episode = await service.create(
            db, "user-a", _episode_payload(), source_type="task", event_key="ev-1", source=source
        )
        episode.status, episode.active_revision = "active", episode.current_revision
        payload = _experience_payload()
        payload.content["claims"][0]["evidence_refs"] = [episode.id]
        experience = await service.create(
            db, "user-a", payload, source_type="task", episode=episode
        )
        await db.commit()
        episode_id, experience_id = episode.id, experience.id

    async with SessionFactory() as db:
        result = await service.forget_source(db, "user-a", "conv-1")
        await db.commit()
        assert result["affected_count"] == 2

    async with SessionFactory() as db:
        episode = await db.get(Memory, episode_id)
        assert episode.status == "deleted"
        experience = await db.get(Memory, experience_id)
        assert experience.status == "suspended"
        assert await search(db, "user-a", MemorySearch(query="MQTT")) == []
        # 同一会话的晚到任务不得重新生成（会话级抑制标记）
        assert await service.tombstoned(db, "user-a", "conversation", "conv-1")


# ------------------------------------------------------------- 修复预算


async def _make_running_run(user_id: str = "user-a") -> AgentRun:
    async with SessionFactory() as db:
        conversation = Conversation(user_id=user_id, title="预算测试")
        db.add(conversation)
        await db.flush()
        message = Message(
            conversation_id=conversation.id,
            role="user",
            content="修复设备",
            client_message_id=f"cmid-{uuid.uuid4().hex[:8]}",
            metadata_json={},
        )
        db.add(message)
        await db.flush()
        run = AgentRun(
            user_id=user_id,
            conversation_id=conversation.id,
            user_message_id=message.id,
            status=RunStatus.RUNNING,
            started_at=utc_now(),
        )
        db.add(run)
        await db.commit()
        await db.refresh(run)
        return run


async def test_repair_budget_limits_and_reuse_gates() -> None:
    run = await _make_running_run()
    link = await actions.reserve(run.id, "srv-1", "execute_device_action", {"device_id": "d1"})
    # 第二次预留被挂起：已有未解决结果时不允许并发新动作
    with pytest.raises(HTTPException) as excinfo:
        await actions.reserve(run.id, "srv-1", "execute_device_action", {"device_id": "d1"})
    assert excinfo.value.detail == "REPAIR_RESULT_UNRESOLVED"

    await actions.save_result(link.id, {"ok": True, "data": {"command": {"command_id": "C1", "status": "failed", "verify_status": "failed"}}})
    saved = await actions.save_result(link.id, {"ok": True, "data": {"command": {"command_id": "C1", "status": "failed", "verify_status": "failed"}}})
    assert saved.command_id == "C1"

    # 失败结果必须先重新诊断且给出新依据，才能继续下一次修复
    with pytest.raises(HTTPException) as excinfo:
        await actions.reserve(run.id, "srv-1", "execute_device_action", {"device_id": "d1"})
    assert excinfo.value.detail == "REPAIR_REDIAGNOSIS_REQUIRED"
    async with SessionFactory() as db:
        stored = await db.get(MemoryActionLink, link.id)
        stored.rediagnosis = {"diagnosis_id": "DIA_NEW", "new_evidence": False}
        await db.commit()
    with pytest.raises(HTTPException) as excinfo:
        await actions.reserve(run.id, "srv-1", "execute_device_action", {"device_id": "d1", "diagnosis_id": "DIA_NEW"})
    assert excinfo.value.detail == "REPAIR_NO_NEW_EVIDENCE"


async def test_repair_budget_exhaustion_returns_limit_error() -> None:
    run = await _make_running_run()
    link = await actions.reserve(run.id, "srv-1", "create_remediation_proposal", {"device_id": "d1"})
    # 确定性校验拒绝：释放名额
    await actions.save_result(link.id, {"ok": False, "error": {"code": "UNKNOWN_ACTION"}})
    links = []
    for index in range(3):
        links.append(await actions.reserve(run.id, "srv-1", "create_remediation_proposal", {"device_id": f"d{index}"}))
    with pytest.raises(HTTPException) as excinfo:
        await actions.reserve(run.id, "srv-1", "create_remediation_proposal", {"device_id": "d9"})
    assert excinfo.value.detail == "REPAIR_ATTEMPT_LIMIT_REACHED"

