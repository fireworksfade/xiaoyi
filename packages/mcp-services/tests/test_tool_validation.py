import json
import sqlite3

import pytest
from mcp.client import Client

from iot_diagnosis.repository import DiagnosisRepository
from iot_mcp import server


@pytest.mark.asyncio
@pytest.mark.parametrize("name,arguments", [
    ("list_devices", {"limit": -1}),
    ("list_devices", {"offset": -1}),
    ("get_device_logs", {"device_id": "D1", "limit": 1000}),
    ("get_device_logs", {"device_id": "D1", "level": "INVALID"}),
    ("search_knowledge", {"query": "MQTT", "top_k": 0}),
    ("search_knowledge", {"query": "", "strategy": "hybrid"}),
    ("search_knowledge", {"query": "MQTT", "strategy": "invalid"}),
    ("search_knowledge", {"query": "MQTT", "sources": ["unknown"]}),
    ("list_knowledge_documents", {"limit": 201}),
    ("execute_device_action", {"device_id": "D1", "action": "unknown", "reason": "test",
                                "diagnosis_id": "DIA_20260922_DEADBEEF"}),
])
async def test_mcp_rejects_bad_arguments(name, arguments):
    async with Client(server.mcp) as client:
        response = await client.call_tool(name, arguments)
        assert response.is_error


def test_diagnosis_input_error_is_not_a_retryable_model_failure(monkeypatch):
    def invalid(*args, **kwargs):
        raise ValueError("MEMORY_CONTEXT_TOO_LARGE")

    monkeypatch.setattr(server, "diagnose", invalid)
    result = server.diagnose_fault("D1", "diagnose")
    assert result["error"]["code"] == "INVALID_REQUEST"
    assert result["error"]["retryable"] is False


@pytest.mark.parametrize("exception,code", [
    (RuntimeError("private internal detail"), "DIAGNOSIS_FAILED"),
    (sqlite3.OperationalError("database locked"), "DATABASE_ERROR"),
    (server.DiagnosisStageError("RETRIEVAL_FAILED"), "RETRIEVAL_FAILED"),
])
def test_diagnosis_failure_is_queryable(tmp_path, monkeypatch, exception, code):
    repository = DiagnosisRepository(str(tmp_path / "diagnosis.db"))
    monkeypatch.setattr(server, "diagnosis_repository", repository)

    def failed(*args, **kwargs):
        raise exception

    monkeypatch.setattr(server, "diagnose", failed)
    result = server.diagnose_fault("D1", "diagnose")
    assert result["error"]["code"] == code
    diagnosis_id = result["error"]["diagnosis_id"]
    trace = server.get_diagnosis_trace(diagnosis_id)
    assert trace["ok"]
    assert "private internal detail" not in json.dumps(result)
    assert repository.list_diagnoses(status="failed")["total"] == 1


def test_sql_pagination_filters_before_slicing_and_handles_missing_state(tmp_path):
    repository = DiagnosisRepository(str(tmp_path / "diagnosis.db"), offline_after_seconds=30)
    repository.apply_status("A", {"online": True, "device_type": "TEST"})
    repository.upsert_device_metadata("B", {"name": "no state", "device_type": "TEST"})
    repository.apply_status("C", {"online": False, "device_type": "TEST"})
    result = repository.list_devices(device_type="TEST", online=False, limit=1, offset=1)
    assert result["total"] == 2 and result["items"][0]["device_id"] == "C"
    result = repository.list_devices(device_type="TEST", online=True, limit=1)
    assert result["total"] == 1 and result["items"][0]["device_id"] == "A"
    with pytest.raises(ValueError):
        repository.get_device_logs("A", -1)
