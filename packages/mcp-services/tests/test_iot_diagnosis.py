import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from mcp.client import Client

from iot_diagnosis import server
from iot_diagnosis.auth import StaticBearerTokenVerifier, auth_configuration
from iot_diagnosis.diagnosis import _profile
from iot_diagnosis.embeddings import (
    HashEmbeddingProvider,
    OpenAICompatibleEmbeddingProvider,
)
from iot_diagnosis.external import QdrantVectorStore
from iot_diagnosis.ingestion import ingest_text
from iot_diagnosis.llm import LLMResponse
from iot_diagnosis.mqtt import MQTTIngestor
from iot_diagnosis.repository import DiagnosisRepository, iso
from iot_diagnosis.reranker import RemoteReranker
from iot_diagnosis.retrieval import search_knowledge
from iot_diagnosis.router import route_query


@pytest.mark.parametrize(
    ("evidence", "fault_name"),
    [
        ("MQTT auth failed: bad user name", "MQTT 认证失败"),
        ("MQTT Broker unreachable, connection refused", "MQTT Broker 不可达"),
        ("network latency and packet loss", "网络延迟或丢包异常"),
        ("WiFi disconnected", "WiFi 连接断开"),
        ("WiFi RSSI -85", "WiFi 弱信号"),
        ("sensor read failed, no data", "传感器读取失败"),
        ("sensor drift out of range", "传感器数据异常"),
        ("heap low, out of memory", "设备内存不足"),
        ("watchdog reset and reboot", "设备异常重启"),
        ("MQTT keep alive timeout", "MQTT Keep Alive Timeout"),
    ],
)
def test_fallback_diagnosis_profiles_cover_core_fault_scenarios(evidence, fault_name) -> None:
    profile = _profile(
        evidence,
        {"mqtt_status": "connected", "rssi": -47, "temperature": 26.3},
    )
    assert profile["fault_name"] == fault_name
    assert profile["cause"]
    assert profile["solutions"]


def test_fallback_router_selects_sources_for_auth_latency_and_runtime() -> None:
    disabled_llm = SimpleNamespace(available=False)
    state = {"mqtt_status": "connected", "rssi": -47, "temperature": 26.3}

    auth = route_query(
        "Broker unauthorized: bad user name",
        state,
        [],
        llm_client=disabled_llm,
    )
    latency = route_query(
        "network latency and packet loss",
        state,
        [],
        llm_client=disabled_llm,
    )
    runtime = route_query(
        "watchdog reset after heap OOM",
        state,
        [],
        llm_client=disabled_llm,
    )

    assert "mqtt_docs" in auth.sources
    assert "wifi_docs" in latency.sources
    assert "device_docs" in runtime.sources


async def test_core_tools_are_discoverable_and_callable(tmp_path, monkeypatch) -> None:
    repository = DiagnosisRepository(str(tmp_path / "diagnosis.db"))
    monkeypatch.setattr(server, "repository", repository)

    async with Client(server.mcp) as client:
        tools = await client.list_tools()
        listed = tools.tools if hasattr(tools, "tools") else tools["tools"]
        assert {
            tool[0]
            if isinstance(tool, tuple)
            else tool["name"]
            if isinstance(tool, dict)
            else tool.name
            for tool in listed
        } == {
            "diagnose_fault",
            "list_devices",
            "get_device_status",
            "get_device_logs",
            "get_diagnosis_trace",
            "list_diagnoses",
            "list_knowledge_documents",
            "list_fault_cases",
            "delete_fault_case",
            "ingest_knowledge_text",
            "search_knowledge",
            "search_fault_cases",
            "add_verified_fault_case",
            "delete_knowledge_document",
            "rebuild_vector_index",
        }

        status = await client.call_tool("get_device_status", {"device_id": "ESP32_05"})
        assert status.structured_content["data"]["rssi"] == -47

        devices = await client.call_tool("list_devices", {"device_type": "ESP32", "online": True})
        assert devices.structured_content["data"]["total"] == 1
        assert devices.structured_content["data"]["items"][0]["device_id"] == "ESP32_05"

        documents = await client.call_tool("list_knowledge_documents", {"source": "mqtt_docs"})
        assert documents.structured_content["data"]["total"] == 1
        assert documents.structured_content["data"]["items"][0]["document_id"] == ("MQTT_DOC_03")

        logs = await client.call_tool(
            "get_device_logs", {"device_id": "ESP32_05", "level": "ERROR"}
        )
        assert "keep alive timeout" in logs.structured_content["data"]["logs"][0]["message"]

        failed_trace = repository.save_diagnosis_error(
            "MISSING", "why offline", "DEVICE_NOT_FOUND", "missing"
        )
        diagnoses = await client.call_tool("list_diagnoses", {"status": "failed", "limit": 10})
        assert diagnoses.structured_content["data"]["total"] == 1
        assert (
            diagnoses.structured_content["data"]["items"][0]["diagnosis_id"]
            == (failed_trace["diagnosis_id"])
        )


