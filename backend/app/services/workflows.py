"""Persisted, fixed IoT remediation workflow state machine."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.tool_semantics import SemanticEvent
from app.models import (
    AgentRun,
    OperationWorkflow,
    OperationWorkflowEvent,
    OperationWorkflowStep,
    RunEvent,
    new_id,
    utc_now,
)

STEP_KEYS = ("diagnose", "select_action", "approve", "remediate", "verify", "archive_case")
TERMINAL = {"completed", "failed", "cancelled"}


class WorkflowError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def workflow_view(
    workflow: OperationWorkflow, steps: list[OperationWorkflowStep]
) -> dict[str, Any]:
    return {
        "id": workflow.id,
        "agent_run_id": workflow.agent_run_id,
        "workflow_type": workflow.workflow_type,
        "workflow_version": workflow.workflow_version,
        "goal": workflow.goal,
        "status": workflow.status,
        "outcome": workflow.outcome,
        "current_step": workflow.current_step,
        "device_id": workflow.device_id,
        "diagnosis_id": workflow.diagnosis_id,
        "proposal_id": workflow.proposal_id,
        "command_id": workflow.command_id,
        "case_id": workflow.case_id,
        "state": workflow.state_json or {},
        "lock_version": workflow.lock_version,
        "created_at": workflow.created_at.isoformat(),
        "updated_at": workflow.updated_at.isoformat(),
        "finished_at": workflow.finished_at.isoformat() if workflow.finished_at else None,
        "steps": [
            {
                "step_key": step.step_key,
                "sequence": step.sequence,
                "status": step.status,
                "attempt_count": step.attempt_count,
                "evidence": step.evidence_json or {},
                "error_code": step.error_code,
                "error_message": step.error_message,
                "started_at": step.started_at.isoformat() if step.started_at else None,
                "finished_at": step.finished_at.isoformat() if step.finished_at else None,
            }
            for step in sorted(steps, key=lambda item: item.sequence)
        ],
    }


async def get_workflow_for_run(
    db: AsyncSession, run_id: str
) -> tuple[OperationWorkflow | None, list[OperationWorkflowStep]]:
    workflow = await db.scalar(
        select(OperationWorkflow).where(OperationWorkflow.agent_run_id == run_id)
    )
    if workflow is None:
        return None, []
    steps = list(
        (
            await db.scalars(
                select(OperationWorkflowStep)
                .where(OperationWorkflowStep.workflow_id == workflow.id)
                .order_by(OperationWorkflowStep.sequence)
            )
        ).all()
    )
    return workflow, steps


def _set_once(workflow: OperationWorkflow, field: str, value: str | None) -> None:
    if value is None:
        return
    current = getattr(workflow, field)
    if current is not None and current != value:
        workflow.state_json = {
            **(workflow.state_json or {}),
            "conflict": {"field": field, "expected": current, "actual": value},
        }
        raise WorkflowError("WORKFLOW_STATE_CONFLICT", f"{field} cannot be overwritten")
    setattr(workflow, field, value)


def _ensure_device(workflow: OperationWorkflow, device_id: str | None) -> None:
    if device_id is None:
        return
    if workflow.device_id is not None and workflow.device_id != device_id:
        raise WorkflowError(
            "WORKFLOW_MULTI_DEVICE_UNSUPPORTED", "one workflow cannot operate multiple devices"
        )
    workflow.device_id = device_id


def _step(steps: list[OperationWorkflowStep], key: str) -> OperationWorkflowStep:
    return next(item for item in steps if item.step_key == key)


def _complete(step: OperationWorkflowStep, evidence: dict[str, Any]) -> None:
    now = utc_now()
    if step.started_at is None:
        step.started_at = now
    step.status = "completed"
    step.attempt_count = max(step.attempt_count, 1)
    step.evidence_json = {**(step.evidence_json or {}), **evidence}
    step.finished_at = now


def _skip(step: OperationWorkflowStep, reason: str) -> None:
    step.status = "skipped"
    step.evidence_json = {"reason": reason}
    step.finished_at = utc_now()


async def _new_workflow(
    db: AsyncSession, run: AgentRun
) -> tuple[OperationWorkflow, list[OperationWorkflowStep]]:
    now = utc_now()
    workflow = OperationWorkflow(
        id=new_id(),
        agent_run_id=run.id,
        conversation_id=run.conversation_id,
        user_id=run.user_id,
        created_at=now,
        updated_at=now,
    )
    steps = [
        OperationWorkflowStep(
            id=new_id(),
            workflow_id=workflow.id,
            step_key=key,
            sequence=index,
            status="pending",
            attempt_count=0,
            input_json={},
            evidence_json={},
            updated_at=now,
        )
        for index, key in enumerate(STEP_KEYS, 1)
    ]
    db.add(workflow)
    db.add_all(steps)
    db.add(
        RunEvent(run_id=run.id, event_type="workflow.started", data={"workflow_id": workflow.id})
    )
    return workflow, steps


async def apply_semantic_event(
    db: AsyncSession, run: AgentRun, event: SemanticEvent
) -> OperationWorkflow | None:
    workflow, steps = await get_workflow_for_run(db, run.id)
    if workflow is None:
        if event.event_type != "diagnosis.completed":
            raise WorkflowError("REQUIRED_EVIDENCE_MISSING", "diagnosis must complete first")
        workflow, steps = await _new_workflow(db, run)
    duplicate = await db.scalar(
        select(OperationWorkflowEvent.id).where(OperationWorkflowEvent.event_key == event.event_key)
    )
    if duplicate:
        return workflow
    archive_completion = (
        workflow.status == "completed"
        and workflow.outcome == "remediated_verified_archive_pending"
        and event.event_type == "remediation.verification_updated"
        and event.payload.get("verify_status") == "succeeded"
        and event.payload.get("case_status") == "archived"
        and bool(event.payload.get("case_id"))
    )
    if workflow.status in TERMINAL and not archive_completion:
        raise WorkflowError("WORKFLOW_STATE_CONFLICT", "terminal workflow cannot be advanced")

    payload = event.payload
    _ensure_device(workflow, payload.get("device_id"))
    if payload.get("diagnosis_id"):
        _set_once(workflow, "diagnosis_id", payload["diagnosis_id"])

    if event.event_type == "diagnosis.completed":
        if workflow.goal != "diagnosis" or _step(steps, "diagnose").status == "completed":
            raise WorkflowError("WORKFLOW_STATE_CONFLICT", "diagnosis is already complete")
        _complete(_step(steps, "diagnose"), payload)
        workflow.current_step = "select_action"
    elif event.event_type == "remediation.proposal_created":
        if (
            _step(steps, "diagnose").status != "completed"
            or workflow.status != "active"
            or workflow.command_id is not None
            or workflow.proposal_id is not None
        ):
            raise WorkflowError("WORKFLOW_STATE_CONFLICT", "proposal cannot be created now")
        workflow.goal = "remediation"
        _set_once(workflow, "proposal_id", payload["proposal_id"])
        _complete(_step(steps, "select_action"), payload)
        approve = _step(steps, "approve")
        approve.status = "waiting"
        approve.started_at = approve.started_at or utc_now()
        workflow.current_step = "approve"
        workflow.status = "waiting_approval"
    elif event.event_type == "remediation.command_started":
        if (
            _step(steps, "diagnose").status != "completed"
            or workflow.status != "active"
            or workflow.command_id is not None
        ):
            raise WorkflowError("WORKFLOW_STATE_CONFLICT", "command cannot be started now")
        workflow.goal = "remediation"
        _set_once(workflow, "command_id", payload["command_id"])
        _complete(_step(steps, "select_action"), payload)
        _skip(_step(steps, "approve"), "low_risk_action")
        remediate = _step(steps, "remediate")
        remediate.status = "running"
        remediate.started_at = remediate.started_at or utc_now()
        remediate.attempt_count += 1
        remediate.evidence_json = payload
        verify = _step(steps, "verify")
        verify.status = "waiting"
        verify.started_at = verify.started_at or utc_now()
        workflow.current_step = "verify"
        workflow.status = "waiting_verification"
    elif event.event_type == "remediation.proposal_decided":
        if workflow.status != "waiting_approval" or workflow.proposal_id is None:
            raise WorkflowError("WORKFLOW_STATE_CONFLICT", "no proposal is awaiting approval")
        _set_once(workflow, "proposal_id", payload["proposal_id"])
        decision = payload["decision"]
        if decision == "approved" and not payload.get("command_id"):
            raise WorkflowError("REQUIRED_EVIDENCE_MISSING", "approved proposal has no command")
        workflow.state_json = {**(workflow.state_json or {}), "proposal_decision": decision}
        _complete(_step(steps, "approve"), payload)
        if decision in {"rejected", "expired"}:
            for key in ("remediate", "verify", "archive_case"):
                _skip(_step(steps, key), f"proposal_{decision}")
            workflow.status = "cancelled"
            workflow.outcome = "cancelled"
            workflow.finished_at = utc_now()
        else:
            _set_once(workflow, "command_id", payload.get("command_id"))
            remediate = _step(steps, "remediate")
            remediate.status = "running"
            remediate.started_at = remediate.started_at or utc_now()
            remediate.attempt_count += 1
            verify = _step(steps, "verify")
            verify.status = "waiting"
            verify.started_at = verify.started_at or utc_now()
            workflow.status = "waiting_verification"
            workflow.current_step = "verify"
    elif event.event_type == "remediation.verification_updated":
        if (
            workflow.goal != "remediation"
            or workflow.command_id is None
            or not (workflow.status == "waiting_verification" or archive_completion)
        ):
            raise WorkflowError("REQUIRED_EVIDENCE_MISSING", "command evidence is missing")
        _set_once(workflow, "command_id", payload["command_id"])
        _set_once(workflow, "case_id", payload.get("case_id"))
        state = {**(workflow.state_json or {}), **payload}
        workflow.state_json = state
        command_status = payload["command_status"]
        verify_status = payload["verify_status"]
        if command_status in {"failed", "rejected", "timeout"} or verify_status == "failed":
            failed_step = _step(steps, "verify" if verify_status == "failed" else "remediate")
            failed_step.status = "failed"
            failed_step.error_code = "REMEDIATION_FAILED"
            failed_step.evidence_json = payload
            failed_step.finished_at = utc_now()
            workflow.status = "failed"
            workflow.outcome = "remediation_failed"
            workflow.finished_at = utc_now()
        elif verify_status == "succeeded":
            _complete(_step(steps, "remediate"), payload)
            _complete(_step(steps, "verify"), payload)
            archive = _step(steps, "archive_case")
            if payload["case_status"] == "archived" and payload.get("case_id"):
                _complete(archive, payload)
                workflow.outcome = "remediated_verified"
            else:
                archive.status = "waiting"
                archive.started_at = archive.started_at or utc_now()
                archive.evidence_json = payload
                workflow.outcome = "remediated_verified_archive_pending"
            workflow.status = "completed"
            workflow.current_step = "archive_case"
            workflow.finished_at = utc_now()
        else:
            workflow.status = "waiting_verification"
            workflow.current_step = "verify"

    workflow.lock_version += 1
    workflow.updated_at = utc_now()
    db.add(
        OperationWorkflowEvent(
            id=new_id(),
            workflow_id=workflow.id,
            event_key=event.event_key,
            event_type=event.event_type,
            payload_json=payload,
        )
    )
    public_type = (
        "workflow.waiting_approval"
        if workflow.status == "waiting_approval"
        else "workflow.waiting_verification"
        if workflow.status == "waiting_verification"
        else "workflow.completed"
        if workflow.status in {"completed", "cancelled"}
        else "workflow.failed"
        if workflow.status == "failed"
        else "workflow.step_updated"
    )
    db.add(
        RunEvent(
            run_id=run.id,
            event_type=public_type,
            data={
                "workflow_id": workflow.id,
                "status": workflow.status,
                "outcome": workflow.outcome,
                "current_step": workflow.current_step,
                "event_type": event.event_type,
            },
        )
    )
    return workflow


async def complete_diagnosis_workflow(
    db: AsyncSession, workflow: OperationWorkflow, steps: list[OperationWorkflowStep]
) -> None:
    if workflow.goal != "diagnosis" or workflow.status in TERMINAL:
        return
    for key in ("select_action", "approve", "remediate", "verify", "archive_case"):
        _skip(_step(steps, key), "diagnosis_goal")
    workflow.status = "completed"
    workflow.outcome = "diagnosed"
    workflow.current_step = "diagnose"
    workflow.finished_at = utc_now()
    workflow.updated_at = utc_now()
    workflow.lock_version += 1
    db.add(
        RunEvent(
            run_id=workflow.agent_run_id,
            event_type="workflow.completed",
            data={
                "workflow_id": workflow.id,
                "status": workflow.status,
                "outcome": workflow.outcome,
            },
        )
    )
