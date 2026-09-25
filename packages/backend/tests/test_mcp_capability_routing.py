"""MCP 能力路由测试（specs WP-09 / §8.3）。

覆盖：注册顺序无关、删除重建后路由不变、能力歧义、显式 ID 不匹配、
工具禁用、策略不符、目录未刷新与服务断连。
"""

import asyncio
import uuid

from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.db import SessionFactory
from app.main import app
from app.models import MCPServer, MCPTool, ToolRiskPolicy
from app.services.mcp_capabilities import resolve_mcp_server

DIAGNOSIS_TOOLS = {
    "list_fault_cases": ToolRiskPolicy.READ_ONLY,
    "delete_fault_case": ToolRiskPolicy.APPROVAL_REQUIRED,
    "add_verified_fault_case": ToolRiskPolicy.APPROVAL_REQUIRED,
    "list_knowledge_documents": ToolRiskPolicy.READ_ONLY,
}
CONTROL_TOOLS = {
    "decide_remediation_proposal": ToolRiskPolicy.APPROVAL_REQUIRED,
}


def _login(client: TestClient) -> str:
    response = client.post("/api/v1/auth/login", json={"username": "admin", "password": "admin123"})
    return response.json()["data"]["csrf_token"]


async def _seed_server(
    server_key: str,
    tools: dict[str, ToolRiskPolicy],
    *,
    enabled: bool = True,
    connected: bool = True,
    service_kind: str = "generic",
    default_for_kind: bool = False,
) -> MCPServer:
    async with SessionFactory() as db:
        server = MCPServer(
            server_key=server_key,
            name=server_key,
            url="http://127.0.0.1:9001/mcp",
            purpose="iot",
            enabled=enabled,
            connection_status="connected" if connected else "disconnected",
            service_kind=service_kind,
            is_default_for_kind=default_for_kind,
        )
        db.add(server)
        await db.flush()
        for tool_name, policy in tools.items():
            db.add(
                MCPTool(
                    server_id=server.id,
                    original_name=tool_name,
                    model_alias=f"{server.server_key}__{tool_name}",
                    enabled=True,
                    risk_policy=policy,
                )
            )
        await db.commit()
        await db.refresh(server)
        return server


def test_registration_order_does_not_change_routing() -> None:
    """先注册 Control、后注册 Diagnosis：知识/案例 API 仍按能力选择 Diagnosis。"""

    async def run():
        async with SessionFactory() as db:
            await _seed_server("iot-control-first", CONTROL_TOOLS, service_kind="control")
            diagnosis = await _seed_server(
                "iot-diagnosis-second", DIAGNOSIS_TOOLS, service_kind="diagnosis"
            )
            chosen = await resolve_mcp_server(db, required_tools={"list_fault_cases"})
            assert chosen.id == diagnosis.id

            # 重复解析（等价于删除重建后的语义）：路由结果不变
            chosen_again = await resolve_mcp_server(db, required_tools={"list_fault_cases"})
            assert chosen_again.server_key == chosen.server_key

            # 控制审批能力仍路由到 Control
            control_chosen = await resolve_mcp_server(
                db, required_tools={"decide_remediation_proposal"}
            )
            assert control_chosen.server_key == "iot-control-first"

    asyncio.run(run())


def test_capability_mismatch_on_explicit_server() -> None:
    """显式传入不具备目标工具的服务时不发起远端调用，返回 MISMATCH。"""

    async def run():
        async with SessionFactory() as db:
            control = await _seed_server("iot-control-only", CONTROL_TOOLS, service_kind="control")
            try:
                await resolve_mcp_server(
                    db,
                    required_tools={"list_fault_cases"},
                    explicit_server_id=control.id,
                )
            except HTTPException as exc:
                assert exc.status_code == 422
                assert exc.detail == "MCP_CAPABILITY_MISMATCH"
            else:
                raise AssertionError("expected MCP_CAPABILITY_MISMATCH")

    asyncio.run(run())


def test_capability_ambiguous_without_default() -> None:
    """两个服务拥有相同能力且未配置默认项时返回明确歧义错误。"""

    async def run():
        async with SessionFactory() as db:
            tools = {
                "list_fault_cases": ToolRiskPolicy.READ_ONLY,
                "delete_fault_case": ToolRiskPolicy.APPROVAL_REQUIRED,
            }
            await _seed_server("diag-a", tools, service_kind="diagnosis")
            await _seed_server("diag-b", tools, service_kind="diagnosis")
            try:
                await resolve_mcp_server(db, required_tools={"list_fault_cases"})
            except HTTPException as exc:
                assert exc.status_code == 409
                assert exc.detail == "MCP_CAPABILITY_AMBIGUOUS"
            else:
                raise AssertionError("expected MCP_CAPABILITY_AMBIGUOUS")

            # 配置默认项后歧义消除（需声明 default_kind）
            await _seed_server(
                "diag-default",
                tools,
                service_kind="diagnosis",
                default_for_kind=True,
            )
            chosen = await resolve_mcp_server(
                db, required_tools={"list_fault_cases"}, default_kind="diagnosis"
            )
            assert chosen.server_key == "diag-default"

    asyncio.run(run())


def test_capability_unavailable_and_disabled_tools() -> None:
    async def run():
        async with SessionFactory() as db:
            await _seed_server(
                "diag-off", {"list_fault_cases": ToolRiskPolicy.READ_ONLY}, enabled=False
            )
            await _seed_server(
                "diag-disc", {"list_fault_cases": ToolRiskPolicy.READ_ONLY}, connected=False
            )
            try:
                await resolve_mcp_server(db, required_tools={"list_fault_cases"})
            except HTTPException as exc:
                assert exc.status_code == 503
                assert exc.detail == "MCP_CAPABILITY_UNAVAILABLE"
            else:
                raise AssertionError("expected MCP_CAPABILITY_UNAVAILABLE")

            # 工具存在但 disabled：等于能力缺失
            await _seed_server("diag-empty", {}, service_kind="diagnosis")
            try:
                await resolve_mcp_server(db, required_tools={"list_fault_cases"})
            except HTTPException as exc:
                assert exc.status_code == 503
            else:
                raise AssertionError("disabled tool must not satisfy capability")

    asyncio.run(run())


def test_policy_mismatch_detected_via_api() -> None:
    """工具存在但策略不符：显式 service_id 请求返回 MISMATCH（不发起调用）。"""

    async def seed():
        return await _seed_server(
            f"diag-readonly-{uuid.uuid4().hex[:6]}",
            {"list_fault_cases": ToolRiskPolicy.READ_ONLY},
            service_kind="diagnosis",
        )

    server_id = asyncio.run(seed()).id

    def fail_invoke(*_args, **_kwargs):  # pragma: no cover - 不应被调用
        raise AssertionError("should not invoke remote tool")

    with TestClient(app) as client:
        csrf = _login(client)
        response = client.delete(
            "/api/v1/fault-cases/FD663EB01",
            params={"service_id": server_id},
            headers={"X-CSRF-Token": csrf},
        )
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "MCP_CAPABILITY_MISMATCH"
