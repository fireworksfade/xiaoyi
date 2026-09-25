import asyncio
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, Protocol, cast

from app.agent.remediation_correlation import (
    RemediationCorrelationError,
    RemediationCorrelationState,
)
from app.config import Settings
from app.db import SessionFactory
from app.mcp_http import mcp_httpx_client_factory
from app.observability.metrics import CONTEXT_ARTIFACT_BYTES, CONTEXT_COMPACTIONS
from app.services.artifacts import LocalArtifactStore, extract_critical_fields, sanitize_artifact
from app.services.context_compactor import compact_model_input


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
    run_id: str | None
    workflow_snapshot: dict[str, Any] | None

    def stream(
        self,
        messages: list[dict[str, str]],
        mcp_servers: list[RuntimeMCPServer],
    ) -> AsyncIterator[RuntimeEvent]: ...


class MockAgentRuntime:
    """确定性联调 Runtime，不调用外部模型。"""

    run_id: str | None = None
    workflow_snapshot: dict[str, Any] | None = None

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
        self.run_id: str | None = None
        self.workflow_snapshot: dict[str, Any] | None = None

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
        from agents.run_config import ModelInputData
        from mcp.types import CallToolResult, TextContent
        from openai import AsyncOpenAI

        correlation = RemediationCorrelationState()
        runtime_run_id = self.run_id
        runtime_settings = self.settings

        def filter_model_input(data: Any) -> ModelInputData:
            compacted = compact_model_input(
                data.model_data.input,
                workflow_snapshot=self.workflow_snapshot,
                keep_recent_tool_results=self.settings.context_keep_recent_tool_results,
                max_tool_output_chars=max(256, self.settings.run_tool_output_inline_bytes),
            )
            if compacted.compacted_outputs:
                CONTEXT_COMPACTIONS.labels(layer="L2").inc(compacted.compacted_outputs)
            return ModelInputData(input=compacted.items, instructions=data.model_data.instructions)

        class CorrelatedMCPServer(MCPServerStreamableHttp):
            async def call_tool(
                self,
                tool_name: str,
                arguments: dict[str, Any] | None,
                meta: dict[str, Any] | None = None,
            ) -> CallToolResult:
                correlation.begin_tool_call(tool_name, arguments)
                try:
                    prepared = correlation.prepare_arguments(tool_name, arguments)
                except RemediationCorrelationError as exc:
                    payload = {
                        "ok": False,
                        "data": None,
                        "error": {
                            "code": exc.code,
                            "message": str(exc),
                            "retryable": False,
                        },
                    }
                    return CallToolResult(
                        content=[
                            TextContent(type="text", text=json.dumps(payload, ensure_ascii=False))
                        ],
                        structured_content=payload,
                        is_error=True,
                    )
                result = await super().call_tool(tool_name, prepared, meta)
                correlation.record_tool_result(tool_name, result.structured_content)
                output = result.structured_content
                if runtime_run_id and isinstance(output, dict):
                    sanitized = sanitize_artifact(output)
                    raw = json.dumps(sanitized, ensure_ascii=False, default=str).encode("utf-8")
                    if len(raw) > runtime_settings.run_tool_output_inline_bytes:
                        async with SessionFactory() as db:
                            artifact = await LocalArtifactStore(
                                runtime_settings.run_artifact_root,
                                runtime_settings.run_artifact_retention_hours,
                            ).write(
                                db,
                                run_id=runtime_run_id,
                                kind="tool_output",
                                content=sanitized,
                            )
                            await db.commit()
                        CONTEXT_ARTIFACT_BYTES.labels(kind="tool_output").inc(artifact.size_bytes)
                        CONTEXT_COMPACTIONS.labels(layer="L1").inc()
                        critical_fields = extract_critical_fields(sanitized)
                        summary = {
                            "ok": output.get("ok") is True,
                            "data": critical_fields,
                            "truncated": True,
                            "artifact_id": artifact.id,
                            "original_bytes": artifact.size_bytes,
                            "sha256": artifact.sha256,
                            "critical_fields": critical_fields,
                            "summary": raw[:1024].decode("utf-8", errors="replace"),
                        }
                        return CallToolResult(
                            content=[
                                TextContent(
                                    type="text", text=json.dumps(summary, ensure_ascii=False)
                                )
                            ],
                            structured_content=summary,
                            is_error=result.is_error,
                        )
                return result

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
                CorrelatedMCPServer(
                    name=server.name,
                    params={
                        "url": server.url,
                        "headers": headers or {},
                        "timeout": self.settings.mcp_agent_timeout_seconds,
                        "httpx_client_factory": mcp_httpx_client_factory,
                    },
                    cache_tools_list=True,
                    tool_filter=create_static_tool_filter(allowed_tool_names=server.allowed_tools),
                    client_session_timeout_seconds=self.settings.mcp_agent_timeout_seconds,
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
                        "你是通用智能体小yi，能自主闭环解决物联网运维问题。"
                        "只使用当前运行明确提供并获准的工具，"
                        "工具名称必须与提供的名称完全一致。"
                        "处理设备问题时遵循闭环流程：\n"
                        "1. 先用 list_devices / get_device_status / get_device_logs / diagnose_fault "
                        "完成诊断，保留结果中的证据来源；\n"
                        "2. 若需要修复，先用 list_device_actions 确认可用动作与风险级别："
                        "低风险动作直接调用 execute_device_action 执行；"
                        "高风险动作调用 create_remediation_proposal 创建提案，"
                        "并明确告知用户等待批准后才会执行；"
                        "两种调用都必须携带本轮诊断返回的 diagnosis_id，"
                        "恢复成功后系统会自动把这次修复沉淀为故障案例；\n"
                        "3. 执行后用 get_action_result 轮询命令结果，"
                        "再用 get_device_status / get_device_logs 确认设备已恢复；"
                        "恢复失败时如实说明并给出下一步建议；\n"
                        "4. 最终汇报要包含：诊断结论、已执行或待批准的动作、恢复验证结果。"
                        "工具失败或依据不足时如实说明，不编造结果。"
                    ),
                    model=model,
                    mcp_servers=manager.active_servers,
                    # 第三方 Chat Completions 模型面对 strict 化后必填的可空参数会
                    # 传出 "None" 字符串并触发 MCP 入参校验失败，因此保持原始
                    # JSON Schema，让可选参数可以真正省略。单一诊断 MCP 服务也
                    # 无需工具名前缀：带前缀会诱使部分模型调用裸名，触发
                    # "Tool not found" 运行失败。
                    mcp_config={
                        "convert_schemas_to_strict": False,
                        "include_server_in_tool_names": False,
                    },
                )
                result = Runner.run_streamed(
                    agent,
                    input=cast(Any, messages),
                    # 闭环运维包含诊断、执行、轮询与验证多个环节，需要更多轮次
                    max_turns=14,
                    run_config=RunConfig(
                        tracing_disabled=True,
                        trace_include_sensitive_data=False,
                        workflow_name="xiaoyi-chat",
                        call_model_input_filter=filter_model_input,
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
                            event.item.tool_origin.mcp_server_name
                            if event.item.tool_origin
                            else None
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
                        tool_name, server_name = tool_calls.get(call_id, ("unknown_tool", None))
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
