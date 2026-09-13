import asyncio
import uuid

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import SessionFactory
from app.main import app
from app.models import AuditLog, MCPPurpose, MCPServer, MCPTool, ToolRiskPolicy

PROPOSAL = {
    "proposal_id": "RPR_20260912_TEST0001",
    "device_id": "ESP32_05",
    "action": "restart_device",
    "parameters": {},
    "reason": "watchdog reset loop",
    "impact": "设备将重启一次，短暂中断上报",
    "status": "pending",
    "version": 1,
    "expires_at": "2026-09-12T23:59:59+00:00",
    "task_status": None,
    "command_id": None,
    "decided_by": None,
    "decided_at": None,
    "created_at": "2026-09-12T08:00:00+00:00",
    "updated_at": "2026-09-12T08:00:00+00:00",
}


def seed_control_server() -> str:
    async def seed() -> str:
        async with SessionFactory() as db:
            server = MCPServer(
                server_key=f"control-{uuid.uuid4().hex[:8]}",
                name="控制测试服务",
                url="http://127.0.0.1:9002/mcp",
                purpose=MCPPurpose.IOT,
                enabled=True,
                connection_status="connected",
            )
            db.add(server)
            await db.flush()
            db.add(
                MCPTool(
                    server_id=server.id,
                    original_name="decide_remediation_proposal",
                    model_alias=f"{server.server_key}__decide_remediation_proposal",
                    enabled=True,
                    risk_policy=ToolRiskPolicy.APPROVAL_REQUIRED,
                )
            )
            await db.commit()
            return server.id

    return asyncio.run(seed())


def login(client: TestClient) -> str:
    response = client.post("/api/v1/auth/login", json={"username": "admin", "password": "admin123"})
    return response.json()["data"]["csrf_token"]


def test_decision_endpoint_approval_flow(monkeypatch) -> None:
    seed_control_server()
    captured: dict[str, object] = {}

    async def fake_invoke(_server, _settings, tool_name, arguments, **_kwargs):
        captured["tool_name"] = tool_name
        captured.update(arguments)
        if tool_name == "get_action_result":
            return {"ok": True, "data": {"proposal": dict(PROPOSAL)}, "error": None}
        assert tool_name == "decide_remediation_proposal"
        decided = {
            **PROPOSAL,
            "status": "approved",
            "version": PROPOSAL["version"] + 1,
            "task_status": "running",
            "decided_by": arguments["decided_by"],
            "command_id": "CMD_TEST",
        }
        return {
            "ok": True,
            "data": {**decided, "command": {"command_id": "CMD_TEST"}, "delivered": True},
            "error": None,
        }

    monkeypatch.setattr("app.api.remediation.invoke_remote_tool", fake_invoke)

    with TestClient(app) as client:
        csrf = login(client)
        response = client.post(
            f"/api/v1/remediation-proposals/{PROPOSAL['proposal_id']}/decision",
            json={"decision": "approved", "expected_version": 1},
            headers={"X-CSRF-Token": csrf},
        )
        assert response.status_code == 200
        body = response.json()["data"]
        assert body["status"] == "approved"
        assert body["task_status"] == "running"
        assert captured["tool_name"] == "decide_remediation_proposal"
        assert captured["decided_by"] == "admin"
        assert captured["expected_version"] == 1

    async def audit_written() -> bool:
        async with SessionFactory() as db:
            record = await db.scalar(
                select(AuditLog).where(
                    AuditLog.action == "remediation.approved",
                    AuditLog.resource_id == PROPOSAL["proposal_id"],
                )
            )
            return record is not None

    assert asyncio.run(audit_written())


def test_decision_rejects_version_conflict_and_non_pending(monkeypatch) -> None:
    seed_control_server()

    async def fake_invoke(_server, _settings, tool_name, arguments, **_kwargs):
        assert tool_name == "get_action_result"
        return {"ok": True, "data": {"proposal": dict(PROPOSAL)}, "error": None}

    monkeypatch.setattr("app.api.remediation.invoke_remote_tool", fake_invoke)

    with TestClient(app) as client:
        csrf = login(client)
        conflict = client.post(
            f"/api/v1/remediation-proposals/{PROPOSAL['proposal_id']}/decision",
            json={"decision": "approved", "expected_version": 7},
            headers={"X-CSRF-Token": csrf},
        )
        assert conflict.status_code == 409
        assert conflict.json()["error"]["code"] == "VERSION_CONFLICT"

        decided = {
            **PROPOSAL,
            "status": "approved",
            "version": 2,
            "task_status": "running",
        }

        async def fake_final(_server, _settings, tool_name, _arguments, **_kwargs):
            assert tool_name == "get_action_result"
            return {"ok": True, "data": {"proposal": decided}, "error": None}

        monkeypatch.setattr("app.api.remediation.invoke_remote_tool", fake_final)
        not_pending = client.post(
            f"/api/v1/remediation-proposals/{PROPOSAL['proposal_id']}/decision",
            json={"decision": "rejected", "expected_version": 2},
            headers={"X-CSRF-Token": csrf},
        )
        assert not_pending.status_code == 409
        assert not_pending.json()["error"]["code"] == "PROPOSAL_NOT_PENDING"


