"""统一 MCP 动作工具的诊断关联参数校验。"""

import pytest
from mcp.client import Client

from iot_mcp import server as control_server


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
