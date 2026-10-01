"""Native Harness tool boundary. No backend model or dispatcher is invoked here."""

import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace

from fastapi import HTTPException
from sqlalchemy import select

from app.agent.memory_tools import MEMORY_TOOL_SPECS, handle_memory_tool
from app.config import get_settings
from app.db import SessionFactory
from app.memory.actions import pinned_budget
from app.memory.service import run_finished
from app.models import (
    AgentRun,
    Conversation,
    MCPServer,
    MCPTool,
    Message,
    RunEvent,
    RunStatus,
    utc_now,
)
from app.services.harness import require_enabled
from app.services.mcp_catalog import RETIRED_TOOLS, invoke_remote_tool
from app.services.operations import add_audit_log
from app.services.runs.tool_processor import collect_proposal
from app.services.tool_execution import ToolExecutor, ToolPreparationError

# Approval decisions and administrative writes remain human operations.
NATIVE_POLICIES = {"read_only", "proposal_only"}
HUMAN_TOOLS = {"decide_remediation_proposal", "ingest_knowledge_text", "delete_knowledge_document"}
_locks = {}


@asynccontextmanager
async def run_lock(run_id):
    entry = _locks.setdefault(run_id, [asyncio.Lock(), 0])
    entry[1] += 1
    try:
        async with entry[0]:
            yield
    finally:
        entry[1] -= 1
        if not entry[1]:
            _locks.pop(run_id, None)


async def native_catalog(db):
    rows = (
        await db.execute(
            select(MCPTool, MCPServer)
            .join(MCPServer, MCPServer.id == MCPTool.server_id)
            .where(
                MCPTool.enabled.is_(True),
                MCPServer.enabled.is_(True),
                MCPServer.deleted_at.is_(None),
                MCPServer.connection_status == "connected",
            )
        )
    ).all()
    items = [
        {
            "id": tool.id,
            "server_id": tool.server_id,
            "name": tool.model_alias,
            "original_name": tool.original_name,
            "description": tool.description,
            "parameters": tool.input_schema,
            "risk_policy": tool.risk_policy.value,
        }
        for tool, _ in rows
        if tool.risk_policy.value in NATIVE_POLICIES
        and tool.original_name not in RETIRED_TOOLS | HUMAN_TOOLS
    ]
    if get_settings().memory_enabled:
        items.extend(
            {
                "id": f"memory:{spec['name']}",
                "name": spec["name"],
                "original_name": spec["name"],
                "description": spec["description"],
                "parameters": spec["parameters"],
                "risk_policy": "proposal_only" if spec["name"] == "propose_memory" else "read_only",
            }
            for spec in MEMORY_TOOL_SPECS
        )
    return items


async def owned_native_run(db, user_id, instance, run_id):
    run = await db.get(AgentRun, run_id)
    state = (run.runtime_state or {}) if run else {}
    if (
        not run
        or run.user_id != user_id
        or state.get("harness_instance") != instance
        or not state.get("harness_native")
    ):
        raise HTTPException(404, "NATIVE_RUN_NOT_FOUND")
    return run


async def create_native_run(db, user_id, instance, context_key):
    await require_enabled(db, user_id, instance)
    existing = await db.scalar(
        select(AgentRun).where(
            AgentRun.user_id == user_id,
            AgentRun.runtime_state["harness_instance"].as_string() == instance,
            AgentRun.runtime_state["harness_context"].as_string() == context_key,
        )
    )
    if existing:
        return existing
    conversation = Conversation(user_id=user_id, title="DeepSeek Harness 主对话工具记录")
    db.add(conversation)
    await db.flush()
    message = Message(
        conversation_id=conversation.id,
        role="user",
        content="DeepSeek Harness 原生工具调用",
        metadata_json={"harness_native": True},
    )
    db.add(message)
    await db.flush()
    run = AgentRun(
        user_id=user_id,
        conversation_id=conversation.id,
        user_message_id=message.id,
        status=RunStatus.RUNNING,
        started_at=utc_now(),
        last_progress_at=utc_now(),
        runtime_state={
            "harness_native": True,
            "harness_instance": instance,
            "harness_context": context_key,
            "repair_budget": pinned_budget(),
        },
    )
    db.add(run)
    await db.flush()
    db.add(RunEvent(run_id=run.id, event_type="run.started", data={"executor": "deepseek-harness"}))
    await db.commit()
    return run


async def settle_native_run(run_id, *, failed=False):
    async with SessionFactory() as db:
        run = await db.get(AgentRun, run_id)
        if (
            not run
            or not (run.runtime_state or {}).get("harness_native")
            or run.status != RunStatus.RUNNING
        ):
            return
        proposals = (
            await db.scalars(
                select(RunEvent).where(
                    RunEvent.run_id == run_id, RunEvent.event_type == "remediation.proposal_created"
                )
            )
        ).all()
        message = Message(
            conversation_id=run.conversation_id,
            role="assistant",
            content="工具调用由 Harness 主对话中的 DeepSeek 模型完成。请在主对话查看回答。",
            metadata_json={
                "harness_native": True,
                "remediation_proposals": [e.data["proposal"] for e in proposals],
            },
        )
        db.add(message)
        await db.flush()
        run.final_message_id = message.id
        run.status = RunStatus.FAILED if failed else RunStatus.COMPLETED
        run.finished_at = utc_now()
        run.error_code = "RUN_STOPPED" if failed else None
        db.add(
            RunEvent(
                run_id=run_id,
                event_type="run.failed" if failed else "run.completed",
                data={"message_id": message.id, "executor": "deepseek-harness"},
            )
        )
        await run_finished(db, run)
        await db.commit()


