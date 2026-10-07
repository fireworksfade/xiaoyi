"""Memory 模块验收测试（spec §16）。

覆盖：结果归一化（AC02/AC28）、价值门控与幂等（AC01/AC06）、用户隔离（AC10）、
状态机与版本（AC03/AC05）、来源撤回（AC18/AC27）、召回过滤（AC12）、
修复预算与再诊断门槛（AC30/AC31）、工作记忆读取（§3.1）、使用记录与反馈
（§5.3/§7.6）、反例暂停（§6.3）、修复循环停止事件（§13.2）、
原生记忆工具（§10.2）、历史迁移分配（AC19/AC20/AC26）。
"""

import json
import uuid
from datetime import timedelta
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import delete, select

from app.config import get_settings
from app.db import SessionFactory
from app.memory import actions, capture, reconcile, service
from app.memory.boundary import rediagnose
from app.memory.models import (
    Memory,
    MemoryActionLink,
    MemoryEvidenceLink,
    MemoryFeedback,
    MemoryIndexState,
    MemoryJob,
    MemoryRevision,
    MemorySource,
    MemoryTombstone,
    MemoryUsage,
    MemoryVectorOutbox,
    WorkingMemory,
)
from app.memory.retrieval import search
from app.memory.schemas import MemorySearch, MemoryWrite
from app.models import AgentRun, Conversation, Message, RunEvent, RunStatus, User, utc_now