def test_decision_requires_admin_and_csrf(monkeypatch) -> None:
    seed_control_server()

    async def fake_invoke(_server, _settings, tool_name, _arguments, **_kwargs):
        assert tool_name == "get_action_result"
        return {"ok": True, "data": {"proposal": dict(PROPOSAL)}, "error": None}

    monkeypatch.setattr("app.api.remediation.invoke_remote_tool", fake_invoke)

    with TestClient(app) as client:
        csrf = login(client)
        no_csrf = client.post(
            f"/api/v1/remediation-proposals/{PROPOSAL['proposal_id']}/decision",
            json={"decision": "approved", "expected_version": 1},
        )
        assert no_csrf.status_code in (401, 403)

        # 普通用户无法决策提案
        client.post(
            "/api/v1/auth/logout",
            headers={"X-CSRF-Token": csrf},
        )
        operator_login = client.post(
            "/api/v1/auth/login", json={"username": "operator", "password": "operator123"}
        )
        if operator_login.status_code == 200:
            operator_csrf = operator_login.json()["data"]["csrf_token"]
            forbidden = client.post(
                f"/api/v1/remediation-proposals/{PROPOSAL['proposal_id']}/decision",
                json={"decision": "approved", "expected_version": 1},
                headers={"X-CSRF-Token": operator_csrf},
            )
            assert forbidden.status_code == 403


def test_control_server_requires_execution_tool(monkeypatch) -> None:
    async def seed_bare_server() -> str:
        async with SessionFactory() as db:
            server = MCPServer(
                server_key=f"bare-{uuid.uuid4().hex[:8]}",
                name="无控制工具服务",
                url="http://127.0.0.1:9001/mcp",
                purpose=MCPPurpose.IOT,
                enabled=True,
                connection_status="connected",
            )
            db.add(server)
            await db.commit()
            return server.id

    asyncio.run(seed_bare_server())

    # 测试共享同一数据库：先禁用既有控制服务上的执行工具，确保找不到可用控制服务
    async def disable_existing_tools() -> None:
        async with SessionFactory() as db:
            tools = await db.scalars(
                select(MCPTool).where(MCPTool.original_name == "decide_remediation_proposal")
            )
            for tool in tools:
                tool.enabled = False
            await db.commit()

    asyncio.run(disable_existing_tools())

    async def fail_invoke(*_args, **_kwargs):  # pragma: no cover - 不应被调用
        raise AssertionError("should not invoke any tool")

    monkeypatch.setattr("app.api.remediation.invoke_remote_tool", fail_invoke)

    with TestClient(app) as client:
        csrf = login(client)
        response = client.get(
            "/api/v1/remediation-proposals?proposal_status=pending",
            headers={"X-CSRF-Token": csrf},
        )
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "CONTROL_MCP_UNAVAILABLE"


def test_collect_proposals_appends_for_message_metadata() -> None:
    """提案必须写入 proposals 列表，否则刷新后审批卡无法从消息元数据恢复。"""
    from app.services.runs import _collect_proposals

    proposals: list[dict[str, object]] = []
    event = {
        "tool_name": "create_remediation_proposal",
        "output": {
            "ok": True,
            "data": {
                "proposal_id": "RPR_20260913_TEST0001",
                "device_id": "ESP32_05",
                "action": "restart_device",
                "status": "pending",
                "version": 1,
            },
        },
    }

    collected = _collect_proposals(event, proposals)

    assert collected is not None
    assert collected["proposal_id"] == "RPR_20260913_TEST0001"
    assert proposals == [collected]
    # 非提案工具不收集
    other = _collect_proposals(
        {"tool_name": "list_devices", "output": {"ok": True, "data": {"items": []}}},
        proposals,
    )
    assert other is None
    assert len(proposals) == 1
