"""Durable action reservations and read-only result recovery."""
from datetime import timedelta

from sqlalchemy import select, update

from app.config import get_settings
from app.db import SessionFactory
from app.memory.capture import normalize_result, record_tool
from app.memory.models import MemoryActionLink, MemorySource
from app.memory.service import digest, enqueue, fail
from app.models import AgentRun, MCPServer, RunEvent, RunStatus, new_id, utc_now

ACTION_TOOLS = {"execute_device_action", "create_remediation_proposal"}


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
            fail("REPAIR_ATTEMPT_LIMIT_REACHED", 409)
        failed_links = [
            link for link in links
            if link.outcome == "failed" and link.reservation != "released"
            and (link.arguments or {}).get("device_id") == device
        ]
        if failed_links:
            latest = max(failed_links, key=lambda link: link.created_at)
            rd = latest.rediagnosis or {}
            if not rd.get("diagnosis_id") or rd.get("diagnosis_id") != arguments.get("diagnosis_id"):
                fail("REPAIR_REDIAGNOSIS_REQUIRED", 409)
            if not rd.get("new_evidence"):
                fail("REPAIR_NO_NEW_EVIDENCE", 409)
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
            tracking_until=utc_now() + timedelta(days=1))
        db.add(link)
        await db.flush()
        await enqueue(db, run.user_id, "track_action", f"track:{link.id}:initial", {"link_id": link.id})
        await db.commit()
        return link


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
                    db.add(RunEvent(run_id=run.id, event_type="remediation.result_updated", data={
                        "command_id": link.command_id, "outcome": outcome,
                        "needs_followup": outcome == "failed" and run.status != RunStatus.RUNNING}))
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
    if link.outcome in {"pending", "inconclusive"} and age < timedelta(days=8):
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