async def _cleanup_memory_tables() -> None:
    async with SessionFactory() as db:
        # users 一并清空：否则先前测试创建的用户会阻止 seed_users 落库 admin
        await db.execute(delete(User))
        for model in (
            MemoryUsage,
            MemoryFeedback,
            MemoryEvidenceLink,
            MemoryIndexState,
            MemoryVectorOutbox,
            MemoryRevision,
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
    previous = (
        settings.memory_enabled,
        settings.memory_auto_capture,
        settings.memory_auto_propose_experience,
    )
    (
        settings.memory_enabled,
        settings.memory_auto_capture,
        settings.memory_auto_propose_experience,
    ) = True, True, True
    await _cleanup_memory_tables()
    yield
    await _cleanup_memory_tables()
    (
        settings.memory_enabled,
        settings.memory_auto_capture,
        settings.memory_auto_propose_experience,
    ) = previous


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
    assert (
        capture.normalize_result({"command": {"status": "applied", "verify_status": "succeeded"}})
        == "succeeded"
    )
    assert (
        capture.normalize_result({"command": {"status": "failed", "verify_status": "succeeded"}})
        == "inconclusive"
    )
    assert (
        capture.normalize_result({"command": {"status": "failed", "verify_status": "failed"}})
        == "failed"
    )
    assert capture.normalize_result({"proposal": {"status": "rejected"}}) == "not_executed"
    assert capture.normalize_result({"command": {"status": "applied"}}) == "pending"
    assert capture.normalize_result({"command": {"status": "timed_out"}}) == "inconclusive"
    assert capture.normalize_result({"command": {"status": "applied", "verify_status": "inconclusive"}}) == "inconclusive"
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
        working = await db.scalar(
            select(WorkingMemory).where(WorkingMemory.owner_user_id == "user-a")
        )
        assert working is not None and "srv-1:CMD_1" in working.facts


async def test_repeated_tool_result_does_not_duplicate_episodes() -> None:
    first = await _capture_for("user-a")
    second = await _capture_for("user-a")
    assert first.id == second.id  # 同一来源幂等合并
    async with SessionFactory() as db:
        jobs = (
            await db.scalars(select(MemoryJob).where(MemoryJob.kind == "capture_episode"))
        ).all()
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
        item = await service.create(
            db, "user-a", _experience_payload(confirm=True), event_key="ep-key"
        )
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

    await actions.save_result(
        link.id,
        {
            "ok": True,
            "data": {
                "command": {"command_id": "C1", "status": "failed", "verify_status": "failed"}
            },
        },
    )
    saved = await actions.save_result(
        link.id,
        {
            "ok": True,
            "data": {
                "command": {"command_id": "C1", "status": "failed", "verify_status": "failed"}
            },
        },
    )
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
        await actions.reserve(
            run.id, "srv-1", "execute_device_action", {"device_id": "d1", "diagnosis_id": "DIA_NEW"}
        )
    assert excinfo.value.detail == "REPAIR_NO_NEW_EVIDENCE"


async def test_repair_budget_exhaustion_returns_limit_error() -> None:
    run = await _make_running_run()
    link = await actions.reserve(
        run.id, "srv-1", "create_remediation_proposal", {"device_id": "d1"}
    )
    # 确定性校验拒绝：释放名额
    await actions.save_result(link.id, {"ok": False, "error": {"code": "UNKNOWN_ACTION"}})
    links = []
    for index in range(3):
        links.append(
            await actions.reserve(
                run.id, "srv-1", "create_remediation_proposal", {"device_id": f"d{index}"}
            )
        )
    with pytest.raises(HTTPException) as excinfo:
        await actions.reserve(run.id, "srv-1", "create_remediation_proposal", {"device_id": "d9"})
    assert excinfo.value.detail == "REPAIR_ATTEMPT_LIMIT_REACHED"


# ------------------------------------------------------------- 工作记忆读取（spec 3.1）


async def test_working_memory_snapshot_expiry_budget_and_scope() -> None:
    run = await _make_running_run()
    async with SessionFactory() as db:
        await service.working_fact(db, run, "srv-1:D1", {"evidence": {"command_id": "D1"}})
        await db.commit()
    async with SessionFactory() as db:
        working = await service.working_snapshot(db, run.user_id, run.conversation_id)
        assert working is not None
        message = service.build_working_message(working, available_tokens=10_000)
        assert message["role"] == "system" and "srv-1:D1" in message["content"]
        # 预算不足时整条放弃，不截断关键事实
        assert service.build_working_message(working, available_tokens=1) is None
        # 另一会话不能直接加载
        assert await service.working_snapshot(db, run.user_id, "conv-other") is None
        # 过期后停止加载临时摘要
        working.expires_at = utc_now() - timedelta(seconds=1)
        await db.commit()
    async with SessionFactory() as db:
        assert await service.working_snapshot(db, run.user_id, run.conversation_id) is None


# ------------------------------------------------------------- 再诊断端到端（AC29/AC30/AC31/AC32）


async def _failed_repair(run, device="d1", index=0) -> MemoryActionLink:
    link = await actions.reserve(
        run.id,
        "srv-1",
        "execute_device_action",
        {"device_id": device, "diagnosis_id": f"DIA_{index}"},
    )
    await actions.save_result(
        link.id,
        {
            "ok": True,
            "data": {
                "command": {
                    "command_id": f"C{index}",
                    "device_id": device,
                    "status": "failed",
                    "verify_status": "failed",
                }
            },
        },
    )
    return link


async def _set_rediagnosis(link_id, diagnosis_id, new_evidence=True, memories=None) -> None:
    async with SessionFactory() as db:
        stored = await db.get(MemoryActionLink, link_id)
        stored.rediagnosis = {
            "diagnosis_id": diagnosis_id,
            "new_evidence": new_evidence,
            "memories": memories or [],
        }
        if memories:
            await service.record_usage(
                db, stored.owner_user_id, memories, run_id=stored.run_id, stage="retrieved"
            )
        await db.commit()


async def test_rediagnosis_feeds_next_repair_with_context() -> None:
    run = await _make_running_run()
    link = await _failed_repair(run)
    seen: dict[str, dict] = {}

    async def call(tool, arguments):
        seen[tool] = arguments
        if tool == "diagnose_fault":
            return SimpleNamespace(
                structured_content={
                    "ok": True,
                    "data": {
                        "diagnosis_id": "DIA_NEW",
                        "new_evidence": True,
                        "fault_name": "MQTT keep alive 超时",
                    },
                }
            )
        return SimpleNamespace(
            structured_content={"ok": True, "data": {"device_id": "d1", "online": False}}
        )

    result = await rediagnose(run.id, "srv-1", link.id, call)
    assert result["diagnosis_id"] == "DIA_NEW" and result["new_evidence"] is True
    # AC29：诊断模型实际收到前次假设/动作、失败证据、最新证据与剩余预算
    repair_context = seen["diagnose_fault"]["repair_context"]
    assert repair_context["previous_action"]["device_id"] == "d1"
    assert repair_context["previous_diagnosis_id"] == "DIA_0"
    assert repair_context["failed_result"]["command"]["command_id"] == "C0"
    assert "get_device_status" in repair_context["latest_evidence"]
    assert "get_device_logs" in repair_context["latest_evidence"]
    assert repair_context["remaining_attempts"] == 2
    assert "memory_context" in seen["diagnose_fault"]
    async with SessionFactory() as db:
        events = (
            await db.scalars(select(RunEvent.event_type).where(RunEvent.run_id == run.id))
        ).all()
        assert "remediation.rediagnosis_started" in events
        assert "remediation.rediagnosis_completed" in events
        stored = await db.get(MemoryActionLink, link.id)
        assert "memories" in stored.rediagnosis  # 注入诊断的记忆被记录，供 applied 反馈链使用
    # 有新依据才允许下一次修复
    next_link = await actions.reserve(
        run.id, "srv-1", "execute_device_action", {"device_id": "d1", "diagnosis_id": "DIA_NEW"}
    )
    assert next_link.diagnosis_id == "DIA_NEW"


async def test_rediagnosis_without_new_evidence_stops_loop() -> None:
    run = await _make_running_run()
    link = await _failed_repair(run)

    async def call(tool, arguments):
        if tool == "diagnose_fault":
            return SimpleNamespace(
                structured_content={
                    "ok": True,
                    "data": {"diagnosis_id": "DIA_SAME", "new_evidence": False},
                }
            )
        return SimpleNamespace(structured_content={"ok": True, "data": {}})

    result = await rediagnose(run.id, "srv-1", link.id, call)
    assert result["new_evidence"] is False
    with pytest.raises(HTTPException) as excinfo:
        await actions.reserve(
            run.id,
            "srv-1",
            "execute_device_action",
            {"device_id": "d1", "diagnosis_id": "DIA_SAME"},
        )
    assert excinfo.value.detail == "REPAIR_NO_NEW_EVIDENCE"
    async with SessionFactory() as db:
        stops = (
            await db.scalars(
                select(RunEvent).where(
                    RunEvent.run_id == run.id, RunEvent.event_type == "remediation.loop_stopped"
                )
            )
        ).all()
        assert [stop.data["reason"] for stop in stops] == ["no_new_evidence"]


async def test_three_failures_exhaust_budget_and_stop_loop() -> None:
    run = await _make_running_run()
    for index in range(3):
        link = await _failed_repair(run, device=f"d{index}", index=index)
        await _set_rediagnosis(link.id, f"DIA_{index}", new_evidence=True)
    with pytest.raises(HTTPException) as excinfo:
        await actions.reserve(
            run.id, "srv-1", "execute_device_action", {"device_id": "d9", "diagnosis_id": "DIA_2"}
        )
    assert excinfo.value.detail == "REPAIR_ATTEMPT_LIMIT_REACHED"
    async with SessionFactory() as db:
        stops = (
            await db.scalars(
                select(RunEvent).where(
                    RunEvent.run_id == run.id, RunEvent.event_type == "remediation.loop_stopped"
                )
            )
        ).all()
        assert stops[-1].data["reason"] == "attempt_limit_reached"
        assert stops[-1].data["used"] == 3 and stops[-1].data["reserved"] == 0
        assert stops[-1].data["origin_run_id"] == run.id


async def test_rediagnosis_respects_run_deadline() -> None:
    run = await _make_running_run()
    link = await _failed_repair(run)
    settings = get_settings()
    previous = settings.agent_run_max_runtime_minutes
    settings.agent_run_max_runtime_minutes = 1
    async with SessionFactory() as db:
        stored_run = await db.get(AgentRun, run.id)
        stored_run.started_at = utc_now() - timedelta(hours=2)
        await db.commit()

    async def call(tool, arguments):
        raise AssertionError("超过运行期限后不得继续调用诊断工具")

    try:
        assert await rediagnose(run.id, "srv-1", link.id, call) is None
    finally:
        settings.agent_run_max_runtime_minutes = previous
    async with SessionFactory() as db:
        stops = (
            await db.scalars(
                select(RunEvent).where(
                    RunEvent.run_id == run.id, RunEvent.event_type == "remediation.loop_stopped"
                )
            )
        ).all()
        assert [stop.data["reason"] for stop in stops] == ["run_deadline"]


async def test_run_finished_failure_records_followup_event() -> None:
    run = await _make_running_run()
    link = await actions.reserve(run.id, "srv-1", "execute_device_action", {"device_id": "d1"})
    async with SessionFactory() as db:
        stored_run = await db.get(AgentRun, run.id)
        stored_run.status = RunStatus.FAILED
        await db.commit()
    await actions.save_result(
        link.id,
        {
            "ok": True,
            "data": {
                "command": {
                    "command_id": "C_LATE",
                    "device_id": "d1",
                    "status": "failed",
                    "verify_status": "failed",
                }
            },
        },
    )
    async with SessionFactory() as db:
        stops = (
            await db.scalars(
                select(RunEvent).where(
                    RunEvent.run_id == run.id, RunEvent.event_type == "remediation.loop_stopped"
                )
            )
        ).all()
        assert [stop.data["reason"] for stop in stops] == ["run_finished"]
        assert stops[0].data["needs_followup"] is True


# ------------------------------------------------------------- 使用记录、反馈与反例（spec 5.3/6.3/7.6）


async def test_usage_feedback_and_counterexample_suspend() -> None:
    async with SessionFactory() as db:
        experience = await service.create(db, "user-a", _experience_payload(confirm=True))
        await db.commit()
        experience_id = experience.id
    run = await _make_running_run()
    link = await _failed_repair(run)
    await _set_rediagnosis(
        link.id,
        "DIA_NEW",
        new_evidence=True,
        memories=[{"memory_id": experience_id, "revision": 1}],
    )
    next_link = await actions.reserve(
        run.id,
        "srv-1",
        "execute_device_action",
        {"device_id": "d1", "diagnosis_id": "DIA_NEW"},
        applied_memory_refs=[{"memory_id": experience_id, "revision": 1}],
    )
    async with SessionFactory() as db:
        stored = await db.get(MemoryActionLink, next_link.id)
        assert stored.applied_memory_ids == [{"memory_id": experience_id, "revision": 1}]
        stages = {
            usage.stage
            for usage in (
                await db.scalars(select(MemoryUsage).where(MemoryUsage.owner_user_id == "user-a"))
            ).all()
        }
        assert "applied" not in stages
    await actions.save_result(
        next_link.id,
        {
            "ok": True,
            "data": {
                "command": {
                    "command_id": "C_ADOPTED",
                    "device_id": "d1",
                    "status": "failed",
                    "verify_status": "failed",
                }
            },
        },
    )
    async with SessionFactory() as db:
        assert await db.scalar(select(MemoryUsage.id).where(MemoryUsage.stage == "applied"))
        item = await db.get(Memory, experience_id)
        assert item.status == "suspended"  # No worker is needed to stop recall.
        feedback = (
            await db.scalars(select(MemoryFeedback).where(MemoryFeedback.owner_user_id == "user-a"))
        ).all()
        assert len(feedback) == 1
        assert feedback[0].outcome == "failed" and feedback[0].command_id == "C_ADOPTED"
        job = await db.scalar(select(MemoryJob).where(MemoryJob.kind == "reconcile_experience"))
        assert job is not None and job.payload["scope_matched"] is True
    await reconcile.reconcile(job)
    async with SessionFactory() as db:
        item = await db.get(Memory, experience_id)
        assert item.status == "suspended" and item.current_revision == 2
        assert item.active_revision == 1
        # 暂停后不再作为有效参考注入
        assert await search(db, "user-a", MemorySearch(query="MQTT")) == []
        rev = await service.revision(db, item)
        assert any("反例" in lim["text"] for lim in rev.content_json["limitations"])
        assert rev.review_state == "candidate"  # 修订待确认，不自动覆盖反例


async def test_counterexample_out_of_scope_only_records_feedback() -> None:
    payload = _experience_payload(confirm=True)
    payload.applicability = {"mcp_server_id": "srv-1", "device_ids": ["OTHER_DEV"]}
    async with SessionFactory() as db:
        experience = await service.create(db, "user-a", payload)
        await db.commit()
        experience_id = experience.id
    run = await _make_running_run()
    link = await actions.reserve(run.id, "srv-1", "execute_device_action", {"device_id": "d1"})
    await actions.save_result(
        link.id,
        {
            "ok": True,
            "data": {
                "command": {
                    "command_id": "C1",
                    "device_id": "d1",
                    "status": "failed",
                    "verify_status": "failed",
                }
            },
        },
    )
    await _set_rediagnosis(
        link.id, "DIA_X", new_evidence=True, memories=[{"memory_id": experience_id, "revision": 1}]
    )
    next_link = await actions.reserve(
        run.id,
        "srv-1",
        "execute_device_action",
        {"device_id": "d1", "diagnosis_id": "DIA_X"},
        applied_memory_refs=[{"memory_id": experience_id, "revision": 1}],
    )
    await actions.save_result(
        next_link.id,
        {
            "ok": True,
            "data": {
                "command": {
                    "command_id": "C2",
                    "device_id": "d1",
                    "status": "failed",
                    "verify_status": "failed",
                }
            },
        },
    )
    async with SessionFactory() as db:
        job = await db.scalar(select(MemoryJob).where(MemoryJob.kind == "reconcile_experience"))
        assert job.payload["scope_matched"] is False
        item = await db.get(Memory, experience_id)
        assert item.status == "active" and item.current_revision == 1
    await reconcile.reconcile(job)
    async with SessionFactory() as db:
        item = await db.get(Memory, experience_id)
        # 条件不一致：只记范围问题（反馈），不暂停、不改写
        assert item.status == "active" and item.current_revision == 1
        feedback = (
            await db.scalars(
                select(MemoryFeedback).where(MemoryFeedback.memory_id == experience_id)
            )
        ).all()
        assert len(feedback) == 1 and feedback[0].outcome == "failed"


async def test_retrieval_records_usage_and_use_count() -> None:
    async with SessionFactory() as db:
        await service.create(db, "user-a", _experience_payload(confirm=True))
        await db.commit()
    async with SessionFactory() as db:
        found = await search(db, "user-a", MemorySearch(query="MQTT 超时"))
        assert found
        await db.commit()
        usages = (
            await db.scalars(select(MemoryUsage).where(MemoryUsage.stage == "retrieved"))
        ).all()
        assert len(usages) == len(found)
        stored = await db.get(Memory, found[0]["memory_id"])
        assert stored.use_count == 1 and stored.last_used_at is not None


# ------------------------------------------------------------- 原生记忆工具（spec 10.2）


async def test_memory_tool_handlers_bind_to_run_user() -> None:
    from app.agent.memory_tools import handle_memory_tool

    run = await _make_running_run()
    async with SessionFactory() as db:
        item = await service.create(db, run.user_id, _experience_payload(confirm=True))
        await db.commit()
        item_id = item.id
    found = await handle_memory_tool(run.id, "search_memory", {"query": "MQTT 超时"})
    assert found["items"] and found["items"][0]["memory_id"] == item_id
    detail = await handle_memory_tool(run.id, "get_memory", {"memory_id": item_id})
    assert detail["item"]["id"] == item_id
    assert await handle_memory_tool(run.id, "get_memory", {"memory_id": "missing"}) == {
        "error": "MEMORY_NOT_FOUND"
    }
    proposed = await handle_memory_tool(
        run.id,
        "propose_memory",
        {
            "title": "模型提议的经验",
            "summary": "候选不自动启用。",
            "content": {
                "claims": [
                    {"text": "假设", "epistemic_status": "observed", "evidence_refs": ["fake"]}
                ]
            },
            "applicability": {"mcp_server_id": "srv-1"},
        },
    )
    assert proposed["status"] == "candidate" and proposed.get("note")
    async with SessionFactory() as db:
        stored = await db.get(Memory, proposed["id"])
        assert stored.status == "candidate" and stored.source_type == "task"
        revision = await service.revision(db, stored)
        claim = revision.content_json["claims"][0]
        # 模型不能自称已观察，也不能伪造证据引用
        assert claim["epistemic_status"] == "hypothesis" and claim["evidence_refs"] != ["fake"]


async def test_memory_lifecycle_metrics_increment() -> None:
    from prometheus_client import REGISTRY

    async with SessionFactory() as db:
        item = await service.create(db, "user-a", _experience_payload())
        await db.commit()
        await service.transition(db, "user-a", item.id, 1, "confirm")
        await db.commit()

    def metric(event: str) -> float:
        return REGISTRY.get_sample_value("xiaoyi_memory_events_total", {"event": event}) or 0.0

    assert metric("confirmed") >= 1


async def test_run_creation_pins_repair_budget() -> None:
    budget = actions.pinned_budget()
    assert budget == {"limit": get_settings().agent_repair_max_attempts, "reserved": 0, "used": 0}
    run = await _make_running_run()
    async with SessionFactory() as db:
        stored = await db.get(AgentRun, run.id)
        stored.runtime_state = {"repair_budget": actions.pinned_budget()}
        await db.commit()
    # 固化后的预算与 reserve 的读取一致：3 次用尽即拒绝
    for index in range(3):
        await actions.reserve(
            run.id, "srv-1", "create_remediation_proposal", {"device_id": f"d{index}"}
        )
    with pytest.raises(HTTPException) as excinfo:
        await actions.reserve(run.id, "srv-1", "create_remediation_proposal", {"device_id": "d9"})
    assert excinfo.value.detail == "REPAIR_ATTEMPT_LIMIT_REACHED"


# ------------------------------------------------------------- 适用范围与不确定性（AC11）


async def test_retrieval_applicability_scoping_and_uncertainty() -> None:
    payload = _experience_payload(confirm=True)
    payload.applicability = {"mcp_server_id": "srv-1", "device_ids": ["ESP32_05"]}
    async with SessionFactory() as db:
        await service.create(db, "user-a", payload)
        await db.commit()
    async with SessionFactory() as db:
        # 同名设备在不同 MCP 服务下不误匹配：整体排除
        assert (
            await search(
                db,
                "user-a",
                MemorySearch(query="MQTT 超时", mcp_server_id="srv-2", device_id="ESP32_05"),
            )
            == []
        )
        # 设备明确不适用：排除
        assert (
            await search(
                db,
                "user-a",
                MemorySearch(query="MQTT 超时", mcp_server_id="srv-1", device_id="OTHER"),
            )
            == []
        )
        # 范围未知时不能当作已满足条件，返回"适用性待核实"
        found = await search(db, "user-a", MemorySearch(query="MQTT 超时", mcp_server_id="srv-1"))
        assert found and any(u.startswith("适用性待核实") for u in found[0]["uncertainty"])


# ------------------------------------------------------------- 向量索引一致性（AC16）


class _FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP_{self.status_code}")

    def json(self):
        return self._payload


class _FakeQdrantClient:
    requests: list = []

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def put(self, url, json=None):
        _FakeQdrantClient.requests.append(("PUT", url))
        if url.endswith("/points?wait=true"):
            return _FakeResponse(200)
        return _FakeResponse(201)

    async def post(self, url, json=None):
        _FakeQdrantClient.requests.append(("POST", url))
        if url.endswith("/embeddings"):
            return _FakeResponse(
                200, {"data": [{"embedding": [0.0] * get_settings().memory_embedding_dimensions}]}
            )
        if url.endswith("/points/query"):
            return _FakeResponse(200, {"result": {"points": []}})
        return _FakeResponse(200)


async def test_vector_indexing_uses_owner_filter_and_marks_indexed(monkeypatch) -> None:
    settings = get_settings()
    monkeypatch.setattr("app.memory.indexing.httpx.AsyncClient", _FakeQdrantClient)
    previous = (settings.memory_qdrant_url, settings.memory_embedding_url)
    settings.memory_qdrant_url = "http://qdrant:6333"
    settings.memory_embedding_url = "http://embed:8080"
    try:
        async with SessionFactory() as db:
            await service.create(db, "user-a", _experience_payload(confirm=True))
            await db.commit()
        from app.memory.indexing import sync, vector_search

        async with SessionFactory() as db:
            job_id = await db.scalar(select(MemoryJob.id).where(MemoryJob.kind == "sync_vector"))
            outbox_id = await db.scalar(select(MemoryJob.payload).where(MemoryJob.id == job_id))
        from types import SimpleNamespace

        await sync(SimpleNamespace(payload=outbox_id))
        async with SessionFactory() as db:
            state = await db.scalar(select(MemoryIndexState))
            assert state.status == "indexed"
        # 空 owner 绝不退化为全库查询
        assert await vector_search("", MemorySearch(query="MQTT")) == {}
    finally:
        settings.memory_qdrant_url, settings.memory_embedding_url = previous


async def test_vector_indexing_fingerprint_mismatch_and_late_upsert_never_revive(
    monkeypatch,
) -> None:
    from types import SimpleNamespace

    settings = get_settings()
    monkeypatch.setattr("app.memory.indexing.httpx.AsyncClient", _FakeQdrantClient)
    previous = (
        settings.memory_qdrant_url,
        settings.memory_embedding_url,
        settings.memory_embedding_fingerprint,
    )
    settings.memory_qdrant_url = "http://qdrant:6333"
    settings.memory_embedding_url = "http://embed:8080"
    try:
        async with SessionFactory() as db:
            item = await service.create(db, "user-a", _experience_payload(confirm=True))
            await db.commit()
            item_id, revision = item.id, item.current_revision
        from app.memory.indexing import sync
        from app.memory.models import MemoryVectorOutbox

        async with SessionFactory() as db:
            outbox_id = await db.scalar(
                select(MemoryVectorOutbox.id).where(MemoryVectorOutbox.memory_id == item_id)
            )
        await sync(SimpleNamespace(payload={"outbox_id": outbox_id}))
        async with SessionFactory() as db:
            state = await db.scalar(select(MemoryIndexState))
            assert state.status == "indexed"
        _FakeQdrantClient.requests.clear()

        # 模型指纹变化后，旧指纹的 upsert 直接放弃并清除，不覆盖新版本
        old_fingerprint = settings.memory_embedding_fingerprint
        settings.memory_embedding_fingerprint = "other-model"
        async with SessionFactory() as db:
            stale = MemoryVectorOutbox(
                owner_user_id="user-a",
                memory_id=item_id,
                revision=revision,
                operation="upsert",
                model_fingerprint=old_fingerprint,
                collection=f"{settings.memory_collection_prefix}_{old_fingerprint}_{settings.memory_embedding_dimensions}_v1",
            )
            db.add(stale)
            await db.flush()
            stale_id = stale.id
            await db.commit()
        await sync(SimpleNamespace(payload={"outbox_id": stale_id}))
        assert not [
            r
            for r in _FakeQdrantClient.requests
            if r[0] == "PUT" and r[1].endswith("/points?wait=true")
        ]
        assert any(
            r[0] == "POST" and r[1].endswith("/points/delete?wait=true")
            for r in _FakeQdrantClient.requests
        )
        async with SessionFactory() as db:
            row = await db.scalar(
                select(MemoryIndexState).where(
                    MemoryIndexState.memory_id == item_id,
                    MemoryIndexState.revision == revision,
                    MemoryIndexState.model_fingerprint == old_fingerprint,
                )
            )
            assert row.status == "excluded"
        _FakeQdrantClient.requests.clear()

        # 删除记忆：purge 任务清掉已索引版本
        async with SessionFactory() as db:
            await service.transition(db, "user-a", item_id, revision, "delete")
            await db.commit()
            purge_id = await db.scalar(
                select(MemoryVectorOutbox.id)
                .where(
                    MemoryVectorOutbox.memory_id == item_id,
                    MemoryVectorOutbox.operation == "purge",
                    MemoryVectorOutbox.status != "done",
                )
                .order_by(MemoryVectorOutbox.id.desc())
                .limit(1)
            )
        await sync(SimpleNamespace(payload={"outbox_id": purge_id}))
        assert any(
            r[0] == "POST" and r[1].endswith("/points/delete?wait=true")
            for r in _FakeQdrantClient.requests
        )

        # 任何晚到的 upsert 都不能让已删除记忆的向量复活
        async with SessionFactory() as db:
            late = MemoryVectorOutbox(
                owner_user_id="user-a",
                memory_id=item_id,
                revision=revision,
                operation="upsert",
                model_fingerprint=settings.memory_embedding_fingerprint,
                collection=f"{settings.memory_collection_prefix}_{settings.memory_embedding_fingerprint}_{settings.memory_embedding_dimensions}_v1",
            )
            db.add(late)
            await db.flush()
            late_id = late.id
            await db.commit()
        await sync(SimpleNamespace(payload={"outbox_id": late_id}))
        assert not [
            r
            for r in _FakeQdrantClient.requests
            if r[0] == "PUT" and r[1].endswith("/points?wait=true")
        ]
    finally:
        settings.memory_qdrant_url, settings.memory_embedding_url = previous[0], previous[1]
        settings.memory_embedding_fingerprint = previous[2]


# ------------------------------------------------------------- 延迟批准与名额（AC33）


async def test_pending_proposal_reservation_and_release() -> None:
    run = await _make_running_run()
    links = []
    for index in range(3):
        links.append(
            await actions.reserve(
                run.id,
                "srv-1",
                "create_remediation_proposal",
                {"device_id": f"d{index}", "diagnosis_id": "DIA_0"},
            )
        )
    # 3 个待批提案占满额度，第 4 个被拒绝
    with pytest.raises(HTTPException) as excinfo:
        await actions.reserve(
            run.id,
            "srv-1",
            "create_remediation_proposal",
            {"device_id": "d9", "diagnosis_id": "DIA_0"},
        )
    assert excinfo.value.detail == "REPAIR_ATTEMPT_LIMIT_REACHED"
    # 提案被拒绝：确认无命令后名额释放
    await actions.save_result(
        links[0].id,
        {
            "ok": True,
            "data": {"proposal": {"proposal_id": "P0", "status": "rejected", "device_id": "d0"}},
        },
    )
    async with SessionFactory() as db:
        released = await db.get(MemoryActionLink, links[0].id)
        assert released.reservation == "released" and released.outcome == "not_executed"
    next_link = await actions.reserve(
        run.id, "srv-1", "create_remediation_proposal", {"device_id": "d3", "diagnosis_id": "DIA_0"}
    )
    assert next_link.reservation == "reserved"


async def test_late_approval_stays_on_original_run_budget() -> None:
    run = await _make_running_run()
    link = await actions.reserve(
        run.id, "srv-1", "create_remediation_proposal", {"device_id": "d1", "diagnosis_id": "DIA_0"}
    )
    async with SessionFactory() as db:
        stored_run = await db.get(AgentRun, run.id)
        stored_run.status = RunStatus.FAILED
        await db.commit()
    # Run 结束后用户显式批准并执行：结果归属原 Run 的关联记录
    await actions.save_result(
        link.id,
        {
            "ok": True,
            "data": {"proposal": {"proposal_id": "P1", "status": "approved", "device_id": "d1"}},
        },
    )
    await actions.save_result(
        link.id,
        {
            "ok": True,
            "data": {
                "command": {
                    "command_id": "C_LATE",
                    "device_id": "d1",
                    "status": "applied",
                    "verify_status": "succeeded",
                }
            },
        },
    )
    async with SessionFactory() as db:
        stored = await db.get(MemoryActionLink, link.id)
        assert stored.run_id == run.id
        assert stored.reservation == "used" and stored.outcome == "succeeded"
        assert stored.command_id == "C_LATE"
    # 晚到成功不产生"需要后续诊断"信号
    async with SessionFactory() as db:
        stops = (
            await db.scalars(
                select(RunEvent).where(RunEvent.event_type == "remediation.loop_stopped")
            )
        ).all()
        assert stops == []
