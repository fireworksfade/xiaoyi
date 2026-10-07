import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from mcp.client import Client

from iot_diagnosis.llm import DiagnosisLLMClient, LLMClientError, LLMResponse
from iot_diagnosis.query_plan import PLAN_CONTRACT
from iot_diagnosis.repository import DiagnosisRepository
from iot_diagnosis.text2sql import Text2SQLError, execute_readonly, query_iot_data


@pytest.fixture
def repository(tmp_path):
    repo = DiagnosisRepository(str(tmp_path / "iot.db"))
    now = datetime.now(timezone.utc)
    for device, seconds in (("test_fresh", 0), ("test_stale", 3600)):
        repo.apply_status(
            device,
            {"online": True, "temperature": 25},
            (now - timedelta(seconds=seconds)).isoformat(),
        )
        repo.add_log(device, {"level": "ERROR", "message": "MQTT timeout"})
        repo.append_telemetry(
            device, {"temperature": 30, "rssi": -70}, (now - timedelta(seconds=seconds)).isoformat()
        )
        repo.save_diagnosis_error(device, "diagnosis question", "TEST_ERROR", "test failure")
    return repo


class FakeLLM:
    available = True

    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def text2sql(self, *args):
        self.calls.append(args)
        return LLMResponse(self.responses.pop(0), 1, 10, 5)


def test_join_aggregation_and_effective_online(repository):
    result = execute_readonly(
        repository,
        """
        SELECT d.device_id, s.online, s.reported_online, count(l.id) AS errors
        FROM iot_devices d JOIN iot_state s USING (device_id)
        LEFT JOIN iot_logs l ON l.device_id = d.device_id AND l.level = :level
        WHERE d.device_id LIKE 'test_%'
        GROUP BY d.device_id ORDER BY d.device_id
    """,
        {"level": "ERROR"},
    )
    assert result["rows"] == [
        {"device_id": "test_fresh", "online": 1, "reported_online": 1, "errors": 1},
        {"device_id": "test_stale", "online": 0, "reported_online": 1, "errors": 1},
    ]
    assert result["sources"] == ["iot_devices", "iot_logs", "iot_state"]


@pytest.mark.parametrize(
    "view", ["iot_devices", "iot_state", "iot_telemetry", "iot_logs", "iot_diagnoses"]
)
def test_scope_enforced_even_without_model_filter(repository, view):
    result = execute_readonly(
        repository, f"SELECT device_id FROM {view}", {}, device_id="test_fresh"
    )
    assert result["rows"] and all(row["device_id"] == "test_fresh" for row in result["rows"])


def test_scope_is_quoted_and_cannot_be_injected(repository):
    device = "x' OR 1=1 --"
    repository.add_log(device, {"message": "only scoped row"})
    result = execute_readonly(repository, "SELECT device_id FROM iot_logs", {}, device_id=device)
    assert result["rows"] == [{"device_id": device}]
    with pytest.raises(Text2SQLError) as error:
        execute_readonly(repository, "SELECT * FROM iot_logs", {}, device_id="test_fresh\x00extra")
    assert error.value.code == "INVALID_REQUEST"


def test_diagnosis_view_hides_trace_and_memory_context(repository):
    result = execute_readonly(repository, "SELECT * FROM iot_diagnoses", {}, device_id="test_fresh")
    assert result["returned"] == 1
    assert not {"result_json", "retrieved_documents_json", "solutions_json"} & set(
        result["columns"]
    )
    with pytest.raises(Text2SQLError):
        execute_readonly(repository, "SELECT result_json FROM iot_diagnoses", {})


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * FROM main.device_log",
        "SELECT * FROM diagnosis_record",
        "SELECT * FROM knowledge_document",
        "SELECT * FROM sqlite_master",
        "SELECT * FROM pragma_table_info('device')",
        "SELECT load_extension('anything') FROM iot_devices",
        "SELECT randomblob(100000000) FROM iot_devices",
        "WITH iot_logs AS (SELECT * FROM main.device_log) SELECT * FROM iot_logs",
        "WITH iot_devices AS (SELECT * FROM device) SELECT * FROM iot_devices",
        "SELECT d.device_id FROM iot_devices d UNION ALL SELECT device_id FROM device_log",
    ],
)
def test_unauthorized_sources_and_functions_rejected(repository, sql):
    with pytest.raises(Text2SQLError, match="未授权") as error:
        execute_readonly(repository, sql, {}, device_id="test_fresh")
    assert error.value.code == "SQL_QUERY_REJECTED"


