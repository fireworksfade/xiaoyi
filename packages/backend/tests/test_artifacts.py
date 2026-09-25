import asyncio
import json
import uuid
from datetime import timedelta
from pathlib import Path

from sqlalchemy import func, select

from app.agent.runtime import RuntimeEvent
from app.agent.tool_semantics import ToolSemanticAdapter
from app.config import get_settings
from app.db import SessionFactory
from app.models import (
    AgentRun,
    Conversation,
    ConversationContextSnapshot,
    Message,
    RunArtifact,
    RunStatus,
    User,
    UserRole,
    utc_now,
)
from app.services.artifacts import LocalArtifactStore, extract_critical_fields, sanitize_artifact
from app.services.context_compactor import (
    compact_model_input,
    save_context_snapshot,
    summarize_history,
)
from app.services.retention import cleanup_run_artifacts
from app.services.run_event_buffer import RunEventBuffer
from app.services.runs import _stream_with_context_recovery
from app.services.workflows import WorkflowError


async def _seed_run() -> str:
    async with SessionFactory() as db:
        user = User(
            username=f"artifact-{uuid.uuid4().hex[:10]}", password_hash="x", role=UserRole.ADMIN
        )
        db.add(user)
        await db.flush()
        conversation = Conversation(user_id=user.id, title="归档测试")
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


def test_sanitizer_redacts_nested_credentials() -> None:
    value = sanitize_artifact(
        {"Authorization": "Bearer abc.def", "nested": {"api_key": "secret"}, "text": "Bearer xyz"}
    )
    assert value["Authorization"] == "[REDACTED]"
    assert value["nested"]["api_key"] == "[REDACTED]"
    assert value["text"] == "Bearer [REDACTED]"
    assert sanitize_artifact({"X-API-Key": "secret"})["X-API-Key"] == "[REDACTED]"
    assert sanitize_artifact("Cookie: session=abc") == "Cookie: [REDACTED]"


def test_archived_summary_retains_workflow_evidence() -> None:
    output = {
        "ok": True,
        "data": {
            "device_id": "ESP32_05",
            "diagnosis_id": "DIA_TEST",
            "fault_type": "mqtt_connection",
            "confidence": 0.91,
            "details": "x" * 1000,
        },
    }
    critical = extract_critical_fields(output)
    events = ToolSemanticAdapter.adapt_tool_result(
        "run",
        {
            "tool_name": "diagnose_fault",
            "call_id": "call",
            "output": {"ok": True, "data": critical, "truncated": True},
        },
    )
    assert events[0].payload["diagnosis_id"] == "DIA_TEST"
    assert events[0].payload["confidence"] == 0.91


def test_archived_action_result_keeps_command_status_distinct_from_proposal() -> None:
    output = {
        "ok": True,
        "data": {
            "proposal": {"status": "approved"},
            "command": {
                "command_id": "CMD_TEST",
                "device_id": "ESP32_05",
                "diagnosis_id": "DIA_TEST",
                "status": "failed",
                "verify_status": "pending",
                "case_status": "pending",
            },
            "large_logs": "x" * 1000,
        },
    }
    critical = extract_critical_fields(output)
    assert critical["command_status"] == "failed"
    events = ToolSemanticAdapter.adapt_tool_result(
        "run",
        {
            "tool_name": "get_action_result",
            "call_id": "call",
            "output": {"ok": True, "data": critical, "truncated": True},
        },
    )
    assert events[0].payload["command_status"] == "failed"


def test_large_output_is_archived_before_summary(tmp_path: Path) -> None:
    run_id = asyncio.run(_seed_run())
    store = LocalArtifactStore(tmp_path)
    buffer = RunEventBuffer(run_id, tool_output_max_bytes=128, artifact_store=store)
    buffer.append(
        RuntimeEvent(
            "tool.finished",
            {"tool_name": "large", "output": {"token": "Bearer secret", "rows": ["x" * 500]}},
        )
    )
    asyncio.run(buffer.flush())

    async def load() -> RunArtifact:
        async with SessionFactory() as db:
            artifact = await db.scalar(select(RunArtifact).where(RunArtifact.run_id == run_id))
            assert artifact is not None
            return artifact

    artifact = asyncio.run(load())
    content = json.loads(Path(artifact.storage_uri).read_text(encoding="utf-8"))
    assert content["token"] == "[REDACTED]"
    assert artifact.size_bytes > 128


