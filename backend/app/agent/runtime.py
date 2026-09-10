import asyncio
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, Protocol

from app.config import Settings
from app.mcp_http import mcp_httpx_client_factory


@dataclass(slots=True)
class RuntimeEvent:
    event_type: str
    data: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class RuntimeMCPServer:
    server_id: str
    name: str
    url: str
    authorization: str | None
    allowed_tools: list[str]


class AgentRuntime(Protocol):
    async def stream(
        self,
        messages: list[dict[str, str]],
        mcp_servers: list[RuntimeMCPServer],
    ) -> AsyncIterator[RuntimeEvent]: ...


class MockAgentRuntime:
    """确定性联调 Runtime，不调用外部模型。"""

    async def stream(
        self,
        messages: list[dict[str, str]],
        mcp_servers: list[RuntimeMCPServer],
    ) -> AsyncIterator[RuntimeEvent]:
        question = messages[-1]["content"] if messages else ""
        yield RuntimeEvent("tool.started", {"tool_name": "demo__inspect_request"})
        await asyncio.sleep(0.02)
        yield RuntimeEvent(
            "tool.finished",
            {"tool_name": "demo__inspect_request", "ok": True, "summary": "请求已分类"},
        )
        answer = (
            f"小yi 已收到：{question}\n\n"
            "当前运行在本地联调模式。配置 OPENAI_API_KEY 后将切换到 OpenAI Agents SDK，"
            "并根据本地策略调用已启用的 MCP 工具。"
        )
        for chunk in [answer[index : index + 18] for index in range(0, len(answer), 18)]:
            await asyncio.sleep(0.01)
            yield RuntimeEvent("answer.delta", {"delta": chunk})
        yield RuntimeEvent("answer.final", {"content": answer})


class OpenAIAgentsRuntime:
    def __init__(self, settings: Settings) -> None:
        if not settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is required for the OpenAI runtime")
        self.settings = settings

    async def stream(
        self,
        messages: list[dict[str, str]],
        mcp_servers: list[RuntimeMCPServer],
    ) -> AsyncIterator[RuntimeEvent]:
        from agents import Agent, RunConfig, Runner
        from agents.items import ToolCallItem, ToolCallOutputItem
        from agents.mcp import MCPServerManager, MCPServerStreamableHttp, create_static_tool_filter
        from agents.models.openai_chatcompletions import OpenAIChatCompletionsModel
        from agents.models.openai_responses import OpenAIResponsesModel
        from openai import AsyncOpenAI

        client = AsyncOpenAI(
            api_key=self.settings.openai_api_key,
            base_url=self.settings.openai_base_url,
        )
        model = (
            OpenAIChatCompletionsModel(
                model=self.settings.openai_model,
                openai_client=client,
            )
            if self.settings.openai_api_mode == "chat_completions"
            else OpenAIResponsesModel(
                model=self.settings.openai_model,
                openai_client=client,
            )
        )

        clients = []
        for server in mcp_servers:
            headers = {"Authorization": server.authorization} if server.authorization else None
            clients.append(
                MCPServerStreamableHttp(
                    name=server.name,
                    params={
                        "url": server.url,
                        "headers": headers,
                        "timeout": 15,
                        "httpx_client_factory": mcp_httpx_client_factory,
                    },
                    cache_tools_list=True,
                    tool_filter=create_static_tool_filter(allowed_tool_names=server.allowed_tools),
                    client_session_timeout_seconds=15,
                    use_structured_content=True,
                )
            )

        try:
            async with MCPServerManager(
                clients,
                drop_failed_servers=True,
                strict=False,
                connect_in_parallel=True,
            ) as manager:
                agent = Agent(
                    name="小yi",
                    instructions=(
                        "你是通用智能体小yi。只使用当前运行明确提供并获准的工具；"
                        "物联网问题优先使用诊断、设备状态、日志、知识和故障案例工具，"
                        "保留结果中的证据来源；工具失败或依据不足时如实说明，不编造结果。"
                    ),
                    model=model,
                    mcp_servers=manager.active_servers,
                    mcp_config={
                        "convert_schemas_to_strict": True,
                        "include_server_in_tool_names": True,
                    },
                )
                result = Runner.run_streamed(
                    agent,
                    input=messages,
                    max_turns=8,
                    run_config=RunConfig(
                        tracing_disabled=True,
                        trace_include_sensitive_data=False,
                        workflow_name="xiaoyi-chat",
                    ),
                )
                final_parts: list[str] = []
                tool_calls: dict[str, tuple[str, str | None]] = {}
                async for event in result.stream_events():
                    if event.type == "raw_response_event":
                        event_data = event.data
                        if getattr(event_data, "type", "") == "response.output_text.delta":
                            delta = getattr(event_data, "delta", "")
                            if delta:
                                final_parts.append(delta)
                                yield RuntimeEvent("answer.delta", {"delta": delta})
                        continue
                    if event.type != "run_item_stream_event":
                        continue
                    if event.name == "tool_called" and isinstance(event.item, ToolCallItem):
                        call_id = event.item.call_id or ""
                        tool_name = event.item.tool_name or "unknown_tool"
                        server_name = (
                            event.item.tool_origin.mcp_server_name if event.item.tool_origin else None
                        )
                        tool_calls[call_id] = (tool_name, server_name)
                        yield RuntimeEvent(
                            "tool.started",
                            {
                                "tool_name": tool_name,
                                "server_name": server_name,
                                "call_id": call_id,
                            },
                        )
                    if event.name == "tool_output" and isinstance(event.item, ToolCallOutputItem):
                        call_id = event.item.call_id or ""
                        tool_name, server_name = tool_calls.get(
                            call_id, ("unknown_tool", None)
                        )
                        output = event.item.output
                        if isinstance(output, str):
                            try:
                                output = json.loads(output)
                            except json.JSONDecodeError:
                                pass
                        ok = output.get("ok") if isinstance(output, dict) else True
                        error = output.get("error") if isinstance(output, dict) else None
                        summary = (
                            "已完成"
                            if ok
                            else str(error.get("message", "工具调用失败"))
                            if isinstance(error, dict)
                            else "工具调用失败"
                        )
                        yield RuntimeEvent(
                            "tool.finished",
                            {
                                "tool_name": tool_name,
                                "server_name": server_name,
                                "call_id": call_id,
                                "ok": bool(ok),
                                "summary": summary,
                                "output": output,
                            },
                        )
                content = "".join(final_parts) or str(result.final_output or "")
                yield RuntimeEvent("answer.final", {"content": content})
        finally:
            await client.close()


def build_runtime(settings: Settings) -> AgentRuntime:
    if settings.agent_runtime.lower() == "openai" and settings.openai_api_key:
        return OpenAIAgentsRuntime(settings)
    return MockAgentRuntime()