def test_inventory_pagination_and_document_aggregation(tmp_path) -> None:
    repository = DiagnosisRepository(str(tmp_path / "diagnosis.db"))
    repository.upsert_status(
        "ESP32_06",
        {
            "device_type": "ESP32",
            "name": "节点 06",
            "online": False,
            "wifi": "disconnected",
            "mqtt": "disconnected",
        },
    )
    repository.replace_knowledge_document(
        source="mqtt_docs",
        document_id="multi-chunk",
        title="Multi Chunk Guide",
        chunks=["a" * 300, "b" * 400],
        device_type="ESP32",
    )

    devices = repository.list_devices(device_type="ESP32", online=False, limit=1)
    documents = repository.list_knowledge_documents(source="mqtt_docs", limit=1, offset=1)

    assert devices["total"] == 1
    assert devices["items"][0]["device_id"] == "ESP32_06"
    assert documents["total"] == 2
    assert documents["items"][0]["document_id"] == "multi-chunk"
    assert documents["items"][0]["title"] == "Multi Chunk Guide"
    assert documents["items"][0]["chunk_count"] == 2
    assert documents["items"][0]["content_chars"] == 700


def test_reingesting_legacy_document_replaces_unsuffixed_chunk(tmp_path) -> None:
    repository = DiagnosisRepository(str(tmp_path / "diagnosis.db"))

    repository.replace_knowledge_document(
        source="mqtt_docs",
        document_id="MQTT_DOC_03",
        title="Replacement Guide",
        chunks=["replacement" * 30],
        device_type="ESP32",
    )

    rows = [
        item
        for item in repository.knowledge_documents(["mqtt_docs"])
        if item["document_id"] == "MQTT_DOC_03"
    ]
    assert [item["source_id"] for item in rows] == ["MQTT_DOC_03#0000"]
    assert rows[0]["title"] == "Replacement Guide"


async def test_router_retrieval_diagnosis_and_traceability(tmp_path, monkeypatch) -> None:
    repository = DiagnosisRepository(str(tmp_path / "diagnosis.db"))
    monkeypatch.setattr(server, "repository", repository)
    # 案例库不再随种子内置，这里补一条案例以验证 fault_cases 参与多源检索
    repository.add_verified_fault_case(
        {
            "device_id": "ESP32_05",
            "fault_type": "mqtt_connection",
            "fault_name": "MQTT keep alive 超时",
            "symptoms": ["MQTT 频繁掉线"],
            "logs": ["MQTT keep alive timeout"],
            "cause": "Keep Alive 配置过短且网络抖动",
            "solution": "重连 Broker 并调大 Keep Alive",
            "verified_by": "test",
        }
    )

    async with Client(server.mcp) as client:
        realtime = await client.call_tool(
            "diagnose_fault",
            {"device_id": "ESP32_05", "query": "设备当前 RSSI 是多少？"},
        )
        realtime_data = realtime.structured_content["data"]
        assert realtime_data["route"]["router"] == "rule"
        assert realtime_data["route"]["retrieval_required"] is False
        assert realtime_data["fault_type"] == "realtime_state"
        assert realtime_data["answer"] == "设备当前 RSSI 为 -47 dBm"
        assert realtime_data["realtime_state"]["device_id"] == "ESP32_05"
        assert realtime_data["observability"]["llm_latency_ms"] == 0

        realtime_trace = await client.call_tool(
            "get_diagnosis_trace",
            {"diagnosis_id": realtime_data["diagnosis_id"]},
        )
        assert (
            realtime_trace.structured_content["data"]["result"]["answer"]
            == (realtime_data["answer"])
        )

        mqtt_state = await client.call_tool(
            "diagnose_fault",
            {"device_id": "ESP32_05", "query": "当前 MQTT 连接状态是什么？"},
        )
        assert mqtt_state.structured_content["data"]["answer"] == (
            "设备当前 MQTT 状态为 disconnected"
        )

        diagnosis = await client.call_tool(
            "diagnose_fault",
            {
                "device_id": "ESP32_05",
                "query": "设备为什么一直断开 MQTT 连接？",
                "logs": ["MQTT disconnected", "MQTT keep alive timeout"],
            },
        )
        item = diagnosis.structured_content["data"]
        assert item["fault_type"] == "mqtt_connection"
        assert item["route"]["router"] in {"semantic", "heuristic_fallback"}
        assert {source["source_type"] for source in item["sources"]} >= {
            "fault_cases",
            "mqtt_docs",
        }
        assert item["observability"]["retrieval_count"] >= 2

        trace = await client.call_tool(
            "get_diagnosis_trace",
            {"diagnosis_id": item["diagnosis_id"]},
        )
        trace_data = trace.structured_content["data"]
        assert trace_data["route"]["router"] in {"semantic", "heuristic_fallback"}
        assert {context["source"] for context in trace_data["contexts"]} >= {
            "fault_cases",
            "mqtt_docs",
        }
        assert all("content" in context for context in trace_data["contexts"])
        assert trace_data["result"]["severity"] == item["severity"]
        assert trace_data["result"]["evidence"] == item["evidence"]


