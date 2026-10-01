from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.agent.remediation_correlation import RemediationCorrelationError
from app.services import tool_execution
from app.services.tool_execution import ToolExecutor, ToolPreparationError


def diagnosis(number):
    return {"ok": True, "data": {"device_id": "d1", "diagnosis_id": number}}


def test_recovery_keeps_server_scope_and_failed_diagnosis_invalidates_old_association():
    executor = ToolExecutor("run", "server-1")
    executor.restore(
        [
            SimpleNamespace(
                event_type="tool.finished",
                data={
                    "server_id": "server-1",
                    "tool_name": "diagnose_fault",
                    "output": diagnosis("D1"),
                },
            ),
            SimpleNamespace(
                event_type="tool.finished",
                data={
                    "server_id": "server-2",
                    "tool_name": "diagnose_fault",
                    "output": diagnosis("D2"),
                },
            ),
        ]
    )
    assert (
        executor.prepare_arguments("execute_device_action", {"device_id": "d1"})["diagnosis_id"]
        == "D1"
    )
    executor.prepare_arguments("diagnose_fault", {"device_id": "d1"})
    executor.record_result("diagnose_fault", {"ok": False})
    with pytest.raises(RemediationCorrelationError, match="尚无成功诊断"):
        executor.prepare_arguments("execute_device_action", {"device_id": "d1"})


async def test_boundary_rejection_prevents_remote_execution(monkeypatch):
    cause = HTTPException(409, "REPAIR_BUDGET_EXHAUSTED")
    monkeypatch.setattr(tool_execution, "prepare", AsyncMock(side_effect=cause))
    call = AsyncMock()
    with pytest.raises(ToolPreparationError) as error:
        await ToolExecutor("run", "server").execute("execute_device_action", {}, call)
    assert error.value.cause is cause
    call.assert_not_awaited()


async def test_shared_execution_records_rediagnosis_and_preserves_transport_result(monkeypatch):
    link = SimpleNamespace(id="link")
    monkeypatch.setattr(
        tool_execution, "prepare", AsyncMock(return_value=({"trusted": True}, link))
    )
    monkeypatch.setattr(tool_execution, "finish", AsyncMock(return_value=link))
    new_diagnosis = {"diagnosis": diagnosis("D-new")["data"], "new_evidence": True}
    rediagnose = AsyncMock(return_value=new_diagnosis)
    monkeypatch.setattr(tool_execution, "rediagnose", rediagnose)
    result = SimpleNamespace(
        structured_content={"ok": True, "data": {"status": "failed"}}, marker="transport"
    )
    call, internal_call = AsyncMock(return_value=result), AsyncMock()
    executor = ToolExecutor("run", "server")
    assert (
        await executor.execute("execute_device_action", {}, call, internal_call=internal_call)
        is result
    )
    call.assert_awaited_once_with("execute_device_action", {"trusted": True})
    rediagnose.assert_awaited_once_with("run", "server", "link", internal_call)
    assert result.marker == "transport"
    assert result.structured_content["rediagnosis"] == new_diagnosis
    prepared = executor.prepare_arguments(
        "execute_device_action",
        {"device_id": "d1", "issued_by": "forged"},
        issued_by="harness:admin",
    )
    assert prepared["diagnosis_id"] == "D-new"
    assert prepared["issued_by"] == "harness:admin"


async def test_transport_failure_is_not_wrapped_or_retried(monkeypatch):
    monkeypatch.setattr(tool_execution, "prepare", AsyncMock(return_value=({}, None)))
    failure = TimeoutError("transport")
    call = AsyncMock(side_effect=failure)
    with pytest.raises(TimeoutError) as error:
        await ToolExecutor("run", "server").execute("execute_device_action", {}, call)
    assert error.value is failure
    call.assert_awaited_once()