def test_small_tool_output_is_redacted_in_run_event(tmp_path: Path) -> None:
    run_id = asyncio.run(_seed_run())
    buffer = RunEventBuffer(
        run_id,
        tool_output_max_bytes=1024,
        artifact_store=LocalArtifactStore(tmp_path),
    )
    buffer.append(RuntimeEvent("tool.finished", {"output": {"Authorization": "Bearer secret"}}))
    asyncio.run(buffer.flush())

    async def load_output() -> dict:
        from app.models import RunEvent

        async with SessionFactory() as db:
            event = await db.scalar(
                select(RunEvent).where(
                    RunEvent.run_id == run_id, RunEvent.event_type == "tool.finished"
                )
            )
            assert event is not None
            return event.data["output"]

    assert asyncio.run(load_output()) == {"Authorization": "[REDACTED]"}


def test_model_input_compaction_preserves_call_pairs_and_artifact_reference() -> None:
    old_output = json.dumps(
        {
            "artifact_id": "artifact-1",
            "original_bytes": 10000,
            "sha256": "a" * 64,
            "critical_fields": {"diagnosis_id": "DIA_TEST", "device_id": "ESP32_05"},
            "summary": "x" * 1000,
        }
    )
    items = [
        {"role": "user", "content": "检查设备"},
        {"type": "function_call", "call_id": "old", "name": "diagnose_fault"},
        {"type": "function_call_output", "call_id": "old", "output": old_output},
        {"type": "function_call", "call_id": "new", "name": "get_action_result"},
        {"type": "function_call_output", "call_id": "new", "output": "latest evidence"},
    ]
    compacted = compact_model_input(
        items,
        workflow_snapshot={"diagnosis_id": "DIA_TEST", "current_step": "verify"},
        keep_recent_tool_results=1,
        max_tool_output_chars=256,
    )
    assert compacted.compacted_outputs == 1
    assert items[2]["output"] == old_output
    assert compacted.items[0]["role"] == "system"
    assert compacted.items[1] == items[0]
    assert compacted.items[2] == items[1]
    summary = json.loads(compacted.items[3]["output"])
    assert summary["artifact_id"] == "artifact-1"
    assert summary["critical_fields"]["diagnosis_id"] == "DIA_TEST"
    assert compacted.items[-1] == items[-1]


def test_prompt_too_long_retries_once_after_archiving_transcript(tmp_path: Path) -> None:
    run_id = asyncio.run(_seed_run())
    settings = get_settings().model_copy(update={"run_artifact_root": str(tmp_path)})

    class OversizedRuntime:
        workflow_snapshot = None
        calls = 0

        async def stream(self, messages, _servers):
            self.calls += 1
            if len(messages) > 1:
                raise RuntimeError("maximum context length exceeded")
            yield RuntimeEvent("answer.final", {"content": "ready"})

    runtime = OversizedRuntime()
    runtime.run_id = run_id
    messages = [
        {"role": "user", "content": "x" * 15_000},
        {"role": "assistant", "content": "old answer"},
        {"role": "user", "content": "current request"},
    ]

    async def collect() -> list[RuntimeEvent]:
        return [
            event
            async for event in _stream_with_context_recovery(
                run_id, runtime, messages, [], settings, allow_retry=True
            )
        ]

    events = asyncio.run(collect())
    assert runtime.calls == 2
    assert [event.event_type for event in events] == ["context.compacted", "answer.final"]
    artifact_id = events[0].data["artifact_id"]

    async def load() -> RunArtifact:
        async with SessionFactory() as db:
            artifact = await db.get(RunArtifact, artifact_id)
            assert artifact is not None
            return artifact

    artifact = asyncio.run(load())
    assert json.loads(Path(artifact.storage_uri).read_text(encoding="utf-8"))["messages"] == (
        messages
    )