async def test_failed_diagnosis_is_queryable(tmp_path, monkeypatch) -> None:
    repository = DiagnosisRepository(str(tmp_path / "diagnosis.db"))
    monkeypatch.setattr(server, "repository", repository)

    async with Client(server.mcp) as client:
        failed = await client.call_tool(
            "diagnose_fault",
            {"device_id": "MISSING", "query": "why offline"},
        )
        diagnosis_id = failed.structured_content["error"]["diagnosis_id"]
        trace = await client.call_tool(
            "get_diagnosis_trace",
            {"diagnosis_id": diagnosis_id},
        )
        missing = await client.call_tool(
            "get_diagnosis_trace",
            {"diagnosis_id": "DIA_MISSING"},
        )

    assert trace.structured_content["data"]["observability"]["error"] == "DEVICE_NOT_FOUND"
    assert missing.structured_content["error"]["code"] == "DIAGNOSIS_NOT_FOUND"


async def test_verified_case_gate_and_dynamic_retrieval(tmp_path, monkeypatch) -> None:
    repository = DiagnosisRepository(str(tmp_path / "diagnosis.db"))
    monkeypatch.setattr(server, "repository", repository)
    payload = {
        "device_id": "ESP32_05",
        "fault_type": "wifi",
        "fault_name": "WiFi 弱信号",
        "symptoms": ["频繁重连"],
        "logs": ["RSSI -85 dBm"],
        "cause": "接入点距离过远",
        "solution": "调整天线并缩短距离",
    }

    async with Client(server.mcp) as client:
        denied = await client.call_tool(
            "add_verified_fault_case",
            {**payload, "verified": False, "verified_by": "operator"},
        )
        assert denied.structured_content["error"]["code"] == "CASE_NOT_VERIFIED"

        added = await client.call_tool(
            "add_verified_fault_case",
            {**payload, "verified": True, "verified_by": "operator"},
        )
        assert added.structured_content["data"]["indexed"] is False
        assert added.structured_content["data"]["sync_status"] == "local_only"

        cases = await client.call_tool(
            "search_fault_cases",
            {"query": "WiFi RSSI -85", "device_type": "ESP32", "fault_type": "wifi"},
        )
        assert cases.structured_content["data"]["results"][0]["fault_name"] == "WiFi 弱信号"


def test_vector_search_without_realtime_state_does_not_fail(tmp_path, monkeypatch) -> None:
    repository = DiagnosisRepository(str(tmp_path / "diagnosis.db"))
    monkeypatch.setattr(
        repository,
        "vector_search",
        lambda *_args: [
            {
                "source": "mqtt_docs",
                "id": "VECTOR_MQTT_01",
                "title": "MQTT vector result",
                "content": "MQTT keep alive timeout",
                "score": 0.9,
            }
        ],
    )

    result = search_knowledge(repository, "MQTT keep alive timeout", sources=[])

    assert result["results"]
    assert all(item["source"] != "realtime_db" for item in result["results"])


def test_qdrant_existing_collection_is_not_recreated(monkeypatch) -> None:
    requests = []

    def fake_request(self, method, path, payload=None):
        requests.append((method, path, payload))
        return {"status": "ok"}

    monkeypatch.setattr(QdrantVectorStore, "_request", fake_request)

    QdrantVectorStore("http://qdrant:6333", "iot_diagnosis_knowledge")

    assert requests == [("GET", "/collections/iot_diagnosis_knowledge", None)]


