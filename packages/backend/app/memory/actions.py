"""Durable action reservations and read-only result recovery."""
from datetime import timedelta

from sqlalchemy import select, update

from app.config import get_settings
from app.db import SessionFactory
from app.memory.capture import normalize_result, record_tool
from app.memory.models import Memory, MemoryActionLink, MemoryFeedback, MemorySource
from app.memory.service import digest, enqueue, fail, record_usage
from app.models import AgentRun, MCPServer, RunEvent, RunStatus, new_id, utc_now

ACTION_TOOLS = {"execute_device_action", "create_remediation_proposal"}


def pinned_budget() -> dict:
    """Run 创建时固化的修复预算；部署期调整不再影响已创建的 Run（spec 7.4）。"""
    return {"limit": get_settings().agent_repair_max_attempts, "reserved": 0, "used": 0}


def loop_stopped_event(run, links, reason, *, command_id=None, diagnosis_id=None):
    """修复循环停止事件：携带 origin_run_id、前次 command_id、已用/预留名额与停止原因（spec 13.2）。

    必须写入调用方的当前会话：另开会话会在 SQLite 上与未提交事务互相锁死。
    """
    from app.observability.metrics import REMEDIATION_LOOP_STOPS
    REMEDIATION_LOOP_STOPS.labels(reason=reason).inc()
    return RunEvent(run_id=run.id, event_type="remediation.loop_stopped", data={
        "origin_run_id": run.id, "reason": reason, "command_id": command_id,
        "diagnosis_id": diagnosis_id,
        "used": sum(link.reservation == "used" for link in links),
        "reserved": sum(link.reservation == "reserved" for link in links),
        "needs_followup": run.status != RunStatus.RUNNING,
    })


async def reserve(run_id, server_id, tool, arguments):
    async with SessionFactory() as db:
        run = await db.get(AgentRun, run_id)
        if not run or run.status != RunStatus.RUNNING:
            fail("RUN_STOPPED", 409)
        state = dict(run.runtime_state or {})
        budget = dict(state.get("repair_budget") or {"limit": get_settings().agent_repair_max_attempts, "reserved": 0, "used": 0})
        links = (await db.scalars(select(MemoryActionLink).where(MemoryActionLink.run_id == run_id))).all()
        device = arguments.get("device_id")
        # 同一设备原动作未收敛时不并发替代修复；跨设备动作共用 Run 预算
        if any(
            link.outcome == "pending" and link.reservation != "released"
            and (link.arguments or {}).get("device_id") == device
            for link in links
        ):
            fail("REPAIR_RESULT_UNRESOLVED", 409)
        if sum(link.reservation != "released" for link in links) >= budget["limit"]:
            failed = max((link for link in links if link.outcome == "failed"), key=lambda link: link.created_at, default=None)
            db.add(loop_stopped_event(run, links, "attempt_limit_reached", command_id=failed.command_id if failed else None))
            await db.commit()
            fail("REPAIR_ATTEMPT_LIMIT_REACHED", 409)
        failed_links = [
            link for link in links
            if link.outcome == "failed" and link.reservation != "released"
            and (link.arguments or {}).get("device_id") == device
        ]
        applied = []
        if failed_links:
            latest = max(failed_links, key=lambda link: link.created_at)
            rd = latest.rediagnosis or {}
            if not rd.get("diagnosis_id") or rd.get("diagnosis_id") != arguments.get("diagnosis_id"):
                fail("REPAIR_REDIAGNOSIS_REQUIRED", 409)
            if not rd.get("new_evidence"):
                db.add(loop_stopped_event(run, links, "no_new_evidence", command_id=latest.command_id, diagnosis_id=rd.get("diagnosis_id")))
                await db.commit()
                fail("REPAIR_NO_NEW_EVIDENCE", 409)
            # 再诊断依据被本次动作实际采纳：记录 applied（检索命中不等于采用，spec 5.3）
            applied = rd.get("memories") or []
        original = run.runtime_state
        budget["reserved"] = sum(link.reservation == "reserved" for link in links) + 1
        budget["used"] = sum(link.reservation == "used" for link in links)
        state["repair_budget"] = budget
        result = await db.execute(update(AgentRun).where(AgentRun.id == run_id, AgentRun.status == RunStatus.RUNNING,
            AgentRun.runtime_state == original).values(runtime_state=state))
        if not result.rowcount:
            fail("REPAIR_BUDGET_CONFLICT", 409)
        link = MemoryActionLink(owner_user_id=run.user_id, run_id=run.id, conversation_id=run.conversation_id,
            mcp_server_id=server_id, correlation_key=new_id(), parameters_hash=digest(arguments),
            arguments=arguments, tool_name=tool, diagnosis_id=arguments.get("diagnosis_id"),
            applied_memory_ids=applied,
            tracking_until=utc_now() + timedelta(days=1))
        db.add(link)
        await db.flush()
        if applied:
            await record_usage(db, run.user_id, applied, run_id=run_id,
                diagnosis_id=arguments.get("diagnosis_id"), stage="applied")
        await enqueue(db, run.user_id, "track_action", f"track:{link.id}:initial", {"link_id": link.id})
        await db.commit()
        return link


