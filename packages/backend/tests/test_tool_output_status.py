from types import SimpleNamespace

import agents
import agents.mcp

from app.agent.runtime import OpenAIAgentsRuntime, normalize_tool_output, segment_separator
from app.config import Settings


def test_segment_separator_only_adds_the_missing_blank_line():
    assert segment_separator("") == ""
    assert segment_separator("我先查一下。") == "\n\n"
    assert segment_separator("我先查一下。\n") == "\n"
    assert segment_separator("我先查一下。\n\n") == ""


async def test_text_from_each_model_turn_starts_its_own_paragraph(monkeypatch):
    """工具调用前后的两轮输出不能拼成“我先查一下。## 标题”，否则标题无法渲染。"""

    def raw(kind, delta=None):
        return SimpleNamespace(type="raw_response_event", data=SimpleNamespace(type=kind, delta=delta))

    events = [
        raw("response.created"),
        raw("response.output_text.delta", "我先查一下"),
        raw("response.output_text.delta", "。"),
        raw("response.created"),
        raw("response.output_text.delta", "## 统计结果\n"),
        raw("response.output_text.delta", "| 设备 | 均值 |"),
    ]

    class FakeResult:
        final_output = None

        async def stream_events(self):
            for event in events:
                yield event

    class FakeManager:
        def __init__(self, *args, **kwargs):
            self.active_servers = []

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

    monkeypatch.setattr(agents.Runner, "run_streamed", staticmethod(lambda *a, **k: FakeResult()))
    monkeypatch.setattr(agents.mcp, "MCPServerManager", FakeManager)
    runtime = OpenAIAgentsRuntime(
        Settings(_env_file=None, openai_api_key="test-key", openai_api_mode="chat_completions")
    )

    streamed = [event async for event in runtime.stream([{"role": "user", "content": "统计"}], [])]

    deltas = "".join(e.data["delta"] for e in streamed if e.event_type == "answer.delta")
    final = next(e.data["content"] for e in streamed if e.event_type == "answer.final")
    assert final == deltas == "我先查一下。\n\n## 统计结果\n| 设备 | 均值 |"


def test_sdk_transport_failure_is_not_reported_as_success():
    output = normalize_tool_output(
        "An error occurred while running the tool. Please try again. "
        "Error: Request 'tools/call' timed out"
    )
    assert output["ok"] is False
    assert output["error"]["code"] == "MCP_TOOL_CALL_FAILED"
    assert output["error"]["retryable"] is True


def test_tool_output_preserves_structured_and_plain_successes():
    assert normalize_tool_output('{"ok":true,"data":{"rows":[]}}') == {
        "ok": True, "data": {"rows": []}
    }
    result = {"ok": False, "error": {"code": "TEXT2SQL_CLARIFICATION_REQUIRED"}}
    assert normalize_tool_output(result) is result
    assert normalize_tool_output("normal tool text") == "normal tool text"