def test_hash_embeddings_are_deterministic_and_collection_size_is_checked(monkeypatch) -> None:
    provider = HashEmbeddingProvider(32)
    assert provider.embed("MQTT timeout") == provider.embed("MQTT timeout")
    assert len(provider.embed("MQTT timeout")) == 32

    monkeypatch.setattr(
        QdrantVectorStore,
        "_request",
        lambda *_args, **_kwargs: {"result": {"config": {"params": {"vectors": {"size": 64}}}}},
    )
    try:
        QdrantVectorStore("http://qdrant:6333", "knowledge", provider)
    except ValueError as exc:
        assert str(exc) == "QDRANT_COLLECTION_DIMENSIONS_MISMATCH"
    else:
        raise AssertionError("dimension mismatch was not rejected")


def test_remote_embedding_adds_query_instruction(monkeypatch) -> None:
    captured = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return json.dumps({"data": [{"index": 0, "embedding": [0.25, 0.75]}]}).encode()

    def fake_urlopen(request, timeout):
        captured["payload"] = json.loads(request.data)
        captured["timeout"] = timeout
        return Response()

    monkeypatch.setenv("DIAGNOSIS_EMBEDDING_QUERY_INSTRUCTION", "Retrieve IoT passages")
    monkeypatch.setattr("iot_diagnosis.embeddings.urlopen", fake_urlopen)
    provider = OpenAICompatibleEmbeddingProvider(
        api_key="local",
        base_url="http://models/v1",
        model="Qwen/Qwen3-Embedding-0.6B",
        dimensions=2,
        timeout_seconds=7,
    )

    assert provider.embed("MQTT timeout", is_query=True) == [0.25, 0.75]
    assert captured["payload"]["input"] == ["Instruct: Retrieve IoT passages\nQuery:MQTT timeout"]
    assert captured["timeout"] == 7


def test_remote_embedding_batch_orders_vectors_by_response_index(monkeypatch) -> None:
    captured = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return json.dumps(
                {
                    "data": [
                        {"index": 1, "embedding": [0.0, 1.0]},
                        {"index": 0, "embedding": [1.0, 0.0]},
                    ]
                }
            ).encode()

    def fake_urlopen(request, timeout):
        captured["payload"] = json.loads(request.data)
        return Response()

    monkeypatch.setattr("iot_diagnosis.embeddings.urlopen", fake_urlopen)
    provider = OpenAICompatibleEmbeddingProvider(
        api_key="local",
        base_url="http://models/v1",
        model="embedding-model",
        dimensions=2,
    )

    vectors = provider.embed_many(["first", "second"])

    assert captured["payload"]["input"] == ["first", "second"]
    assert vectors == [[1.0, 0.0], [0.0, 1.0]]


@pytest.mark.skip(reason="MySQL mirror removed in P0 architecture simplification")
def test_qdrant_batch_upsert_uses_one_embedding_and_one_write(monkeypatch) -> None:
    calls = []

    class BatchProvider:
        name = "batch"
        dimensions = 2

        def embed_many(self, texts, *, is_query=False):
            calls.append(("embed", texts))
            return [[1.0, 0.0] for _ in texts]

    monkeypatch.setattr(
        QdrantVectorStore,
        "_ensure_collection",
        lambda _self: None,
    )
    store = QdrantVectorStore("http://qdrant:6333", "knowledge", BatchProvider())
    monkeypatch.setattr(
        store,
        "_request",
        lambda method, path, payload=None: calls.append((method, path, payload)) or {},
    )

    store.upsert_many(
        [
            {"source": "mqtt_docs", "id": "a", "content": "first"},
            {"source": "mqtt_docs", "id": "b", "content": "second"},
        ]
    )

    assert calls[0] == ("embed", ["first", "second"])
    assert calls[1][0:2] == (
        "PUT",
        "/collections/knowledge/points?wait=true",
    )
    assert len(calls[1][2]["points"]) == 2


def test_remote_reranker_preserves_model_order_and_scores(monkeypatch) -> None:
    request_payload = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return json.dumps(
                {"results": [{"index": 1, "score": 0.99}, {"index": 0, "score": 0.1}]}
            ).encode()

    def fake_urlopen(request, **_kwargs):
        request_payload.update(json.loads(request.data.decode()))
        return Response()

    monkeypatch.setattr("iot_diagnosis.reranker.urlopen", fake_urlopen)
    candidates = [
        {"source": "wifi_docs", "id": "wifi", "content": "WiFi RSSI"},
        {"source": "mqtt_docs", "id": "mqtt", "content": "MQTT timeout"},
    ]

    ranked = RemoteReranker("http://models/rerank").rerank(
        "MQTT timeout", candidates, expected_source="mqtt_docs", top_k=2
    )

    assert [item["id"] for item in ranked] == ["mqtt", "wifi"]
    assert [item["score"] for item in ranked] == [0.99, 0.1]
    assert request_payload["top_n"] == len(candidates)


