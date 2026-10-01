"""统一 MCP 的 HTTP 认证与后台保留任务。"""

import asyncio
import os
import subprocess
import sys
from pathlib import Path

import pytest

from iot_diagnosis.repository import DiagnosisRepository
from iot_diagnosis.retention import RetentionService
from iot_mcp import server


def test_configured_bearer_token_protects_mcp_http(tmp_path):
    environment = {
        **os.environ,
        "DIAGNOSIS_DATABASE_PATH": str(tmp_path / "diagnosis.db"),
        "CONTROL_DATABASE_PATH": str(tmp_path / "control.db"),
        "DIAGNOSIS_MCP_BEARER_TOKEN": "cleanup-test-token",
        "DIAGNOSIS_MCP_PUBLIC_URL": "http://127.0.0.1:9000",
        "DIAGNOSIS_QDRANT_URL": "",
        "RETRIEVAL_QDRANT_URL": "",
        "DIAGNOSIS_SYNC_RETRY_SECONDS": "0",
        "DIAGNOSIS_RETENTION_INTERVAL_HOURS": "0",
        "MQTT_ENABLED": "false",
    }
    code = """
from starlette.testclient import TestClient
from iot_mcp.server import mcp

with TestClient(mcp.streamable_http_app(), base_url="http://127.0.0.1:9000") as client:
    payload = {
        "jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {
            "protocolVersion": "2025-11-25", "capabilities": {},
            "clientInfo": {"name": "cleanup-test", "version": "1"},
        },
    }
    headers = {"Accept": "application/json, text/event-stream"}
    assert client.post("/mcp", json=payload, headers=headers).status_code == 401
    assert client.post("/mcp", json=payload, headers={
        **headers, "Authorization": "Bearer invalid-token",
    }).status_code == 401
    authorized = client.post("/mcp", json=payload, headers={
        **headers, "Authorization": "Bearer cleanup-test-token",
    })
    assert authorized.status_code == 200, authorized.text
    assert client.get("/ready").status_code == 200
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=Path(__file__).resolve().parents[1],
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.asyncio
async def test_retention_scheduler_runs_current_interface(tmp_path, monkeypatch):
    monkeypatch.setenv("MQTT_ENABLED", "false")
    monkeypatch.setenv("DIAGNOSIS_SYNC_RETRY_SECONDS", "0")
    monkeypatch.setenv("DIAGNOSIS_RETENTION_INTERVAL_HOURS", "0.000005")
    monkeypatch.setenv("DIAGNOSIS_RETENTION_DELETE_ENABLED", "false")
    monkeypatch.setenv("DIAGNOSIS_QDRANT_URL", "")
    monkeypatch.setenv("RETRIEVAL_QDRANT_URL", "")
    repository = DiagnosisRepository(str(tmp_path / "retention.db"))
    monkeypatch.setattr(server, "diagnosis_repository", repository)
    finished = asyncio.Event()
    loop = asyncio.get_running_loop()
    reports = []
    original_run = RetentionService.run

    def observed_run(service):
        report = original_run(service)
        reports.append((service.path, report))
        loop.call_soon_threadsafe(finished.set)
        return report

    monkeypatch.setattr(RetentionService, "run", observed_run)
    async with server.service_lifespan(server.mcp):
        await asyncio.wait_for(finished.wait(), timeout=2)
    await asyncio.sleep(0)
    assert reports[0][0] == repository.path
    assert reports[0][1].dry_run is True
