"""Backend-owned context at the MCP call boundary; no model-controlled identity."""

from datetime import timedelta

from sqlalchemy import select

from app.config import get_settings
from app.db import SessionFactory
from app.memory.actions import ACTION_TOOLS, check_trace, reserve, save_result
from app.memory.capture import record_tool
from app.memory.models import MemoryActionLink
from app.memory.retrieval import search
from app.memory.schemas import MemorySearch
from app.memory.service import digest
from app.models import AgentRun, RunEvent, RunStatus, utc_now


async def prepare(run_id, server_id, tool, arguments):
    arguments = dict(arguments or {})
    for key in ("memory_context", "repair_context", "correlation_key", "owner_user_id"):
        arguments.pop(key, None)
    async with SessionFactory() as db:
        run = await db.get(AgentRun, run_id)
        if tool == "get_diagnosis_trace":
            await check_trace(db, run.user_id, server_id, arguments.get("diagnosis_id"))
        if tool == "diagnose_fault" and get_settings().memory_enabled:
            arguments["memory_context"] = await search(db, run.user_id, MemorySearch(
                query=arguments.get("query", "诊断"), mcp_server_id=server_id, device_id=arguments.get("device_id"),
                run_id=run_id))
            await db.commit()  # search 内的 usage 记录需要落库
    link = await reserve(run_id, server_id, tool, arguments) if tool in ACTION_TOOLS else None
    if link:
        arguments["correlation_key"] = link.correlation_key
    return arguments, link


async def finish(run_id, server_id, tool, arguments, output, link=None):
    if link:
        await save_result(link.id, output)
    elif tool == "get_action_result":
        async with SessionFactory() as db:
            query = select(MemoryActionLink).where(MemoryActionLink.run_id == run_id, MemoryActionLink.mcp_server_id == server_id)
            if arguments.get("command_id"):
                query = query.where(MemoryActionLink.command_id == arguments["command_id"])
            else:
                query = query.where(MemoryActionLink.proposal_id == arguments.get("proposal_id"))
            link = await db.scalar(query)
        if link:
            await save_result(link.id, output)
    async with SessionFactory() as db:
        run = await db.get(AgentRun, run_id)
        await record_tool(db, run, server_id, tool, arguments, output)
        await db.commit()
    return link


async def rediagnose(run_id, server_id, link_id, call):
    """Invoked synchronously by the active runtime. Workers never restart a Run."""
    async with SessionFactory() as db:
        run = await db.get(AgentRun, run_id)
        link = await db.get(MemoryActionLink, link_id)
        if not run or run.status != RunStatus.RUNNING or link.outcome != "failed":
            return None
        # 运行期限：超限后不再自动再诊断，结果留给后台跟踪（spec 7.2/7.3）
        if run.started_at and (utc_now() - run.started_at.replace(tzinfo=utc_now().tzinfo)) > timedelta(minutes=get_settings().agent_run_max_runtime_minutes):
            from app.memory.actions import loop_stopped_event
            db.add(loop_stopped_event(run, [link], "run_deadline", command_id=link.command_id))
            await db.commit()
            return None
        if link.rediagnosis.get("result_hash") == link.result_hash and link.rediagnosis.get("diagnosis_id"):
            return link.rediagnosis
        db.add(RunEvent(run_id=run_id, event_type="remediation.rediagnosis_started", data={"command_id": link.command_id}))
        await db.commit()
    device = link.arguments["device_id"]
    evidence = {}
    for tool in ("get_device_status", "get_device_logs"):
        async with SessionFactory() as db:
            run = await db.get(AgentRun, run_id)
            if run.status != RunStatus.RUNNING:
                return None
        result = await call(tool, {"device_id": device})
        evidence[tool] = result.structured_content
    async with SessionFactory() as db:
        run = await db.get(AgentRun, run_id)
        if run.status != RunStatus.RUNNING:
            return None
        memories = await search(db, run.user_id, MemorySearch(query=str(link.arguments.get("reason", "修复失败"))[:2000], mcp_server_id=server_id, device_id=device))
        count = len((await db.scalars(select(MemoryActionLink.id).where(MemoryActionLink.run_id == run_id, MemoryActionLink.reservation != "released"))).all())
    context = {"previous_diagnosis_id": link.diagnosis_id, "previous_action": link.arguments,
        "failed_result": link.result, "latest_evidence": evidence,
        "remaining_attempts": max(0, get_settings().agent_repair_max_attempts - count)}
    response = await call("diagnose_fault", {"device_id": device, "query": "修复已明确失败，请根据最新证据重新诊断，说明假设变化与新方案依据。",
        "memory_context": memories, "repair_context": context})
    data = (response.structured_content or {}).get("data") or {}
    if not data.get("diagnosis_id"):
        return None  # not consumed; a subsequent bounded poll may retry diagnosis
    async with SessionFactory() as db:
        link = await db.get(MemoryActionLink, link_id)
        run = await db.get(AgentRun, run_id)
        link.rediagnosis = {"result_hash": link.result_hash, "diagnosis_id": data["diagnosis_id"],
            "evidence_hash": digest(evidence), "new_evidence": bool(data.get("new_evidence")), "diagnosis": data,
            "memories": [{"memory_id": m["memory_id"], "revision": m["revision"]} for m in memories]}
        await record_tool(db, run, server_id, "diagnose_fault", {"device_id": device}, response.structured_content)
        db.add(RunEvent(run_id=run_id, event_type="remediation.rediagnosis_completed", data={
            "diagnosis_id": data["diagnosis_id"], "command_id": link.command_id, "used_attempts": count}))
        await db.commit()
        return link.rediagnosis