def test_remote_reranker_stabilizes_saturated_scores_with_retrieval_rank(monkeypatch) -> None:
    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return json.dumps(
                {
                    "results": [
                        {"index": 2, "score": 0.9995},
                        {"index": 0, "score": 0.9994},
                        {"index": 1, "score": 0.9993},
                    ]
                }
            ).encode()

    monkeypatch.setattr("iot_diagnosis.reranker.urlopen", lambda *_args, **_kwargs: Response())
    candidates = [
        {"source": "mqtt_docs", "id": "rrf-first", "content": "first"},
        {"source": "mqtt_docs", "id": "rrf-second", "content": "second"},
        {"source": "mqtt_docs", "id": "model-first", "content": "third"},
    ]

    ranked = RemoteReranker("http://models/rerank").rerank(
        "MQTT timeout", candidates, expected_source="mqtt_docs", top_k=3
    )

    # Qwen rank 权重为 2，仍是主排序；RRF 输入顺序负责稳定近饱和分数。
    assert [item["id"] for item in ranked] == ["model-first", "rrf-first", "rrf-second"]
    assert ranked[0]["score"] == 0.9995


def test_mqtt_style_status_and_log_updates(tmp_path) -> None:
    repository = DiagnosisRepository(str(tmp_path / "diagnosis.db"))
    repository.upsert_status(
        "ESP32_05",
        {
            "timestamp": iso(),
            "wifi": "connected",
            "mqtt": "connected",
            "rssi": -51,
            "temperature": 28.2,
            "uptime": 90000,
        },
    )
    repository.add_log(
        "ESP32_05",
        {"level": "INFO", "module": "mqtt", "message": "MQTT connected"},
    )
    assert repository.get_device_status("ESP32_05")["mqtt_status"] == "connected"
    assert repository.get_device_logs("ESP32_05", level="INFO")[0]["message"] == "MQTT connected"


def test_fault_topic_is_ingested_and_stale_heartbeat_marks_device_offline(tmp_path) -> None:
    repository = DiagnosisRepository(str(tmp_path / "diagnosis.db"), offline_after_seconds=30)
    stale = (datetime.now(timezone.utc) - timedelta(seconds=31)).isoformat()
    repository.upsert_status(
        "ESP32_STALE",
        {"timestamp": stale, "online": True, "mqtt": "connected", "wifi": "connected"},
    )
    assert repository.get_device_status("ESP32_STALE")["online"] is False
    assert repository.get_device_status("ESP32_STALE")["reported_online"] is True

    ingestor = MQTTIngestor(repository)
    ingestor._on_message(
        None,
        None,
        SimpleNamespace(
            topic="iot/ESP32_STALE/fault",
            payload=json.dumps(
                {
                    "fault_type": "mqtt_timeout",
                    "level": "ERROR",
                    "message": "MQTT keep alive timeout",
                }
            ).encode("utf-8"),
        ),
    )
    fault = repository.get_device_logs("ESP32_STALE", level="ERROR")[0]
    assert fault["module"] == "fault:mqtt_timeout"
    assert fault["message"] == "MQTT keep alive timeout"


async def test_configured_llm_drives_router_and_diagnosis(tmp_path, monkeypatch) -> None:
    repository = DiagnosisRepository(str(tmp_path / "diagnosis.db"))
    monkeypatch.setattr(server, "repository", repository)

    class FakeLLM:
        available = True

        def route(self, _query, _state, _logs):
            return LLMResponse(
                data={
                    "fault_type": "mqtt",
                    "need_retrieval": True,
                    "sources": ["fault_cases", "mqtt_docs", "realtime_db"],
                    "top_k": 4,
                },
                latency_ms=12.5,
                input_tokens=80,
                output_tokens=20,
            )

        def diagnose(self, _query, _state, _logs, _contexts):
            return LLMResponse(
                data={
                    "fault_type": "mqtt_connection",
                    "fault_name": "LLM 诊断的 MQTT 超时",
                    "cause": "客户端心跳间隔大于 Broker 超时",
                    "solutions": ["缩短心跳间隔", "检查 Broker 超时"],
                    "severity": "high",
                    "confidence": 0.91,
                    "requires_manual_inspection": False,
                },
                latency_ms=25.0,
                input_tokens=160,
                output_tokens=60,
            )

    monkeypatch.setattr(
        "iot_diagnosis.diagnosis.DiagnosisLLMClient.from_env",
        lambda: FakeLLM(),
    )
    async with Client(server.mcp) as client:
        result = await client.call_tool(
            "diagnose_fault",
            {"device_id": "ESP32_05", "query": "MQTT 为什么反复超时？"},
        )
    item = result.structured_content["data"]
    # 语义路由优先于 LLM Router；LLM Router 只在向量路由不可用时兜底
    assert item["route"]["router"] == "semantic"
    assert item["fault_name"] == "LLM 诊断的 MQTT 超时"
    assert item["observability"]["llm_latency_ms"] == 25.0
    assert item["observability"]["input_tokens"] == 160
    assert item["observability"]["output_tokens"] == 60


