import asyncio
import uuid
from types import MappingProxyType

from app.agent.lifecycle import HookContext, HookObservation, LifecycleHooks
from app.agent.tool_semantics import SemanticEvent, SemanticEventError, ToolSemanticAdapter
from app.db import SessionFactory
from app.models import AgentRun, Conversation, Message, RunStatus, User, UserRole
from app.services.completion_gate import CompletionGate
from app.services.workflows import WorkflowError, apply_semantic_event, get_workflow_for_run


async def _seed_run() -> str:
    async with SessionFactory() as db:
        user = User(username=f"wf-{uuid.uuid4().hex[:8]}", password_hash="x", role=UserRole.ADMIN)
        db.add(user)
        await db.flush()
        conversation = Conversation(user_id=user.id, title="workflow")
        db.add(conversation)
        await db.flush()
        message = Message(conversation_id=conversation.id, role="user", content="diagnose")
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


async def _apply(run_id: str, event: SemanticEvent):
    async with SessionFactory() as db:
        run = await db.get(AgentRun, run_id)
        assert run is not None
        await apply_semantic_event(db, run, event)
        await db.commit()


def test_adapter_rejects_malformed_success() -> None:
    try:
        ToolSemanticAdapter.adapt_tool_result(
            "run", {"tool_name": "diagnose_fault", "output": {"ok": True, "data": {}}}
        )
    except SemanticEventError:
        pass
    else:
        raise AssertionError("malformed evidence advanced the adapter")


def test_adapter_accepts_localized_fault_type() -> None:
    events = ToolSemanticAdapter.adapt_tool_result(
        "run",
        {
            "tool_name": "diagnose_fault",
            "call_id": "call",
            "output": {
                "ok": True,
                "data": {
                    "device_id": "ESP32_05",
                    "diagnosis_id": "DIA_20260923_C494DD06",
                    "fault_type": "MQTT连接故障",
                    "confidence": 0.99,
                },
            },
        },
    )
    assert events[0].payload["fault_type"] == "MQTT连接故障"


def test_workflow_is_idempotent_and_gate_requires_verification() -> None:
    run_id = asyncio.run(_seed_run())
    diagnosis = SemanticEvent(
        "diagnosis.completed",
        f"{run_id}:diagnosis.completed:c1",
        {
            "device_id": "ESP32_05",
            "diagnosis_id": "DIA_TEST",
            "fault_type": "mqtt_connection",
            "confidence": 0.9,
        },
    )
    asyncio.run(_apply(run_id, diagnosis))
    asyncio.run(_apply(run_id, diagnosis))
    command = SemanticEvent(
        "remediation.command_started",
        f"{run_id}:remediation.command_started:c2",
        {
            "device_id": "ESP32_05",
            "diagnosis_id": "DIA_TEST",
            "command_id": "CMD_TEST",
            "action": "reconnect_mqtt",
            "risk_level": "low",
        },
    )
    asyncio.run(_apply(run_id, command))

    async def check_pending() -> None:
        async with SessionFactory() as db:
            workflow, steps = await get_workflow_for_run(db, run_id)
            assert workflow is not None
            decision = CompletionGate(2).evaluate(workflow, steps)
            assert decision.action == "continue"
            assert decision.reason_code == "WAITING_DEVICE_VERIFICATION"

    asyncio.run(check_pending())
    verified = SemanticEvent(
        "remediation.verification_updated",
        f"{run_id}:remediation.verification_updated:c3",
        {
            "device_id": "ESP32_05",
            "diagnosis_id": "DIA_TEST",
            "command_id": "CMD_TEST",
            "command_status": "succeeded",
            "verify_status": "succeeded",
            "case_status": "pending",
            "case_id": None,
        },
    )
    asyncio.run(_apply(run_id, verified))

    async def check_complete() -> None:
        async with SessionFactory() as db:
            workflow, steps = await get_workflow_for_run(db, run_id)
            assert workflow is not None
            decision = CompletionGate(2).evaluate(workflow, steps)
            assert decision.action == "pass_final"
            assert decision.reason_code == "CASE_ARCHIVE_PENDING"

    asyncio.run(check_complete())


