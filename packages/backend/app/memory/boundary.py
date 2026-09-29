"""Backend-owned context at the MCP call boundary; no model-controlled identity."""

import asyncio
import logging
from datetime import timedelta

from sqlalchemy import select, update

from app.config import get_settings
from app.db import SessionFactory
from app.memory.actions import (
    ACTION_TOOLS,
    check_trace,
    deadline_reached,
    loop_stopped_event,
    reserve,
    save_result,
)
from app.memory.capture import record_tool
from app.memory.models import MemoryActionLink, MemorySource
from app.memory.retrieval import search
from app.memory.schemas import MemorySearch
from app.memory.service import digest
from app.models import AgentRun, RunEvent, RunStatus, new_id, utc_now

logger = logging.getLogger("xiaoyi.memory.boundary")


async def capture_safely(db, run, server_id, tool, arguments, output):
    try:
        async with db.begin_nested():
            await record_tool(db, run, server_id, tool, arguments, output)
    except Exception:
        logger.warning("memory capture failed; active run can continue", exc_info=True)


async def recall_safely(db, owner, query):
    try:
        async with db.begin_nested():
            return await search(db, owner, query)
    except Exception:
        logger.warning("memory recall failed; diagnosing from tool evidence", exc_info=True)
        return []


async def prepare(run_id, server_id, tool, arguments):
    arguments = dict(arguments or {})
    adopted = arguments.pop("applied_memory_refs", None)
    for key in ("memory_context", "repair_context", "correlation_key", "owner_user_id"):
        arguments.pop(key, None)
    async with SessionFactory() as db:
        run = await db.get(AgentRun, run_id)
        if not run or run.status != RunStatus.RUNNING:
            from app.memory.service import fail

            fail("RUN_STOPPED", 409)
        if tool == "get_diagnosis_trace":
            await check_trace(db, run.user_id, server_id, arguments.get("diagnosis_id"))
        if tool == "diagnose_fault" and get_settings().memory_enabled:
            arguments["memory_context"] = await recall_safely(
                db,
                run.user_id,
                MemorySearch(
                    query=arguments.get("query", "诊断"),
                    mcp_server_id=server_id,
                    device_id=arguments.get("device_id"),
                    run_id=run_id,
                ),
            )
            await db.commit()  # search 内的 usage 记录需要落库
    link = (
        await reserve(run_id, server_id, tool, arguments, applied_memory_refs=adopted)
        if tool in ACTION_TOOLS
        else None
    )
    if link:
        arguments["correlation_key"] = link.correlation_key
    return arguments, link


async def finish(run_id, server_id, tool, arguments, output, link=None):
    if link:
        await save_result(link.id, output)
    elif tool == "get_action_result":
        async with SessionFactory() as db:
            query = select(MemoryActionLink).where(
                MemoryActionLink.run_id == run_id, MemoryActionLink.mcp_server_id == server_id
            )
            if arguments.get("command_id"):
                query = query.where(MemoryActionLink.command_id == arguments["command_id"])
            else:
                query = query.where(MemoryActionLink.proposal_id == arguments.get("proposal_id"))
            link = await db.scalar(query)
        if link:
            await save_result(link.id, output)
    async with SessionFactory() as db:
        run = await db.get(AgentRun, run_id)
        await capture_safely(db, run, server_id, tool, arguments, output)
        await db.commit()
    return link