@pytest.mark.skip(reason="MySQL mirror removed in P0 architecture simplification")
def test_external_write_outbox_recovers_without_false_index_success(tmp_path) -> None:
    repository = DiagnosisRepository(str(tmp_path / "diagnosis.db"))

    class FlakyStore:
        def __init__(self):
            self.available = False

        def upsert_fault_case(self, _item):
            if not self.available:
                raise ConnectionError("mysql unavailable")

        def upsert(self, _item):
            if not self.available:
                raise ConnectionError("qdrant unavailable")
            return True

    mysql = FlakyStore()
    qdrant = FlakyStore()
    repository.external.mysql = mysql
    repository.external.qdrant = qdrant

    result = repository.add_verified_fault_case(
        {
            "device_id": "ESP32_05",
            "fault_type": "wifi",
            "fault_name": "Temporary external failure",
            "symptoms": ["disconnect"],
            "logs": ["RSSI -90"],
            "cause": "weak signal",
            "solution": "move access point",
            "verified_by": "operator",
        }
    )

    assert result["indexed"] is False
    assert result["sync_status"] == "pending"
    assert repository.external_sync_status()["pending"] == 2

    mysql.available = True
    qdrant.available = True
    retried = repository.retry_external_sync()

    assert retried == {"processed": 2, "delivered": 2, "failed": 0}
    assert repository.external_sync_status()["pending"] == 0


@pytest.mark.skip(reason="MySQL mirror removed in P0 architecture simplification")
def test_outbox_retry_delivers_after_recovery(tmp_path) -> None:
    repository = DiagnosisRepository(str(tmp_path / "diagnosis.db"))

    class FlakyStore:
        def __init__(self):
            self.available = False
            self.delivered: list[str] = []

        def __getattr__(self, operation):
            def call(*_args):
                if not self.available:
                    raise ConnectionError("external store unavailable")
                self.delivered.append(operation)
                return True

            return call

    mysql = FlakyStore()
    qdrant = FlakyStore()
    repository.external.mysql = mysql
    repository.external.qdrant = qdrant
    repository.external.configured["mysql"] = True
    repository.external.configured["qdrant"] = True

    # WP-08：启动不再执行全量快照同步；外部存储不可用时的写入进入 outbox
    trace = repository.save_diagnosis_error(
        "ESP32_05",
        "startup recovery test",
        "UPSTREAM_UNAVAILABLE",
        "temporary failure",
    )
    pending = repository.external_sync_status()
    assert pending["pending"] > 0
    assert pending["by_component"]["mysql"] > 0
    with repository._connect() as db:
        queued_operations = {
            row["operation"]
            for row in db.execute(
                "SELECT operation FROM external_sync_outbox WHERE completed_at IS NULL"
            )
        }
    assert "upsert_diagnosis" in queued_operations

    mysql.available = True
    qdrant.available = True
    retried = repository.retry_external_sync(limit=1000)

    assert retried["failed"] == 0
    assert retried["delivered"] == retried["processed"]
    assert repository.external_sync_status()["pending"] == 0
    assert "upsert_diagnosis" in mysql.delivered
    assert (
        repository.get_diagnosis_trace(trace["diagnosis_id"])["observability"]["error"]
        == "UPSTREAM_UNAVAILABLE"
    )


