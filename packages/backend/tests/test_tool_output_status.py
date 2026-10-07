from app.agent.runtime import normalize_tool_output


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