async def execute_native_tool(app, user, instance, run_id, tool_id, arguments, call_id):
    async with run_lock(run_id):
        async with SessionFactory() as db:
            await require_enabled(db, user.id, instance)
            run = await owned_native_run(db, user.id, instance, run_id)
            if run.status != RunStatus.RUNNING:
                raise HTTPException(409, "RUN_STOPPED")
            prior = await db.scalar(
                select(RunEvent).where(
                    RunEvent.run_id == run_id,
                    RunEvent.data["harness_call_id"].as_string() == call_id,
                )
            )
            if prior:
                # Do not replay writes after an ambiguous transport failure.
                raise HTTPException(409, "NATIVE_CALL_ALREADY_SUBMITTED")
            spec = next((s for s in await native_catalog(db) if s["id"] == tool_id), None)
            if not spec:
                raise HTTPException(403, "NATIVE_TOOL_NOT_ALLOWED")
            tool = await db.get(MCPTool, tool_id) if not tool_id.startswith("memory:") else None
            server = await db.get(MCPServer, tool.server_id) if tool else None
            executor = ToolExecutor(run_id, server.id if server else None)
            if server:
                events = (
                    await db.scalars(
                        select(RunEvent)
                        .where(
                            RunEvent.run_id == run_id,
                            RunEvent.event_type.in_(["tool.started", "tool.finished"]),
                        )
                        .order_by(RunEvent.id)
                    )
                ).all()
                executor.restore(events)
                prepared = executor.prepare_arguments(
                    spec["original_name"], arguments, issued_by=f"harness:{user.username}"
                )
            else:
                prepared = arguments
            db.add(
                RunEvent(
                    run_id=run_id,
                    event_type="tool.started",
                    data={
                        "harness_call_id": call_id,
                        "tool_name": spec["original_name"],
                        "server_id": server.id if server else None,
                        "arguments": {"device_id": arguments.get("device_id")},
                    },
                )
            )
            await db.commit()

        task = asyncio.current_task()
        active = getattr(app.state, "harness_native_tasks", None)
        if active is None:
            active = app.state.harness_native_tasks = {}
        active[run_id] = task
        try:
            if server:

                async def call(name, args):
                    async with SessionFactory() as db:
                        await require_enabled(db, user.id, instance)
                    output = await invoke_remote_tool(
                        server,
                        get_settings(),
                        name,
                        args,
                        read_only=spec["risk_policy"] == "read_only",
                    )
                    return SimpleNamespace(structured_content=output)

                async def internal_call(name, args):
                    async with SessionFactory() as db:
                        await require_enabled(db, user.id, instance)
                        allowed = any(
                            s.get("server_id") == server.id
                            and s["original_name"] == name
                            and s["risk_policy"] == "read_only"
                            for s in await native_catalog(db)
                        )
                        if not allowed:
                            raise HTTPException(403, "NATIVE_TOOL_NOT_ALLOWED")
                    output = await invoke_remote_tool(
                        server, get_settings(), name, args, read_only=True
                    )
                    return SimpleNamespace(structured_content=output)

                try:
                    result = (
                        await executor.execute(
                            spec["original_name"], prepared, call, internal_call=internal_call
                        )
                    ).structured_content
                except ToolPreparationError as exc:
                    raise exc.cause from None
            else:
                result = await handle_memory_tool(run_id, spec["original_name"], prepared)
            async with SessionFactory() as db:
                db.add(
                    RunEvent(
                        run_id=run_id,
                        event_type="tool.finished",
                        data={
                            "harness_call_id": call_id,
                            "tool_name": spec["original_name"],
                            "server_id": server.id if server else None,
                            "output": result,
                        },
                    )
                )
                proposal = collect_proposal(
                    {"tool_name": spec["original_name"], "output": result}, []
                )
                if proposal:
                    db.add(
                        RunEvent(
                            run_id=run_id,
                            event_type="remediation.proposal_created",
                            data={"proposal": proposal},
                        )
                    )
                run = await db.get(AgentRun, run_id)
                run.last_progress_at = utc_now()
                add_audit_log(
                    db,
                    actor_type="user",
                    actor_id=user.id,
                    action="harness.native_tool",
                    resource_type="agent_run",
                    resource_id=run_id,
                    request_id=call_id,
                    details={
                        "instance": instance,
                        "tool": spec["original_name"],
                        "server_id": server.id if server else None,
                    },
                )
                await db.commit()
            return {"run_id": run_id, "result": result}
        except asyncio.CancelledError:
            await settle_native_run(run_id, failed=True)
            raise
        finally:
            if active.get(run_id) is task:
                active.pop(run_id, None)