@pytest.mark.skip(reason="MySQL mirror removed in P0 architecture simplification")
def test_retry_reconnects_client_that_was_missing_at_startup(tmp_path, monkeypatch) -> None:
    repository = DiagnosisRepository(str(tmp_path / "diagnosis.db"))
    availability = {"ready": False}

    class RecoveringMySQL:
        def __init__(self, _dsn):
            if not availability["ready"]:
                raise ConnectionError("mysql unavailable during startup")
            self.delivered: list[str] = []

        def __getattr__(self, operation):
            def call(*_args):
                self.delivered.append(operation)
                return True

            return call

    monkeypatch.setattr("iot_diagnosis.external.MySQLMirror", RecoveringMySQL)
    repository.external.configured["mysql"] = True
    repository.external.mysql_dsn = "mysql://test:test@mysql/test"
    repository.external.mysql = None

    assert repository.external.mysql is None
    # 外部存储配置了但客户端缺失时，写入进入 outbox（不依赖启动全量同步）
    repository.save_diagnosis_error(
        "ESP32_05",
        "missing client recovery test",
        "MYSQL_UNAVAILABLE",
        "startup connection failed",
    )
    assert repository.external_sync_status()["by_component"]["mysql"] > 0

    availability["ready"] = True
    retried = repository.retry_external_sync(limit=1000)

    assert retried["failed"] == 0
    assert retried["delivered"] == retried["processed"]
    assert repository.external.mysql is not None
    assert repository.external_sync_status()["pending"] == 0
    assert "upsert_diagnosis" in repository.external.mysql.delivered


def test_text_ingestion_chunks_and_replaces_document(tmp_path) -> None:
    repository = DiagnosisRepository(str(tmp_path / "diagnosis.db"))
    content = ("MQTT keep alive guidance. " * 30) + "\n\n" + ("Broker timeout. " * 30)

    first = ingest_text(
        repository,
        source="mqtt_docs",
        document_id="mqtt-guide",
        title="MQTT Guide",
        content=content,
        chunk_size=300,
        overlap=30,
    )
    assert first["chunk_count"] > 1
    assert first["sync_status"] == "local_only"

    second = ingest_text(
        repository,
        source="mqtt_docs",
        document_id="mqtt-guide",
        title="MQTT Guide v2",
        content="Updated MQTT guide " * 20,
        chunk_size=400,
        overlap=20,
    )
    stored = [
        item
        for item in repository.knowledge_documents(["mqtt_docs"])
        if item["document_id"] == "mqtt-guide"
    ]

    assert len(stored) == second["chunk_count"]
    assert {item["source_id"] for item in stored} == set(second["chunk_ids"])
    assert all("Updated" in item["content"] for item in stored)


def test_rebuild_vector_index_batches_sqlite_documents_and_cases(tmp_path) -> None:
    repository = DiagnosisRepository(str(tmp_path / "diagnosis.db"))

    class FakeProvider:
        name = "real-test"

    class FakeQdrant:
        collection = "test_collection"
        dimensions = 1024
        embedding_provider = FakeProvider()

        def __init__(self):
            self.items = []

        def upsert_many(self, items):
            self.items.extend(items)
            return True

    target = FakeQdrant()
    repository.external.qdrant = target
    result = repository.rebuild_vector_index(["mqtt_docs", "fault_cases"])

    assert result["attempted"] == result["indexed"] == len(target.items)
    assert result["attempted"] > 0
    assert result["pending"] == 0
    assert result["embedding_provider"] == "real-test"
    assert result["collection"] == "test_collection"
    assert result["dimensions"] == 1024
    assert result["sync_status"] == "complete"


def test_failed_batch_vector_write_queues_each_chunk_for_recovery(tmp_path) -> None:
    repository = DiagnosisRepository(str(tmp_path / "diagnosis.db"))

    class FailingQdrant:
        def delete_document(self, _item):
            return True

        def upsert_many(self, _items):
            raise ConnectionError("model or qdrant unavailable")

    repository.external.qdrant = FailingQdrant()
    result = repository.replace_knowledge_document(
        source="mqtt_docs",
        document_id="batch-recovery",
        title="Batch recovery",
        chunks=["first chunk", "second chunk"],
        device_type="ESP32",
    )

    assert result["vector_indexed"] is False
    assert result["sync_status"] == "pending"
    assert repository.external_sync_status()["by_component"]["qdrant"] == 2


