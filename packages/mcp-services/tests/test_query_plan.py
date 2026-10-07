"""Golden query results verify analytics meaning, not just SQL executability."""

from datetime import datetime, timedelta, timezone

import pytest

from iot_diagnosis.llm import LLMResponse
from iot_diagnosis.query_plan import QueryPlanError, compile_plan
from iot_diagnosis.repository import DiagnosisRepository
from iot_diagnosis.text2sql import Text2SQLError, execute_readonly, query_iot_data

NOW = datetime(2026, 10, 7, 2, 30, tzinfo=timezone.utc)


@pytest.fixture
def golden(tmp_path, monkeypatch):
    import iot_diagnosis.text2sql as module

    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW.astimezone(tz or timezone.utc)

    monkeypatch.setattr(module, "datetime", FixedDateTime)
    repo = DiagnosisRepository(str(tmp_path / "golden.db"), offline_after_seconds=120)
    for device in ("A", "B", "C"):
        repo.upsert_device_metadata(device, {"device_type": "golden", "firmware_version": "v1"})
    repo.apply_status("A", {"online": True}, NOW.isoformat())
    repo.apply_status("B", {"online": True}, (NOW - timedelta(hours=1)).isoformat())
    samples = [
        ("A", 24, 20),
        ("A", 2, 10),
        ("A", 1, 30),
        ("A", 0.5, None),
        ("A", 25, 999),
        ("A", 0, 888),
        ("B", 1, 50),
    ]
    for device, hours, temp in samples:
        repo.append_telemetry(
            device,
            {"temperature": temp, "rssi": -70, "uptime": 100},
            (NOW - timedelta(hours=hours)).isoformat(),
        )
    # Telemetry updates freshness; restore the desired latest-state fixtures.
    repo.apply_status("A", {"online": True}, NOW.isoformat())
    repo.apply_status("B", {"online": True}, (NOW - timedelta(hours=1)).isoformat())
    for device, level, log_module, hours in (
        ("A", "ERROR", "mqtt", 3),
        ("A", "ERROR", "mqtt", 1),
        ("A", "INFO", "mqtt", 1),
        ("B", "ERROR", "sensor", 1),
    ):
        repo.add_log(
            device,
            {
                "level": level,
                "module": log_module,
                "message": "disconnect retry",
                "timestamp": (NOW - timedelta(hours=hours)).isoformat(),
            },
        )
    for device in ("A", "B"):
        item = repo.save_diagnosis_error(device, "failure", "MODEL_ERROR", "failed diagnosis")
        with repo._connect() as db:
            db.execute(
                "UPDATE diagnosis_record SET created_at = ? WHERE diagnosis_id = ?",
                ((NOW - timedelta(hours=1)).isoformat(), item["diagnosis_id"]),
            )
    return repo


def plan(metric="temperature", **overrides):
    return {
        "metric": metric,
        "aggregations": ["avg", "max"],
        "window": {"kind": "last_hours", "hours": 24},
        **overrides,
    }


def run(repo, raw, scope=None, offset=480, max_rows=100):
    compiled = compile_plan(
        raw, device_id=scope, now=NOW, utc_offset_minutes=offset, max_rows=max_rows
    )
    result = execute_readonly(
        repo,
        compiled.sql,
        compiled.parameters,
        device_id=compiled.device_id,
        now=NOW,
        max_rows=compiled.limit,
    )
    return compiled, result


def test_temperature_golden_window_and_null_samples(golden):
    compiled, result = run(golden, plan(aggregations=["avg", "min", "max", "count"]), "A")
    assert result["rows"] == [{"avg": 20, "min": 10, "max": 30, "count": 3, "sample_count": 3}]
    assert compiled.parameters["query_start"] == (NOW - timedelta(hours=24)).isoformat()
    assert compiled.parameters["query_end"] == NOW.isoformat()
    # Includes exact start; excludes exact end, old sample and null temperature.
    _, samples = run(golden, plan("telemetry_samples", aggregations=["count"]), "A")
    assert samples["rows"] == [{"count": 4}]


def test_metadata_enrichment_cannot_multiply_measurements_by_logs(golden):
    compiled, result = run(
        golden,
        plan(
            group_by=["device_id"],
            filters={"device_type": "golden"},
            sort={"key": "avg", "direction": "desc"},
        ),
    )
    assert result["rows"] == [
        {"device_id": "B", "avg": 50, "max": 50, "sample_count": 1},
        {"device_id": "A", "avg": 20, "max": 30, "sample_count": 3},
    ]
    assert result["sources"] == ["iot_devices", "iot_telemetry"]
    assert "iot_logs" not in compiled.sql


def test_hourly_buckets_use_business_timezone(golden):
    _, result = run(golden, plan(bucket="hour", sort={"key": "time", "direction": "asc"}), "A")
    assert result["rows"] == [
        {"bucket": "2026-10-06 10:00:00", "avg": 20, "max": 20, "sample_count": 1},
        {"bucket": "2026-10-07 08:00:00", "avg": 10, "max": 10, "sample_count": 1},
        {"bucket": "2026-10-07 09:00:00", "avg": 30, "max": 30, "sample_count": 1},
        {"bucket": "2026-10-07 10:00:00", "avg": None, "max": None, "sample_count": 0},
    ]