@pytest.mark.parametrize(
    "sql",
    [
        "DELETE FROM iot_logs",
        "PRAGMA query_only = OFF",
        "ATTACH DATABASE ':memory:' AS other",
        "SELECT * FROM iot_logs; DELETE FROM device_log;",
        "SELECT 1",
        "EXPLAIN QUERY PLAN SELECT * FROM iot_logs",
    ],
)
def test_writes_and_multiple_statements_never_execute(repository, sql):
    before = repository.get_device_logs("test_fresh")
    with pytest.raises(Text2SQLError):
        execute_readonly(repository, sql, {})
    assert repository.get_device_logs("test_fresh") == before


def test_scoped_count_cte_and_empty_result(repository):
    result = execute_readonly(
        repository,
        """
        WITH errors AS (SELECT * FROM iot_logs WHERE level = :level)
        SELECT count(*) AS error_count FROM errors
    """,
        {"level": "ERROR"},
        device_id="test_fresh",
    )
    assert result["rows"] == [{"error_count": 1}]
    empty = execute_readonly(repository, "SELECT * FROM iot_logs", {}, device_id="absent")
    assert empty["rows"] == [] and not empty["truncated"]


def test_row_cell_and_byte_limits_report_truncation(repository):
    result = execute_readonly(repository, "SELECT * FROM iot_logs ORDER BY id", {}, max_rows=1)
    assert len(result["rows"]) == 1 and result["truncated"]
    repository.add_log("test_fresh", {"message": "长" * 3000})
    result = execute_readonly(
        repository,
        "SELECT message FROM iot_logs ORDER BY id DESC",
        {},
        device_id="test_fresh",
        max_rows=1,
    )
    assert len(result["rows"][0]["message"]) == 2000 and result["cells_truncated"]
    for _ in range(10):
        repository.add_log("test_fresh", {"message": "长" * 2000})
    result = execute_readonly(
        repository, "SELECT message FROM iot_logs", {}, device_id="test_fresh"
    )
    assert result["returned"] < 12 and result["truncated"]


def test_expensive_aggregate_is_interrupted(repository):
    with pytest.raises(Text2SQLError) as error:
        execute_readonly(
            repository,
            """
            WITH RECURSIVE seq(x) AS (
                SELECT 1 UNION ALL SELECT x+1 FROM seq WHERE x < 100000000
            ) SELECT count(*) AS n FROM seq CROSS JOIN iot_devices
        """,
            {},
            timeout_seconds=0.01,
        )
    assert error.value.code == "SQL_QUERY_TIMEOUT"


def test_duplicate_columns_and_blob_results_rejected(repository):
    for sql in (
        "SELECT device_id AS x, name AS x FROM iot_devices",
        "SELECT CAST(name AS BLOB) AS name FROM iot_devices",
    ):
        with pytest.raises(Text2SQLError) as error:
            execute_readonly(repository, sql, {})
        assert error.value.code == "SQL_QUERY_INVALID"


def test_natural_language_generation_and_clock_parameters(repository):
    client = FakeLLM(
        {
            "plan": {
                "metric": "log_entries",
                "aggregations": ["count"],
                "window": {"kind": "today"},
                "filters": {"level": "ERROR"},
            },
        }
    )
    result = query_iot_data(repository, "今天有多少条错误日志", "test_fresh", llm_client=client)
    assert result["rows"] == [{"count": 1}]
    start = datetime.fromisoformat(result["parameters"]["query_start"])
    assert start.hour == 16 and start.minute == 0
    assert result["generation_attempts"] == 1 and result["input_tokens"] == 10
    assert result["execution_mode"] == "query_plan"


def test_one_plan_correction_without_leaking_rows_to_model(repository):
    client = FakeLLM(
        {"plan": {"metric": "devices", "aggregations": ["avg"], "window": {"kind": "current"}}},
        {"plan": {"metric": "devices", "aggregations": ["count"], "window": {"kind": "current"}}},
    )
    result = query_iot_data(repository, "设备数量", "test_fresh", llm_client=client)
    assert result["rows"] == [{"count": 1}] and result["generation_attempts"] == 2
    assert "只支持 count" in client.calls[1][-1]["error"]
    assert result["input_tokens"] == 20