async def test_optional_bearer_auth_and_readiness(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DIAGNOSIS_MCP_BEARER_TOKEN", "test-secret-token")
    monkeypatch.setenv("DIAGNOSIS_MCP_PUBLIC_URL", "http://127.0.0.1:9001")
    settings, verifier = auth_configuration()
    assert settings is not None
    assert isinstance(verifier, StaticBearerTokenVerifier)
    assert await verifier.verify_token("wrong") is None
    assert (await verifier.verify_token("test-secret-token")).scopes == ["mcp:invoke"]

    repository = DiagnosisRepository(str(tmp_path / "diagnosis.db"))
    monkeypatch.setattr(server, "repository", repository)
    monkeypatch.setenv("DIAGNOSIS_QDRANT_URL", "http://qdrant:6333")
    response = await server.ready(None)
    payload = json.loads(response.body)

    assert response.status_code == 503
    assert payload["status"] == "not_ready"
    assert "qdrant" in payload["issues"]


async def test_readiness_reports_retrieval_model_outage(tmp_path, monkeypatch) -> None:
    repository = DiagnosisRepository(str(tmp_path / "diagnosis.db"))
    monkeypatch.setattr(server, "repository", repository)
    monkeypatch.setenv("DIAGNOSIS_MYSQL_DSN", "")
    monkeypatch.setenv("DIAGNOSIS_QDRANT_URL", "")
    monkeypatch.setenv("DIAGNOSIS_EMBEDDING_PROVIDER", "openai_compatible")
    monkeypatch.setenv("DIAGNOSIS_RETRIEVAL_MODEL_HEALTH_URL", "http://models:9010/health")
    monkeypatch.setattr(
        "iot_diagnosis.embeddings.urlopen",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(TimeoutError()),
    )

    response = await server.ready(None)
    payload = json.loads(response.body)

    assert response.status_code == 503
    assert payload["retrieval_models"]["status"] == "unavailable"
    assert "retrieval_models" in payload["issues"]


async def test_tool_schemas_keep_optional_params_optional() -> None:
    """契约回归：strict 化把可选参数强转为必填会让第三方模型传出
    字符串 "None" 并触发 MCP 入参校验失败，因此任何带默认值或可空
    的参数都不得出现在 required 中。"""
    async with Client(server.mcp) as client:
        tools = (await client.list_tools()).tools
    assert tools, "no tools discovered"
    for tool in tools:
        schema = tool.input_schema or {}
        properties = schema.get("properties") or {}
        for name in schema.get("required") or []:
            parameter = properties.get(name) or {}
            any_of = parameter.get("anyOf")
            nullable = any(item.get("type") == "null" for item in any_of or [])
            type_value = parameter.get("type")
            type_nullable = isinstance(type_value, list) and "null" in type_value
            assert not (nullable or type_nullable), (
                f"{tool.name}.{name} 是可空参数却出现在 required 中"
            )


def test_list_and_delete_fault_cases(tmp_path) -> None:
    """案例库分页列表与删除：删除需同步清理镜像与向量（本地降级 local_only）。"""
    repository = DiagnosisRepository(str(tmp_path / "cases.db"))
    base = {
        "device_id": "ESP32_05",
        "fault_type": "mqtt_connection",
        "fault_name": "MQTT keep alive 超时",
        "symptoms": ["心跳超时"],
        "logs": ["ERROR mqtt keep alive timeout"],
        "cause": "网络抖动导致心跳丢失",
        "solution": "重连 Broker 并放宽超时",
    }
    first = repository.add_verified_fault_case({**base, "verified_by": "auto-remediation:C1"})
    second = repository.add_verified_fault_case(
        {
            **base,
            "fault_name": "传感器读数卡死",
            "fault_type": "sensor_anomaly",
            "verified_by": "admin",
        }
    )

    listed = repository.list_fault_cases()
    assert listed["total"] == 2
    by_id = {item["fault_id"]: item for item in listed["items"]}
    assert {first["fault_id"], second["fault_id"]} <= set(by_id)
    assert by_id[second["fault_id"]]["verified_by"] == "admin"
    assert by_id[second["fault_id"]]["symptoms"] == ["心跳超时"]
    assert by_id[first["fault_id"]]["verified_by"] == "auto-remediation:C1"

    filtered = repository.list_fault_cases(limit=1)
    assert filtered["total"] == 2 and len(filtered["items"]) == 1

    removed = repository.delete_fault_case(first["fault_id"])
    assert removed["deleted"] is True
    assert removed["sync_status"] in ("complete", "local_only")
    remaining = {item["fault_id"] for item in repository.list_fault_cases()["items"]}
    assert remaining == {second["fault_id"]}

    missing = repository.delete_fault_case("F00000000")
    assert missing["deleted"] is False

    with pytest.raises(ValueError):
        repository.delete_fault_case("not-a-case-id")


def test_case_vector_document_carries_document_id() -> None:
    """Qdrant 删除按 document_id 过滤，案例向量 payload 必须携带该字段。"""
    document = DiagnosisRepository._case_document(
        {
            "fault_id": "FTEST0001",
            "fault_name": "MQTT keep alive 超时",
            "symptoms": ["心跳超时"],
            "logs": ["ERROR timeout"],
            "cause": "网络抖动",
            "solution": "重连",
            "device_type": "ESP32",
        }
    )
    assert document["source"] == "fault_cases"
    assert document["document_id"] == "FTEST0001"