def test_local_today_and_yesterday_have_correct_utc_boundaries(golden):
    today, _ = run(golden, plan(window={"kind": "today"}), "A")
    yesterday, _ = run(golden, plan(window={"kind": "yesterday"}), "A")
    assert today.parameters["query_start"] == "2026-10-06T16:00:00+00:00"
    assert today.parameters["query_end"] == NOW.isoformat()
    assert yesterday.parameters["query_start"] == "2026-10-05T16:00:00+00:00"
    assert yesterday.parameters["query_end"] == "2026-10-06T16:00:00+00:00"
    western, _ = run(golden, plan(window={"kind": "today"}), "A", offset=-300)
    assert western.parameters["query_start"] == "2026-10-06T05:00:00+00:00"


def test_explicit_range_interprets_naive_times_as_business_time(golden):
    compiled, result = run(
        golden,
        plan(
            window={"kind": "range", "start": "2026-10-07T08:30:00", "end": "2026-10-07T09:30:00"}
        ),
        "A",
    )
    assert compiled.parameters["query_start"] == "2026-10-07T00:30:00+00:00"
    assert result["rows"] == [{"avg": 10, "max": 10, "sample_count": 1}]


def test_log_ranking_counts_matching_rows_and_filters_are_bound(golden):
    _, result = run(
        golden,
        plan(
            "log_entries",
            aggregations=["count"],
            group_by=["device_id"],
            filters={"level": "ERROR", "device_type": "golden"},
            sort={"key": "count", "direction": "desc"},
        ),
    )
    assert result["rows"] == [{"device_id": "A", "count": 2}, {"device_id": "B", "count": 1}]
    compiled, result = run(
        golden, plan("log_entries", aggregations=["count"], filters={"module": "mqtt' OR 1=1 --"})
    )
    assert result["rows"] == [{"count": 0}]
    assert "OR 1=1" not in compiled.sql


@pytest.mark.parametrize("metric", ["telemetry_devices", "log_devices", "diagnosed_devices"])
def test_distinct_devices_are_not_confused_with_record_counts(golden, metric):
    _, result = run(golden, plan(metric, aggregations=["count"], filters={"device_type": "golden"}))
    assert result["rows"] == [{"count": 2}]
    _, logs = run(
        golden, plan("log_entries", aggregations=["count"], filters={"device_type": "golden"})
    )
    assert logs["rows"] == [{"count": 4}]


def test_diagnosis_failure_count_and_current_online_count(golden):
    _, result = run(
        golden,
        plan(
            "diagnosis_records",
            aggregations=["count"],
            filters={"diagnosis_status": "failed", "device_type": "golden"},
        ),
    )
    assert result["rows"] == [{"count": 2}]
    for metric, count in (("devices", 3), ("online_devices", 1), ("offline_devices", 2)):
        _, result = run(
            golden,
            plan(
                metric,
                aggregations=["count"],
                window={"kind": "current"},
                filters={"device_type": "golden"},
            ),
        )
        assert result["rows"] == [{"count": count}]


def test_details_have_stable_order_and_enforce_caller_limit(golden):
    compiled, result = run(
        golden, plan("log_entries", mode="details", aggregations=[], limit=200), "A", max_rows=1
    )
    assert compiled.limit == 1 and result["returned"] == 1 and result["truncated"]
    assert result["rows"][0]["device_id"] == "A"
    _, devices = run(
        golden,
        plan(
            "devices",
            mode="details",
            aggregations=[],
            window={"kind": "current"},
            filters={"device_type": "golden"},
        ),
    )
    assert [row["device_id"] for row in devices["rows"]] == ["A", "B", "C"]
    assert [row["online"] for row in devices["rows"]] == [1, 0, 0]


@pytest.mark.parametrize(
    "overrides",
    [
        {"metric": "disconnect_count"},
        {"sql": "SELECT 1"},
        {"joins": ["iot_logs"]},
        {"aggregations": ["sum"]},
        {"aggregations": ["avg", "avg"]},
        {"group_by": ["module"]},
        {"group_by": ["device_id", "device_id"]},
        {"filters": {"level": "ERROR"}},
        {"filters": {"value_min": 30, "value_max": 10}},
        {"filters": {"value_min": float("nan")}},
        {"filters": {"unknown_field": "x"}},
        {"window": {"kind": "last_hours", "hours": True}},
        {"window": {"kind": "last_hours", "hours": "24"}},
        {"window": {"kind": "last_hours", "hours": 0}},
        {"window": {"kind": "today", "hours": 24}},
        {"window": {"kind": "last_hours"}},
        {"window": {"kind": "range", "start": "bad", "end": "bad"}},
        {"window": {"kind": "range", "start": "2026-10-07", "end": "2026-10-06"}},
        {"mode": "details"},
        {"sort": {"key": "time"}},
        {"limit": 201},
    ],
)
def test_invalid_plans_rejected_before_sql_execution(overrides):
    with pytest.raises(QueryPlanError):
        compile_plan(
            plan(**overrides), device_id=None, now=NOW, utc_offset_minutes=480, max_rows=100
        )


