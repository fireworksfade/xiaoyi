"""Capture only verified tool facts, never the assistant's success claims."""
from sqlalchemy import select

from app.config import get_settings
from app.memory.models import Memory, MemorySource
from app.memory.schemas import MemoryWrite
from app.memory.service import create, digest, edit, enqueue, index_change, tombstoned, working_fact
from app.services.artifacts import sanitize_artifact


def normalize_result(data, *, expired=False):
    command = data.get("command") or (data if data.get("command_id") else {})
    proposal = data.get("proposal") or (data if data.get("proposal_id") and not command else {})
    status, verify = command.get("status"), command.get("verify_status")
    if status == "failed" and verify == "succeeded":
        return "inconclusive"
    if verify == "succeeded":
        return "succeeded"
    if verify == "failed" or status == "failed":
        return "failed"
    if not command and proposal.get("status") in {"rejected", "expired"}:
        return "not_executed"
    if status in {"timed_out", "timeout"} or expired:
        return "inconclusive"
    return "pending"


async def record_tool(db, run, server_id, tool_name, arguments, output):
    if not get_settings().memory_enabled or not get_settings().memory_auto_capture:
        return None
    if output.get("ok") is not True or tool_name not in {"diagnose_fault", "get_action_result", "execute_device_action", "create_remediation_proposal"}:
        return None
    data = output.get("data")
    if not isinstance(data, dict):
        return None
    command = data.get("command") or (data if data.get("command_id") else {})
    proposal = data.get("proposal") or (data if data.get("proposal_id") and not command else {})
    diagnosis_id = data.get("diagnosis_id") or command.get("diagnosis_id") or proposal.get("diagnosis_id")
    source_id = command.get("command_id") or proposal.get("proposal_id") or diagnosis_id
    if not source_id:
        return None
    if await tombstoned(db, run.user_id, "conversation", run.conversation_id):
        return None
    key = f"{server_id}:{source_id}"
    source = await db.scalar(select(MemorySource).where(MemorySource.owner_user_id == run.user_id, MemorySource.source_key == key))
    excerpt = sanitize_artifact(data)
    # Keep bounded evidence fields; do not replicate trace contexts or raw transcripts.
    excerpt = {k: v for k, v in excerpt.items() if k in {
        "diagnosis_id", "device_id", "fault_type", "fault_name", "cause", "root_cause",
        "solutions", "evidence", "confidence", "command", "proposal", "command_id",
        "proposal_id", "status", "verify_status", "ack", "action", "parameters", "reason",
        "diagnosis", "unresolved_items", "delivery_status",
    }}
    if not source:
        source = MemorySource(owner_user_id=run.user_id, source_key=key, source_type="tool",
            source_id=source_id, run_id=run.id, conversation_id=run.conversation_id,
            mcp_server_id=server_id, diagnosis_id=diagnosis_id, command_id=command.get("command_id"),
            excerpt=excerpt, content_hash=digest(excerpt))
        db.add(source)
    else:
        source.excerpt, source.content_hash = excerpt, digest(excerpt)
    await db.flush()
    await working_fact(db, run, key, {"source_id": source.id, "tool": tool_name, "evidence": excerpt})
    await enqueue(db, run.user_id, "capture_episode", f"source:{source.id}:{source.content_hash}", {"source_id": source.id})
    return source


async def capture_source(db, source):
    if source.access_state == "forgotten" or await tombstoned(db, source.owner_user_id, "conversation", source.conversation_id or ""):
        return None
    data = source.excerpt
    command = data.get("command") or (data if data.get("command_id") else {})
    has_action = bool(command or data.get("proposal") or data.get("proposal_id"))
    # A diagnostic ID without any finding is not a useful episode.
    if not has_action and not any(data.get(k) for k in ("fault_name", "cause", "root_cause", "diagnosis", "evidence")):
        return None
    outcome = normalize_result(data) if has_action else "inconclusive"
    content = {"observations": [data], "hypotheses": [], "actions": [command] if command else [],
        "outcome": outcome, "unresolved_items": [] if outcome == "succeeded" else ["根因及后续结果需核实"],
        "root_cause_status": "unknown"}
    device = command.get("device_id") or data.get("device_id")
    payload = MemoryWrite(kind="episodic", title=f"{device or '设备'} · {data.get('fault_name') or command.get('action') or '诊断经历'}"[:160],
        summary=f"{data.get('fault_name') or command.get('action') or '诊断'}；结果：{outcome}。本次结果不确认根因。",
        content=content, applicability={"mcp_server_id": source.mcp_server_id, "device_ids": [device] if device else []})
    key = source.source_key
    item = await db.scalar(select(Memory).where(Memory.owner_user_id == source.owner_user_id, Memory.event_key == key))
    if item and item.status == "deleted":
        return None
    if item:
        from app.memory.service import revision
        rev = await revision(db, item)
        if rev.content_json == content:
            return item
        payload.expected_revision = item.current_revision
        item = await edit(db, source.owner_user_id, item.id, payload)
    else:
        item = await create(db, source.owner_user_id, payload, source_type="task", event_key=key, source=source)
    if item:
        # Rule-reviewed facts may be active; pending episodes are still excluded at retrieval.
        item.status, item.active_revision = "active", item.current_revision
        await index_change(db, item)
        from app.observability.metrics import MEMORY_EVENTS
        MEMORY_EVENTS.labels(event="episode_recorded").inc()
        if outcome != "pending" and get_settings().memory_auto_propose_experience:
            await enqueue(db, source.owner_user_id, "propose_experience", f"extract:{item.id}:{item.current_revision}",
                {"memory_id": item.id, "revision": item.current_revision})
    return item


async def capture_job(db, job):
    if job.payload.get("source_id"):
        source = await db.get(MemorySource, job.payload["source_id"])
        if source and source.owner_user_id == job.owner_user_id:
            await capture_source(db, source)
    else:
        sources = (await db.scalars(select(MemorySource).where(MemorySource.owner_user_id == job.owner_user_id,
            MemorySource.run_id == job.payload.get("run_id")))).all()
        for source in sources:
            await capture_source(db, source)
