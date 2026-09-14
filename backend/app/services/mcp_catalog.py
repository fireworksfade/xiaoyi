import hashlib
import re
import time
from typing import Any
from urllib.parse import urlsplit

from agents.mcp import MCPServerStreamableHttp
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.runtime import RuntimeMCPServer
from app.config import Settings
from app.mcp_http import mcp_httpx_client_factory
from app.models import MCPServer, MCPTool, ToolRiskPolicy, utc_now
from app.observability.metrics import MCP_CALLS, MCP_LATENCY
from app.security import decrypt_secret


def validate_mcp_url(url: str, settings: Settings) -> str:
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("MCP_URL_INVALID")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("MCP_URL_INVALID")
    hostname = parsed.hostname.lower()
    allowed = any(
        hostname == rule or (rule.startswith(".") and hostname.endswith(rule))
        for rule in settings.mcp_allowed_hosts
    )
    if not allowed:
        raise ValueError("MCP_HOST_NOT_ALLOWED")
    return url.rstrip("/")


def stable_alias(server_key: str, tool_name: str) -> str:
    raw = f"{server_key}__{tool_name}"
    normalized = re.sub(r"[^A-Za-z0-9_-]+", "_", raw).strip("_")
    if len(normalized) <= 80:
        return normalized
    suffix = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:10]
    return f"{normalized[:69]}_{suffix}"


async def fetch_remote_tools(server: MCPServer, settings: Settings):
    credential = decrypt_secret(server.credential_ciphertext, settings.app_secret_key)
    headers = {"Authorization": f"Bearer {credential}"} if credential else None
    client = MCPServerStreamableHttp(
        name=server.server_key,
        params={
            "url": server.url,
            "headers": headers,
            "timeout": 10,
            "httpx_client_factory": mcp_httpx_client_factory,
        },
        client_session_timeout_seconds=15,
    )
    async with client:
        return await client.list_tools()


async def invoke_remote_tool(
    server: MCPServer,
    settings: Settings,
    tool_name: str,
    arguments: dict[str, Any],
    *,
    read_only: bool,
    extra_headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    credential = decrypt_secret(server.credential_ciphertext, settings.app_secret_key)
    headers = dict(extra_headers or {})
    if credential:
        headers["Authorization"] = f"Bearer {credential}"
    client = MCPServerStreamableHttp(
        name=server.server_key,
        params={
            "url": server.url,
            "headers": headers or None,
            "timeout": 15,
            "httpx_client_factory": mcp_httpx_client_factory,
        },
        client_session_timeout_seconds=20,
        use_structured_content=True,
        max_retry_attempts=1 if read_only else 0,
    )
    async with client:
        started = time.perf_counter()
        try:
            result = await client.call_tool(tool_name, arguments)
        except Exception:
            MCP_CALLS.labels(server=server.server_key, result="error").inc()
            MCP_LATENCY.labels(server=server.server_key).observe(time.perf_counter() - started)
            raise
        MCP_CALLS.labels(server=server.server_key, result="ok").inc()
        MCP_LATENCY.labels(server=server.server_key).observe(time.perf_counter() - started)
    structured = getattr(result, "structured_content", None)
    if not isinstance(structured, dict):
        raise RuntimeError("MCP_RESULT_INVALID")
    return structured


async def refresh_tool_catalog(
    db: AsyncSession,
    server: MCPServer,
    settings: Settings,
) -> list[MCPTool]:
    remote_tools = await fetch_remote_tools(server, settings)
    existing = {
        item.original_name: item
        for item in (await db.scalars(select(MCPTool).where(MCPTool.server_id == server.id))).all()
    }
    seen: set[str] = set()
    for remote in remote_tools:
        seen.add(remote.name)
        item = existing.get(remote.name)
        if item is None:
            item = MCPTool(
                server_id=server.id,
                original_name=remote.name,
                model_alias=stable_alias(server.server_key, remote.name),
                enabled=False,
                risk_policy=ToolRiskPolicy.DISABLED,
            )
            db.add(item)
        elif item.input_schema != remote.input_schema:
            item.enabled = False
            item.risk_policy = ToolRiskPolicy.DISABLED
            item.catalog_version += 1
        item.description = remote.description or ""
        item.input_schema = remote.input_schema

    for name, item in existing.items():
        if name not in seen:
            item.enabled = False
            item.risk_policy = ToolRiskPolicy.DISABLED

    server.connection_status = "connected"
    server.last_error = None
    server.last_checked_at = utc_now()
    server.tools_version += 1
    await db.commit()
    return list(
        (
            await db.scalars(
                select(MCPTool)
                .where(MCPTool.server_id == server.id)
                .order_by(MCPTool.original_name)
            )
        ).all()
    )


async def load_agent_mcp_servers(
    db: AsyncSession,
    settings: Settings,
) -> list[RuntimeMCPServer]:
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
    result: list[RuntimeMCPServer] = []
    for server in servers:
        tool_names = list(
            (
                await db.scalars(
                    select(MCPTool.original_name).where(
                        MCPTool.server_id == server.id,
                        MCPTool.enabled.is_(True),
                        MCPTool.risk_policy.in_(
                            [ToolRiskPolicy.READ_ONLY, ToolRiskPolicy.PROPOSAL_ONLY]
                        ),
                    )
                )
            ).all()
        )
        if not tool_names:
            continue
        credential = decrypt_secret(server.credential_ciphertext, settings.app_secret_key)
        result.append(
            RuntimeMCPServer(
                server_id=server.id,
                name=server.server_key,
                url=server.url,
                authorization=f"Bearer {credential}" if credential else None,
                allowed_tools=tool_names,
            )
        )
    return result
