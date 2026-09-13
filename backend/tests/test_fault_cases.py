import asyncio
import uuid

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import SessionFactory, create_schema
from app.main import app
from app.models import AuditLog, MCPPurpose, MCPServer, MCPTool, ToolRiskPolicy

CASES_PAGE = {
    "items": [
        {
            "fault_id": "FD663EB01",
            "device_id": "ESP32_09",
            "device_type": "ESP32",
            "fault_type": "sensor_anomaly",
            "fault_name": "温度读数持续卡死",
            "symptoms": ["读数恒为 78°C"],
            "cause": "传感器漂移",
            "solution": "执行零点校准",
            "verified_by": "auto-remediation:CMD_1",
            "source": "human_verified",
            "created_at": "2026-09-13T09:14:13+00:00",
        }
    ],
    "total": 1,
    "limit": 50,
    "offset": 0,
}

DELETE_RESULT = {
    "fault_id": "FD663EB01",
    "deleted": True,
    "mysql_saved": True,
    "vector_deleted": True,
    "sync_status": "complete",
}


def seed_iot_server(*, delete_tool_policy: ToolRiskPolicy) -> str:
    async def seed() -> str:
        await create_schema()
        async with SessionFactory() as db:
            server = MCPServer(
                server_key=f"diag-{uuid.uuid4().hex[:8]}",
                name="诊断测试服务",
                url="http://127.0.0.1:9001/mcp",
                purpose=MCPPurpose.IOT,
                enabled=True,
                connection_status="connected",
            )
            db.add(server)
            await db.flush()
            db.add(
                MCPTool(
                    server_id=server.id,
                    original_name="list_fault_cases",
                    model_alias=f"{server.server_key}__list_fault_cases",
                    enabled=True,
                    risk_policy=ToolRiskPolicy.READ_ONLY,
                )
            )
            db.add(
                MCPTool(
                    server_id=server.id,
                    original_name="delete_fault_case",
                    model_alias=f"{server.server_key}__delete_fault_case",
                    enabled=True,
                    risk_policy=delete_tool_policy,
                )
            )
            await db.commit()
            return server.id

    return asyncio.run(seed())


def login(client: TestClient) -> str:
    response = client.post("/api/v1/auth/login", json={"username": "admin", "password": "admin123"})
    return response.json()["data"]["csrf_token"]


def test_list_fault_cases_requires_login() -> None:
    seed_iot_server(delete_tool_policy=ToolRiskPolicy.APPROVAL_REQUIRED)

    with TestClient(app) as client:
        response = client.get("/api/v1/fault-cases")
        assert response.status_code == 401


# 测试共享同一个 SQLite 库，seed 会累积多个服务器；请求必须带 service_id
# 才能定向到本测试注册的服务器，避免命中其他测试的旧配置。


def test_list_fault_cases_forwards_read_only_call(monkeypatch) -> None:
    server_id = seed_iot_server(delete_tool_policy=ToolRiskPolicy.APPROVAL_REQUIRED)
    captured: dict[str, object] = {}

    async def fake_invoke(_server, _settings, tool_name, arguments, **_kwargs):
        captured["tool_name"] = tool_name
        captured.update(arguments)
        assert tool_name == "list_fault_cases"
        return {"ok": True, "data": CASES_PAGE, "error": None}

    monkeypatch.setattr("app.api.knowledge.invoke_remote_tool", fake_invoke)

    with TestClient(app) as client:
        login(client)
        response = client.get(
            "/api/v1/fault-cases",
            params={"service_id": server_id, "limit": 10, "offset": 5},
        )
        assert response.status_code == 200
        payload = response.json()["data"]
        assert payload["items"][0]["fault_id"] == "FD663EB01"
        assert payload["total"] == 1
        assert captured["limit"] == 10 and captured["offset"] == 5


def test_delete_fault_case_requires_approval_tool(monkeypatch) -> None:
    server_id = seed_iot_server(delete_tool_policy=ToolRiskPolicy.READ_ONLY)

    async def fail_invoke(*_args, **_kwargs):  # pragma: no cover - 不应被调用
        raise AssertionError("should not invoke delete tool")

    monkeypatch.setattr("app.api.knowledge.invoke_remote_tool", fail_invoke)

    with TestClient(app) as client:
        csrf = login(client)
        response = client.delete(
            "/api/v1/fault-cases/FD663EB01",
            params={"service_id": server_id},
            headers={"X-CSRF-Token": csrf},
        )
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "FAULT_CASE_DELETE_TOOL_NOT_APPROVED"


def test_delete_fault_case_requires_csrf(monkeypatch) -> None:
    server_id = seed_iot_server(delete_tool_policy=ToolRiskPolicy.APPROVAL_REQUIRED)

    async def fake_invoke(_server, _settings, tool_name, arguments, **_kwargs):
        return {"ok": True, "data": DELETE_RESULT, "error": None}

    monkeypatch.setattr("app.api.knowledge.invoke_remote_tool", fake_invoke)

    with TestClient(app) as client:
        login(client)
        response = client.delete("/api/v1/fault-cases/FD663EB01", params={"service_id": server_id})
        assert response.status_code == 403


def test_delete_fault_case_audits_and_forwards(monkeypatch) -> None:
    server_id = seed_iot_server(delete_tool_policy=ToolRiskPolicy.APPROVAL_REQUIRED)
    captured: dict[str, object] = {}

    async def fake_invoke(_server, _settings, tool_name, arguments, **_kwargs):
        captured["tool_name"] = tool_name
        captured.update(arguments)
        return {"ok": True, "data": DELETE_RESULT, "error": None, "trace_id": "trace-1"}

    # DELETE 端点在 fault_cases 命名空间直接调用 invoke_remote_tool
    monkeypatch.setattr("app.api.fault_cases.invoke_remote_tool", fake_invoke)

    with TestClient(app) as client:
        csrf = login(client)
        response = client.delete(
            "/api/v1/fault-cases/FD663EB01",
            params={"service_id": server_id},
            headers={"X-CSRF-Token": csrf},
        )
        assert response.status_code == 200
        payload = response.json()["data"]
        assert payload["sync_status"] == "complete"
        assert payload["trace_id"] == "trace-1"
        assert captured["fault_id"] == "FD663EB01"

    async def check_audit() -> None:
        async with SessionFactory() as db:
            logs = (
                await db.scalars(select(AuditLog).where(AuditLog.action == "fault_case.deleted"))
            ).all()
            assert logs, "应写入 fault_case.deleted 审计日志"

    asyncio.run(check_audit())
    assert server_id  # 引用以保持种子有效