def test_prompt_too_long_after_tool_start_never_replays_tool(tmp_path: Path) -> None:
    run_id = asyncio.run(_seed_run())
    settings = get_settings().model_copy(update={"run_artifact_root": str(tmp_path)})

    class ToolStartedRuntime:
        workflow_snapshot = None
        calls = 0

        async def stream(self, _messages, _servers):
            self.calls += 1
            yield RuntimeEvent("tool.started", {"tool_name": "execute_device_action"})
            raise RuntimeError("prompt_too_long")

    runtime = ToolStartedRuntime()
    runtime.run_id = run_id

    async def collect() -> None:
        async for _event in _stream_with_context_recovery(
            run_id, runtime, [{"role": "user", "content": "repair"}], [], settings, allow_retry=True
        ):
            pass

    try:
        asyncio.run(collect())
    except WorkflowError as exc:
        assert exc.code == "CONTEXT_COMPACTION_EXHAUSTED"
    else:
        raise AssertionError("tool execution was replayed")
    assert runtime.calls == 1


def test_history_snapshot_is_monotonic_and_keeps_important_ids(tmp_path: Path) -> None:
    run_id = asyncio.run(_seed_run())
    store = LocalArtifactStore(tmp_path)
    transcript = [
        {"role": "user", "content": "检查 DIA_20260923_AABBCCDD"},
        {"role": "assistant", "content": "命令 CMD_20260923_AABBCCDD 已执行"},
    ]
    summary = summarize_history(
        transcript, current_goal="继续检查", workflow_snapshot={"command_id": "CMD_1"}
    )
    assert "DIA_20260923_AABBCCDD" in summary["important_ids"]
    assert "CMD_1" in summary["important_ids"]

    async def persist_twice() -> tuple[str, str]:
        async with SessionFactory() as db:
            run = await db.get(AgentRun, run_id)
            assert run is not None
            first = await save_context_snapshot(
                db,
                store,
                run_id=run_id,
                conversation_id=run.conversation_id,
                covers_through_message_id=run.user_message_id,
                summary=summary,
                source_transcript=transcript,
                estimated_tokens=100,
            )
            await db.commit()
            old_id = first.id
            extra = Message(
                conversation_id=run.conversation_id,
                role="assistant",
                content="later",
            )
            db.add(extra)
            await db.commit()
            newer = await save_context_snapshot(
                db,
                store,
                run_id=run_id,
                conversation_id=run.conversation_id,
                covers_through_message_id=extra.id,
                summary=summary,
                source_transcript=transcript,
                estimated_tokens=120,
            )
            await db.commit()
            assert newer.id != old_id
            stale = await save_context_snapshot(
                db,
                store,
                run_id=run_id,
                conversation_id=run.conversation_id,
                covers_through_message_id=run.user_message_id,
                summary=summary,
                source_transcript=transcript,
                estimated_tokens=100,
            )
            count = await db.scalar(
                select(func.count())
                .select_from(ConversationContextSnapshot)
                .where(ConversationContextSnapshot.conversation_id == run.conversation_id)
            )
            assert count == 1
            return newer.id, stale.id

    newer_id, stale_id = asyncio.run(persist_twice())
    assert stale_id == newer_id


def test_retention_preserves_active_snapshot_source(tmp_path: Path) -> None:
    run_id = asyncio.run(_seed_run())
    store = LocalArtifactStore(tmp_path)

    async def check() -> None:
        async with SessionFactory() as db:
            run = await db.get(AgentRun, run_id)
            assert run is not None
            snapshot = await save_context_snapshot(
                db,
                store,
                run_id=run_id,
                conversation_id=run.conversation_id,
                covers_through_message_id=run.user_message_id,
                summary={"current_goal": "test"},
                source_transcript={"messages": []},
                estimated_tokens=1,
            )
            await db.commit()
            artifact = await db.get(RunArtifact, snapshot.source_artifact_id)
            assert artifact is not None
            artifact.expires_at = utc_now() - timedelta(hours=1)
            await db.commit()
            report = await cleanup_run_artifacts(
                db, root=str(tmp_path), batch_size=10, delete_enabled=True
            )
            assert report["protected"] == 1
            assert report["deleted"] == 0
            assert await db.get(RunArtifact, artifact.id) is not None
            assert Path(artifact.storage_uri).exists()

    asyncio.run(check())