def test_history_online_and_device_scope_changes_require_clarification():
    for raw in (
        plan("online_devices", aggregations=["count"]),
        plan(device_id="B"),
        plan(window={"kind": "range", "start": "2026-10-07", "end": "2026-10-09"}),
    ):
        with pytest.raises(QueryPlanError) as error:
            compile_plan(raw, device_id="A", now=NOW, utc_offset_minutes=480, max_rows=100)
        assert error.value.code == "TEXT2SQL_CLARIFICATION_REQUIRED"


def test_empty_aggregates_keep_zero_sample_evidence(golden):
    _, result = run(golden, plan(), "C")
    assert result["rows"] == [{"avg": None, "max": None, "sample_count": 0}]


class PlanLLM:
    available = True

    def __init__(self, raw):
        self.raw = raw
        self.calls = 0

    def text2sql(self, *args):
        self.calls += 1
        return LLMResponse({"plan": self.raw}, 1, 10, 5)


def test_natural_language_pipeline_returns_verified_plan_and_window(golden):
    result = query_iot_data(
        golden, "查询 A 最近 24 小时平均和最高温度", "A", llm_client=PlanLLM(plan())
    )
    assert result["rows"] == [{"avg": 20, "max": 30, "sample_count": 3}]
    assert result["query_plan"]["device_id"] == "A"
    assert result["metric_definition"]["unit"] == "°C"
    assert result["time_window"]["bounds"] == "[start, end)"


@pytest.mark.parametrize(
    "question",
    ["A 最近一天掉线多少次", "根据日志统计 A 的掉线次数", "How many disconnects did A have?"],
)
def test_disconnect_events_cannot_be_silently_replaced_by_log_counts(golden, question):
    client = PlanLLM(plan("log_entries", aggregations=["count"]))
    with pytest.raises(Text2SQLError) as error:
        query_iot_data(golden, question, "A", llm_client=client)
    assert error.value.code == "TEXT2SQL_CLARIFICATION_REQUIRED" and client.calls == 0


def test_explicit_disconnect_log_count_is_a_valid_record_query(golden):
    client = PlanLLM(
        plan(
            "log_entries",
            aggregations=["count"],
            window={"kind": "all"},
            filters={"level": "ERROR", "message_contains": "disconnect"},
        )
    )
    result = query_iot_data(golden, "统计 A 的掉线日志条数", "A", llm_client=client)
    assert result["rows"] == [{"count": 2}] and client.calls == 1


def test_scope_conflict_is_not_repaired_or_executed(golden):
    client = PlanLLM(plan(device_id="B"))
    with pytest.raises(Text2SQLError) as error:
        query_iot_data(golden, "A 的温度", "A", llm_client=client)
    assert error.value.code == "TEXT2SQL_CLARIFICATION_REQUIRED" and client.calls == 1


def test_invalid_model_json_is_repaired_once_before_querying(golden):
    from iot_diagnosis.llm import LLMClientError

    class InvalidFirst(PlanLLM):
        def text2sql(self, *args):
            if self.calls == 0:
                self.calls += 1
                raise LLMClientError("LLM_RESPONSE_INVALID")
            assert "JSON" in args[-1]["error"]
            return super().text2sql(*args)

    client = InvalidFirst(plan())
    result = query_iot_data(golden, "A 的过去24小时温度", "A", llm_client=client)
    assert result["generation_attempts"] == 2
    assert result["rows"] == [{"avg": 20, "max": 30, "sample_count": 3}]
    assert client.calls == 2


def test_invalid_model_json_never_retries_more_than_once(golden, monkeypatch):
    from iot_diagnosis.llm import LLMClientError

    class AlwaysInvalid(PlanLLM):
        def text2sql(self, *args):
            self.calls += 1
            raise LLMClientError("LLM_RESPONSE_INVALID")

    def forbidden_execute(*args, **kwargs):
        pytest.fail("invalid JSON must not reach SQLite")

    monkeypatch.setattr("iot_diagnosis.text2sql.execute_readonly", forbidden_execute)
    client = AlwaysInvalid(plan())
    with pytest.raises(Text2SQLError) as error:
        query_iot_data(golden, "A 的温度", "A", llm_client=client)
    assert error.value.code == "LLM_RESPONSE_INVALID" and client.calls == 2


@pytest.mark.parametrize(
    "raw", [plan("disconnect_count", aggregations=["count"]), plan("uptime", aggregations=["sum"])]
)
def test_unsupported_meaning_cannot_be_repaired_into_another_metric(golden, raw):
    client = PlanLLM(raw)
    with pytest.raises(Text2SQLError) as error:
        query_iot_data(golden, "查询所需指标", "A", llm_client=client)
    assert error.value.code == "TEXT2SQL_CLARIFICATION_REQUIRED" and client.calls == 1
