"""MCP Streamable HTTP 传输层集成测试。

依赖主后端声明的 openai-agents SDK（agents.mcp），对真实 MCP 服务发起发现请求；
未设置 MCP_INTEGRATION_URL 时跳过，不作为单元测试门槛。
"""

import os

import pytest
from agents.mcp import MCPServerStreamableHttp

from app.mcp_http import mcp_httpx_client_factory


async def test_streamable_http_discovery() -> None:
    url = os.getenv("MCP_INTEGRATION_URL", "").strip()
    if not url:
        pytest.skip("set MCP_INTEGRATION_URL to run the live transport test")
    token = os.getenv("MCP_INTEGRATION_TOKEN", "").strip()
    client = MCPServerStreamableHttp(
        name="iot-diagnosis-test",
        params={
            "url": url,
            "headers": {"Authorization": f"Bearer {token}"} if token else None,
            "timeout": 10,
            "httpx_client_factory": mcp_httpx_client_factory,
        },
        client_session_timeout_seconds=15,
    )
    async with client:
        tools = await client.list_tools()
    assert "diagnose_fault" in {tool.name for tool in tools}
    assert "search_knowledge" in {tool.name for tool in tools}
