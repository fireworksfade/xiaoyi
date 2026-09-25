from __future__ import annotations

import io
import json
import urllib.error

import pytest
from mcp.client import Client
from starlette.requests import Request

from iot_control import server as control_server
from iot_control.diagnosis_verifier import (
    DiagnosisVerificationError,
    DiagnosisVerifier,
)
from iot_diagnosis import server as diagnosis_server


class FakeResponse:
    def __init__(self, payload: dict):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


@pytest.mark.asyncio
async def test_control_tool_schemas_require_diagnosis_id() -> None:
    async with Client(control_server.mcp) as client:
        response = await client.list_tools()
        tools = response.tools if hasattr(response, "tools") else response["tools"]
        by_name = {tool["name"] if isinstance(tool, dict) else tool.name: tool for tool in tools}
        for name in ("execute_device_action", "create_remediation_proposal"):
            tool = by_name[name]
            schema = tool["inputSchema"] if isinstance(tool, dict) else tool.input_schema
            assert "diagnosis_id" in schema["required"]


def test_verifier_returns_verified_diagnosis(monkeypatch) -> None:
    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda request, timeout: FakeResponse(
            {
                "ok": True,
                "data": {
                    "diagnosis_id": "DIA_20260922_DEADBEEF",
                    "device_id": "ESP32_05",
                    "verified": True,
                },
            }
        ),
    )
    verifier = DiagnosisVerifier("http://diagnosis/internal/diagnoses/verify", "secret")
    result = verifier.verify("DIA_20260922_DEADBEEF", "ESP32_05")
    assert result["verified"] is True


def test_verifier_preserves_diagnosis_error_code(monkeypatch) -> None:
    payload = json.dumps(
        {
            "ok": False,
            "error": {
                "code": "DIAGNOSIS_DEVICE_MISMATCH",
                "message": "诊断记录与目标设备不一致",
            },
        }
    ).encode("utf-8")

    def fail(_request, timeout):
        raise urllib.error.HTTPError("http://diagnosis", 409, "Conflict", {}, io.BytesIO(payload))

    monkeypatch.setattr("urllib.request.urlopen", fail)
    verifier = DiagnosisVerifier("http://diagnosis/internal/diagnoses/verify")
    with pytest.raises(DiagnosisVerificationError) as excinfo:
        verifier.verify("DIA_20260922_DEADBEEF", "ESP32_99")
    assert excinfo.value.code == "DIAGNOSIS_DEVICE_MISMATCH"


def _request(payload: dict, authorization: str = "") -> Request:
    body = json.dumps(payload).encode("utf-8")
    delivered = False

    async def receive():
        nonlocal delivered
        if delivered:
            return {"type": "http.disconnect"}
        delivered = True
        return {"type": "http.request", "body": body, "more_body": False}

    headers = []
    if authorization:
        headers.append((b"authorization", authorization.encode("latin-1")))
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/internal/diagnoses/verify",
            "headers": headers,
        },
        receive,
    )


class FakeDiagnosisRepository:
    def __init__(self, trace: dict | None):
        self.trace = trace

    def get_diagnosis_trace(self, _diagnosis_id: str):
        return self.trace


@pytest.mark.asyncio
async def test_verification_endpoint_checks_device_and_success(monkeypatch) -> None:
    monkeypatch.delenv("DIAGNOSIS_VERIFY_BEARER_TOKEN", raising=False)
    monkeypatch.delenv("DIAGNOSIS_MCP_BEARER_TOKEN", raising=False)
    monkeypatch.setattr(
        diagnosis_server,
        "repository",
        FakeDiagnosisRepository(
            {
                "diagnosis_id": "DIA_20260922_DEADBEEF",
                "device_id": "ESP32_05",
                "observability": {"error": None},
            }
        ),
    )

    response = await diagnosis_server.verify_diagnosis_reference(
        _request(
            {
                "diagnosis_id": "DIA_20260922_DEADBEEF",
                "device_id": "ESP32_05",
            }
        )
    )
    assert response.status_code == 200

    mismatch = await diagnosis_server.verify_diagnosis_reference(
        _request(
            {
                "diagnosis_id": "DIA_20260922_DEADBEEF",
                "device_id": "ESP32_99",
            }
        )
    )
    assert mismatch.status_code == 409

    diagnosis_server.repository.trace["fault_type"] = "realtime_state"
    not_actionable = await diagnosis_server.verify_diagnosis_reference(
        _request(
            {
                "diagnosis_id": "DIA_20260922_DEADBEEF",
                "device_id": "ESP32_05",
            }
        )
    )
    assert not_actionable.status_code == 422


@pytest.mark.asyncio
async def test_verification_endpoint_requires_configured_bearer(monkeypatch) -> None:
    monkeypatch.setenv("DIAGNOSIS_VERIFY_BEARER_TOKEN", "verify-secret")
    response = await diagnosis_server.verify_diagnosis_reference(
        _request(
            {
                "diagnosis_id": "DIA_20260922_DEADBEEF",
                "device_id": "ESP32_05",
            }
        )
    )
    assert response.status_code == 401