async def rediagnose(run_id, server_id, link_id, call):
    """Invoked synchronously by the active runtime. Workers never restart a Run."""
    async with SessionFactory() as db:
        run = await db.get(AgentRun, run_id)
        link = await db.get(MemoryActionLink, link_id)
        if (
            not run
            or run.status != RunStatus.RUNNING
            or not link
            or link.outcome != "failed"
            or link.run_id != run_id
            or link.mcp_server_id != server_id
        ):
            return None
        # 运行期限：超限后不再自动再诊断，结果留给后台跟踪（spec 7.2/7.3）
        if deadline_reached(run):
            db.add(loop_stopped_event(run, [link], "run_deadline", command_id=link.command_id))
            await db.commit()
            return None
        if link.rediagnosis.get("result_hash") == link.result_hash and link.rediagnosis.get(
            "diagnosis_id"
        ):
            return link.rediagnosis
        previous = link.rediagnosis
        if previous.get("lease_until", "") > utc_now().isoformat():
            return None
        token, failure_hash = new_id(), link.result_hash
        lease = {
            "result_hash": failure_hash,
            "lease_token": token,
            "lease_until": (utc_now() + timedelta(minutes=5)).isoformat(),
        }
        claimed = await db.execute(
            update(MemoryActionLink)
            .where(
                MemoryActionLink.id == link_id,
                MemoryActionLink.rediagnosis == previous,
                MemoryActionLink.result_hash == failure_hash,
            )
            .values(rediagnosis=lease)
        )
        if not claimed.rowcount:
            return None
        budget = (run.runtime_state or {}).get("repair_budget") or {}
        links = list(
            (
                await db.scalars(select(MemoryActionLink).where(MemoryActionLink.run_id == run_id))
            ).all()
        )
        used = sum(entry.reservation == "used" for entry in links)
        count = sum(entry.reservation != "released" for entry in links)
        limit = budget.get("limit", get_settings().agent_repair_max_attempts)
        db.add(
            RunEvent(
                run_id=run_id,
                event_type="remediation.rediagnosis_started",
                data={
                    "origin_run_id": run_id,
                    "command_id": link.command_id,
                    "used_attempts": used,
                    "limit": limit,
                },
            )
        )
        await db.commit()

    async def bounded_call(tool, arguments):
        async with SessionFactory() as db:
            run = await db.get(AgentRun, run_id)
            if run.status != RunStatus.RUNNING or deadline_reached(run):
                db.add(
                    loop_stopped_event(
                        run,
                        links,
                        "run_deadline" if deadline_reached(run) else "run_finished",
                        command_id=link.command_id,
                    )
                )
                await db.commit()
                return None
            original = run.runtime_state
            state = dict(original or {})
            checks = state.get("repair_read_calls", 0)
            if checks >= 14:
                db.add(loop_stopped_event(run, links, "tool_budget", command_id=link.command_id))
                await db.commit()
                return None
            state["repair_read_calls"] = checks + 1
            updated = await db.execute(
                update(AgentRun)
                .where(
                    AgentRun.id == run_id,
                    AgentRun.status == RunStatus.RUNNING,
                    AgentRun.runtime_state == original,
                )
                .values(runtime_state=state)
            )
            if not updated.rowcount:
                return None
            await db.commit()
            remaining = (
                (
                    (
                        run.started_at.replace(tzinfo=utc_now().tzinfo)
                        + timedelta(minutes=get_settings().agent_run_max_runtime_minutes)
                    )
                    - utc_now()
                ).total_seconds()
                if run.started_at
                else 60
            )
        return await asyncio.wait_for(
            call(tool, arguments),
            timeout=max(0.001, min(remaining, get_settings().mcp_agent_timeout_seconds)),
        )

    try:
        device, evidence = link.arguments["device_id"], {}
        for tool in ("get_device_status", "get_device_logs"):
            result = await bounded_call(tool, {"device_id": device})
            if result is None:
                return None
            evidence[tool] = result.structured_content
        async with SessionFactory() as db:
            previous_diagnosis = None
            try:
                async with db.begin_nested():
                    prior_source = (
                        await db.scalar(
                            select(MemorySource)
                            .where(
                                MemorySource.owner_user_id == run.user_id,
                                MemorySource.mcp_server_id == server_id,
                                MemorySource.diagnosis_id == link.diagnosis_id,
                                MemorySource.source_id == link.diagnosis_id,
                                MemorySource.command_id.is_(None),
                                MemorySource.access_state != "forgotten",
                            )
                            .order_by(MemorySource.created_at.desc())
                            .limit(1)
                        )
                        if link.diagnosis_id
                        else None
                    )
                    previous_diagnosis = prior_source.excerpt if prior_source else None
            except Exception:
                logger.warning(
                    "previous diagnosis memory unavailable; retaining original action reason",
                    exc_info=True,
                )
            memories = await recall_safely(
                db,
                run.user_id,
                MemorySearch(
                    query=str(link.arguments.get("reason", "修复失败"))[:2000],
                    mcp_server_id=server_id,
                    device_id=device,
                    run_id=run_id,
                ),
            )
            await db.commit()
        context = {
            "previous_diagnosis_id": link.diagnosis_id,
            "previous_diagnosis": previous_diagnosis,
            "previous_hypothesis": link.arguments.get("reason"),
            "previous_action": link.arguments,
            "failed_result": link.result,
            "latest_evidence": evidence,
            "remaining_attempts": max(0, limit - count),
        }
        response = await bounded_call(
            "diagnose_fault",
            {
                "device_id": device,
                "query": "修复已明确失败，请根据最新证据重新诊断，说明假设变化与新方案依据。",
                "memory_context": memories,
                "repair_context": context,
            },
        )
        if response is None:
            return None
        data = (response.structured_content or {}).get("data") or {}
        if not data.get("diagnosis_id"):
            return None
        async with SessionFactory() as db:
            stored = await db.get(MemoryActionLink, link_id)
            run = await db.get(AgentRun, run_id)
            if (
                stored.result_hash != failure_hash
                or stored.rediagnosis.get("lease_token") != token
                or run.status != RunStatus.RUNNING
                or deadline_reached(run)
            ):
                return None
            stored.rediagnosis = {
                "result_hash": failure_hash,
                "diagnosis_id": data["diagnosis_id"],
                "evidence_hash": digest(evidence),
                "new_evidence": bool(data.get("new_evidence")),
                "diagnosis": data,
                "memories": [
                    {"memory_id": m["memory_id"], "revision": m["revision"]} for m in memories
                ],
            }
            await capture_safely(
                db,
                run,
                server_id,
                "diagnose_fault",
                {"device_id": device},
                response.structured_content,
            )
            db.add(
                RunEvent(
                    run_id=run_id,
                    event_type="remediation.rediagnosis_completed",
                    data={
                        "origin_run_id": run_id,
                        "diagnosis_id": data["diagnosis_id"],
                        "command_id": link.command_id,
                        "used_attempts": used,
                        "limit": limit,
                    },
                )
            )
            await db.commit()
            return stored.rediagnosis
    finally:
        # Failed or cancelled diagnosis remains retryable; no failure is consumed early.
        async with SessionFactory() as db:
            stored = await db.get(MemoryActionLink, link_id)
            if stored and stored.rediagnosis.get("lease_token") == token:
                stored.rediagnosis = {}
                await db.commit()