def test_raw_sql_model_response_never_executes(repository, monkeypatch):
    import iot_diagnosis.text2sql as module

    executed = []
    monkeypatch.setattr(module, "execute_readonly", lambda *args, **kwargs: executed.append(args))
    client = FakeLLM(*[{"sql": "SELECT * FROM device_log", "parameters": {}}] * 2)
    with pytest.raises(Text2SQLError) as error:
        query_iot_data(repository, "日志", llm_client=client)
    assert error.value.code == "TEXT2SQL_PLAN_INVALID" and len(client.calls) == 2
    assert not executed


def test_second_invalid_plan_stops_generation(repository):
    client = FakeLLM(
        *[{"plan": {"metric": "devices", "aggregations": ["avg"], "window": {"kind": "current"}}}]
        * 2
    )
    with pytest.raises(Text2SQLError) as error:
        query_iot_data(repository, "设备数量", llm_client=client)
    assert error.value.code == "TEXT2SQL_PLAN_INVALID" and len(client.calls) == 2


def test_clarification_missing_model_and_model_failure(repository):
    client = FakeLLM({"clarification": "请提供故障率的判定口径", "plan": None})
    with pytest.raises(Text2SQLError) as error:
        query_iot_data(repository, "故障率", llm_client=client)
    assert error.value.code == "TEXT2SQL_CLARIFICATION_REQUIRED"
    with pytest.raises(Text2SQLError) as error:
        query_iot_data(repository, "设备数量", llm_client=SimpleNamespace(available=False))
    assert error.value.code == "LLM_NOT_CONFIGURED"

    def fail(*args):
        raise LLMClientError("LLM_REQUEST_FAILED")

    with pytest.raises(Text2SQLError) as error:
        query_iot_data(
            repository, "设备数量", llm_client=SimpleNamespace(available=True, text2sql=fail)
        )
    assert error.value.code == "LLM_REQUEST_FAILED"


def test_prompt_contains_schema_and_business_semantics(monkeypatch):
    captured = {}

    def capture(self, system, user):
        captured.update(system=system, user=user)
        return LLMResponse({}, 0, 0, 0)

    monkeypatch.setattr(DiagnosisLLMClient, "_complete_json", capture)
    DiagnosisLLMClient("key", "http://model", "model").text2sql(
        "今天日志", PLAN_CONTRACT, "test_fresh", {"now_utc": "clock"}, 480
    )
    assert "日志条数不等于断线次数" in captured["system"]
    assert captured["user"]["device_id"] == "test_fresh"
    assert "plan_schema" in captured["user"]["plan_contract"]


@pytest.mark.asyncio
async def test_mcp_tool_exposed_readonly_and_returns_data(repository, monkeypatch):
    from iot_mcp import server

    monkeypatch.setattr(server, "diagnosis_repository", repository)
    response_plan = {
        "plan": {"metric": "devices", "aggregations": ["count"], "window": {"kind": "current"}}
    }
    client = FakeLLM(response_plan)
    monkeypatch.setattr(DiagnosisLLMClient, "from_env", classmethod(lambda cls: client))
    async with Client(server.mcp) as mcp_client:
        response = await mcp_client.list_tools()
        tools = response.tools if hasattr(response, "tools") else response["tools"]
        tool = next(
            t for t in tools if (t["name"] if isinstance(t, dict) else t.name) == "query_iot_data"
        )
        annotations = tool["annotations"] if isinstance(tool, dict) else tool.annotations
        assert (
            annotations["readOnlyHint"]
            if isinstance(annotations, dict)
            else annotations.read_only_hint
        )
        response = await mcp_client.call_tool(
            "query_iot_data", {"query": "设备数量", "device_id": "test_fresh"}
        )
        content = response.content if hasattr(response, "content") else response["content"]
        text = content[0].text if hasattr(content[0], "text") else content[0]["text"]
        result = json.loads(text)
        assert result["ok"] and result["data"]["rows"] == [{"count": 1}]
    # Also verify the existing result envelope, which the backend consumes.
    client.responses.append(response_plan)
    result = server.query_iot_data("设备数量", "test_fresh")
    assert result["ok"] and result["data"]["rows"] == [{"count": 1}]
    monkeypatch.setattr(
        DiagnosisLLMClient, "from_env", classmethod(lambda cls: SimpleNamespace(available=False))
    )
    failure = server.query_iot_data("设备数量", "test_fresh")
    assert not failure["ok"] and failure["error"]["code"] == "LLM_NOT_CONFIGURED"