async def record_feedback(db, link, command_id, outcome):
    """有效/无效次数只来自实际采用经验关联的命令结果（spec 5.3/7.6）。"""
    from app.memory.service import revision

    for entry in link.applied_memory_ids or []:
        memory_id, revision_number = entry.get("memory_id"), entry.get("revision")
        item = await db.get(Memory, memory_id)
        if not item or item.owner_user_id != link.owner_user_id or item.kind != "experience":
            continue
        existing = await db.scalar(select(MemoryFeedback).where(
            MemoryFeedback.owner_user_id == link.owner_user_id,
            MemoryFeedback.memory_id == memory_id, MemoryFeedback.command_id == command_id))
        if existing:
            continue
        db.add(MemoryFeedback(owner_user_id=link.owner_user_id, memory_id=memory_id,
            revision=revision_number, command_id=command_id, outcome=outcome,
            evidence={"result_hash": link.result_hash, "mcp_server_id": link.mcp_server_id,
                "device_id": (link.arguments or {}).get("device_id")}))
        if outcome == "failed":
            rev = await revision(db, item, revision_number)
            await enqueue(db, link.owner_user_id, "reconcile_experience",
                f"reconcile:{memory_id}:{command_id}",
                {"memory_id": memory_id, "link_id": link.id,
                    "scope_matched": scope_matches(rev.applicability_json if rev else None, link)})


def scope_matches(applicability, link) -> bool:
    """适用条件与失败动作一致才算明确反例；范围不一致只记范围问题（spec 7.6）。"""
    scope = applicability or {}
    expected_server = scope.get("mcp_server_id")
    if expected_server and expected_server != link.mcp_server_id:
        return False
    device_ids = scope.get("device_ids")
    if device_ids and (link.arguments or {}).get("device_id") not in device_ids:
        return False
    return True


async def save_result(link_id, output):
    async with SessionFactory() as db:
        link = await db.get(MemoryActionLink, link_id)
        run = await db.get(AgentRun, link.run_id)
        data = output.get("data") or {}
        command = data.get("command") or (data if data.get("command_id") and not data.get("proposal_id") else {})
        proposal = data.get("proposal") or (data if data.get("proposal_id") else {})
        if command.get("command_id"):
            link.command_id, link.reservation = command["command_id"], "used"
        if proposal.get("proposal_id"):
            link.proposal_id = proposal["proposal_id"]
        if output.get("ok") is not True:
            # Only definitive validation rejection releases a slot; transport errors retain it.
            code = (output.get("error") or {}).get("code")
            if code in {"UNKNOWN_ACTION", "ACTION_REQUIRES_APPROVAL", "ACTION_NOT_HIGH_RISK", "DIAGNOSIS_NOT_FOUND", "DIAGNOSIS_DEVICE_MISMATCH", "INVALID_PARAMETERS"}:
                link.reservation = "released"
                link.outcome = "not_executed"
        else:
            outcome = normalize_result(data, expired=utc_now() > link.tracking_until.replace(tzinfo=utc_now().tzinfo))
            if outcome == "not_executed":
                link.reservation = "released"
            if link.result_hash != digest(data):
                link.result, link.result_hash, link.outcome = data, digest(data), outcome
                if run:
                    await record_tool(db, run, link.mcp_server_id, "get_action_result", {}, output)
                    if link.command_id and link.applied_memory_ids and outcome in {"succeeded", "failed", "inconclusive"}:
                        await record_feedback(db, link, link.command_id, outcome)
                    needs_followup = outcome == "failed" and run.status != RunStatus.RUNNING
                    db.add(RunEvent(run_id=run.id, event_type="remediation.result_updated", data={
                        "command_id": link.command_id, "outcome": outcome, "needs_followup": needs_followup}))
                    if needs_followup:
                        run_links = (await db.scalars(select(MemoryActionLink).where(MemoryActionLink.run_id == run.id))).all()
                        db.add(loop_stopped_event(run, run_links, "run_finished", command_id=link.command_id))
        await db.commit()
        return link


async def track(job):
    from app.services.mcp_catalog import invoke_remote_tool
    async with SessionFactory() as db:
        link = await db.get(MemoryActionLink, job.payload["link_id"])
        if not link or link.reservation == "released":
            return
        server = await db.get(MCPServer, link.mcp_server_id)
        if not server or not server.enabled or server.deleted_at:
            raise RuntimeError("MEMORY_SOURCE_UNAVAILABLE")
    if link.command_id:
        tool, arguments = "get_action_result", {"command_id": link.command_id}
    elif link.proposal_id:
        tool, arguments = "get_action_result", {"proposal_id": link.proposal_id}
    else:
        tool, arguments = "get_action_by_correlation", {"correlation_key": link.correlation_key}
    output = await invoke_remote_tool(server, get_settings(), tool, arguments, read_only=True)
    if output.get("ok") is not True:
        raise RuntimeError("MEMORY_ACTION_QUERY_FAILED")
    link = await save_result(link.id, output)
    age = utc_now() - link.created_at.replace(tzinfo=utc_now().tzinfo)
    if link.outcome in {"pending", "inconclusive"} and age < timedelta(days=7):
        delay = 86400 if age > timedelta(days=1) else get_settings().memory_action_poll_seconds
        async with SessionFactory() as db:
            next_job = await enqueue(db, link.owner_user_id, "track_action", f"track:{link.id}:{job.id}", {"link_id": link.id})
            next_job.next_run_at = utc_now() + timedelta(seconds=delay)
            await db.commit()


async def check_trace(db, owner, server_id, diagnosis_id):
    source = await db.scalar(select(MemorySource).where(MemorySource.owner_user_id == owner,
        MemorySource.mcp_server_id == server_id, MemorySource.diagnosis_id == diagnosis_id))
    if not source or source.access_state == "forgotten":
        fail("DIAGNOSIS_NOT_FOUND", 404)