def test_multi_device_is_rejected() -> None:
    run_id = asyncio.run(_seed_run())
    asyncio.run(
        _apply(
            run_id,
            SemanticEvent(
                "diagnosis.completed",
                f"{run_id}:diagnosis.completed:c1",
                {
                    "device_id": "ESP32_05",
                    "diagnosis_id": "DIA_TEST",
                    "fault_type": "mqtt_connection",
                    "confidence": 0.9,
                },
            ),
        )
    )
    try:
        asyncio.run(
            _apply(
                run_id,
                SemanticEvent(
                    "remediation.command_started",
                    f"{run_id}:remediation.command_started:c2",
                    {
                        "device_id": "ESP32_06",
                        "diagnosis_id": "DIA_TEST",
                        "command_id": "CMD_TEST",
                        "action": "reconnect_mqtt",
                    },
                ),
            )
        )
    except WorkflowError as exc:
        assert exc.code == "WORKFLOW_MULTI_DEVICE_UNSUPPORTED"
    else:
        raise AssertionError("second device was accepted")


def test_approval_requires_existing_proposal_and_command_evidence() -> None:
    run_id = asyncio.run(_seed_run())
    asyncio.run(
        _apply(
            run_id,
            SemanticEvent(
                "diagnosis.completed",
                f"{run_id}:diagnosis.completed:c1",
                {
                    "device_id": "ESP32_05",
                    "diagnosis_id": "DIA_TEST",
                    "fault_type": "mqtt_connection",
                    "confidence": 0.9,
                },
            ),
        )
    )
    premature = SemanticEvent(
        "remediation.proposal_decided",
        f"{run_id}:remediation.proposal_decided:c2",
        {"proposal_id": "PROP_TEST", "decision": "approved", "command_id": "CMD_TEST"},
    )
    try:
        asyncio.run(_apply(run_id, premature))
    except WorkflowError as exc:
        assert exc.code == "WORKFLOW_STATE_CONFLICT"
    else:
        raise AssertionError("approval skipped proposal creation")

    asyncio.run(
        _apply(
            run_id,
            SemanticEvent(
                "remediation.proposal_created",
                f"{run_id}:remediation.proposal_created:c3",
                {
                    "proposal_id": "PROP_TEST",
                    "device_id": "ESP32_05",
                    "diagnosis_id": "DIA_TEST",
                    "action": "restart_device",
                    "risk_level": "high",
                    "status": "pending",
                },
            ),
        )
    )
    try:
        asyncio.run(
            _apply(
                run_id,
                SemanticEvent(
                    "remediation.proposal_decided",
                    f"{run_id}:remediation.proposal_decided:c4",
                    {"proposal_id": "PROP_TEST", "decision": "approved", "command_id": None},
                ),
            )
        )
    except WorkflowError as exc:
        assert exc.code == "REQUIRED_EVIDENCE_MISSING"
    else:
        raise AssertionError("approval without a command was accepted")

    asyncio.run(_apply(run_id, premature))

    async def check_approved() -> None:
        async with SessionFactory() as db:
            workflow, steps = await get_workflow_for_run(db, run_id)
            assert workflow is not None
            assert workflow.command_id == "CMD_TEST"
            assert workflow.status == "waiting_verification"
            assert next(step for step in steps if step.step_key == "verify").status == "waiting"

    asyncio.run(check_approved())


def test_lifecycle_hooks_preserve_order_and_isolate_timeout() -> None:
    hooks = LifecycleHooks(timeout_ms=5)

    async def first(_context: HookContext) -> HookObservation:
        return HookObservation("first", MappingProxyType({}))

    async def slow(_context: HookContext) -> None:
        await asyncio.sleep(0.05)

    async def last(_context: HookContext) -> HookObservation:
        return HookObservation("last", MappingProxyType({}))

    hooks.register("after_tool", "first", first)
    hooks.register("after_tool", "slow", slow)
    hooks.register("after_tool", "last", last)
    observations = asyncio.run(hooks.emit("after_tool", HookContext(run_id="run")))
    assert [item.name for item in observations] == ["first", "hook.failed", "last"]
    assert observations[1].data["hook"] == "slow"
