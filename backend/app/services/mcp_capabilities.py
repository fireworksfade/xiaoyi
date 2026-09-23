"""MCP 能力路由（specs WP-09 / §8）。

`purpose=iot` 只用于粗分类；业务 API 按已发现且启用的工具目录匹配所需能力：

- 显式 service_id：验证该服务具备所需工具（含策略要求），缺失时
  MCP_CAPABILITY_MISMATCH；
- 未提供：唯一匹配直接选择；无匹配 MCP_CAPABILITY_UNAVAILABLE；
- 多个匹配且无默认项 → MCP_CAPABILITY_AMBIGUOUS，不按创建时间静默选择。
"""

from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import MCPServer, MCPTool, ToolRiskPolicy

# 常用能力组合：调用方也可直接传工具名集合
CAPABILITY_KNOWLEDGE_READ = {"list_knowledge_documents"}
CAPABILITY_KNOWLEDGE_WRITE = {"ingest_knowledge_text", "delete_knowledge_document"}
CAPABILITY_FAULT_CASES = {
    "list_fault_cases",
    "delete_fault_case",
    "add_verified_fault_case",
    "update_fault_case_lifecycle",
}
CAPABILITY_CONTROL_APPROVAL = {"decide_remediation_proposal"}


def _unavailable() -> HTTPException:
    return HTTPException(status_code=503, detail="MCP_CAPABILITY_UNAVAILABLE")


def _ambiguous() -> HTTPException:
    return HTTPException(status_code=409, detail="MCP_CAPABILITY_AMBIGUOUS")


def _mismatch() -> HTTPException:
    return HTTPException(status_code=422, detail="MCP_CAPABILITY_MISMATCH")


async def _enabled_tools(db: AsyncSession, server_id: str) -> dict[str, ToolRiskPolicy]:
    """服务上已发现且启用的工具 → 风险策略映射。"""
    rows = await db.scalars(
        select(MCPTool).where(
            MCPTool.server_id == server_id,
            MCPTool.enabled.is_(True),
            MCPTool.risk_policy != ToolRiskPolicy.DISABLED,
        )
    )
    return {item.original_name: item.risk_policy for item in rows.all()}


def _satisfies(
    available: dict[str, ToolRiskPolicy],
    required_tools: set[str],
    require_policy: dict[str, ToolRiskPolicy] | None,
) -> bool:
    if set(available) & required_tools != required_tools:
        return False
    for tool, policy in (require_policy or {}).items():
        if tool in required_tools and available.get(tool) != policy:
            return False
    return True


async def resolve_mcp_server(
    db: AsyncSession,
    *,
    required_tools: set[str],
    explicit_server_id: str | None = None,
    default_kind: str | None = None,
    require_policy: dict[str, ToolRiskPolicy] | None = None,
) -> MCPServer:
    """按能力选择 MCP 服务；失败时抛出稳定错误码的 HTTP 异常。"""

    if explicit_server_id:
        server = await db.scalar(
            select(MCPServer).where(
                MCPServer.id == explicit_server_id,
                MCPServer.deleted_at.is_(None),
            )
        )
        if not server or not server.enabled or server.connection_status != "connected":
            raise _unavailable()
        available = await _enabled_tools(db, server.id)
        if not _satisfies(available, required_tools, require_policy):
            raise _mismatch()
        return server

    servers = list(
        (
            await db.scalars(
                select(MCPServer).where(
                    MCPServer.enabled.is_(True),
                    MCPServer.connection_status == "connected",
                    MCPServer.deleted_at.is_(None),
                )
            )
        ).all()
    )
    candidates: list[MCPServer] = []
    for server in servers:
        available = await _enabled_tools(db, server.id)
        if _satisfies(available, required_tools, require_policy):
            candidates.append(server)

    if not candidates:
        raise _unavailable()
    if len(candidates) == 1:
        return candidates[0]

    # 多个匹配：优先 service_kind 的默认项；未配置默认项时保持显式歧义错误
    if default_kind:
        defaults = [
            server
            for server in candidates
            if server.service_kind == default_kind and server.is_default_for_kind
        ]
        if len(defaults) == 1:
            return defaults[0]
        kind_matches = [server for server in candidates if server.service_kind == default_kind]
        if len(kind_matches) == 1:
            return kind_matches[0]
    raise _ambiguous()
