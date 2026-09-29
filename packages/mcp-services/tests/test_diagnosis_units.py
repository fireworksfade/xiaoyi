"""从统一 MCP 重构前的 legacy 测试中保留的诊断模块单测。

原 tests/test_iot_diagnosis.py 依赖已删除的 iot_diagnosis.server 路由，
其中针对现存模块（embedding/reranker 客户端、Qdrant 存储、outbox 恢复、
ingestion、重建）的同步测试拆分到此文件继续生效；server 集成测试随
路由重构一并移除。
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from iot_diagnosis.diagnosis import _profile, diagnose
from iot_diagnosis.embeddings import (
    HashEmbeddingProvider,
    OpenAICompatibleEmbeddingProvider,
)
from iot_diagnosis.external import QdrantVectorStore
from iot_diagnosis.ingestion import ingest_text
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


def test_external_write_outbox_recovers_without_false_index_success(tmp_path) -> None:
    repository = DiagnosisRepository(str(tmp_path / "diagnosis.db"))

    class FlakyStore:
        def __init__(self):
            self.available = False

        def delete_document(self, _item):
            return True

        def upsert(self, _item):
            if not self.available:
                raise ConnectionError("qdrant unavailable")
            return True

        def upsert_many(self, _items):
            if not self.available:
                raise ConnectionError("qdrant unavailable")
            return True

    qdrant = FlakyStore()
    repository.external.qdrant = qdrant

    result = ingest_text(
        repository,
        source="mqtt_docs",
        document_id="outbox-recovery",
        title="Outbox recovery",
        content="MQTT keep alive guidance. " * 30,
        chunk_size=4000,
    )

    assert result["vector_indexed"] is False
    assert result["sync_status"] == "pending"
    assert repository.external_sync_status()["pending"] == 1

    qdrant.available = True
    retried = repository.retry_external_sync()

    assert retried == {"processed": 1, "delivered": 1, "failed": 0}
    assert repository.external_sync_status()["pending"] == 0








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


def test_rebuild_vector_index_batches_sqlite_documents(tmp_path) -> None:
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
    result = repository.rebuild_vector_index(["mqtt_docs"])

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


def test_rejects_case_sources_after_retirement(tmp_path) -> None:
    """案例库退役后，旧来源与案例 CRUD 不再存在（spec §11.1）。"""
    repository = DiagnosisRepository(str(tmp_path / "cases.db"))
    with pytest.raises(ValueError):
        repository.rebuild_vector_index(["fault_cases"])
    assert not hasattr(repository, "add_verified_fault_case")
    assert not hasattr(repository, "list_fault_cases")
    assert not hasattr(repository, "delete_fault_case")
    assert not hasattr(repository, "fault_cases")


def test_diagnose_passes_memory_context_to_llm_and_preserves_refs(tmp_path, monkeypatch) -> None:
    """AC13：memory_context 实际进入 MCP 内部诊断 LLM，输出保留版本引用（spec 4.2/8.4）。"""
    repository = DiagnosisRepository(str(tmp_path / "diagnosis.db"))
    repository.upsert_status(
        "ESP32_05",
        {
            "device_type": "ESP32",
            "name": "节点 05",
            "online": False,
            "wifi": "connected",
            "mqtt": "disconnected",
        },
    )
    calls: dict[str, object] = {}

    class RecordingLLM:
        available = True

        def route(self, query, state, logs):
            return SimpleNamespace(
                data={"fault_type": "mqtt", "need_retrieval": True,
                      "sources": ["mqtt_docs"], "top_k": 3},
                latency_ms=0.1, input_tokens=1, output_tokens=1,
            )

        def diagnose(self, query, state, logs, contexts,
                     memory_context=None, repair_context=None):
            calls["memory_context"] = memory_context
            calls["repair_context"] = repair_context
            return SimpleNamespace(
                data={"fault_type": "mqtt_connection", "fault_name": "MQTT 连接异常",
                      "cause": "keep alive 配置大于 Broker 超时",
                      "solutions": ["下调 keep alive"], "severity": "medium",
                      "confidence": 0.7, "requires_manual_inspection": False,
                      "new_evidence": ["更换参数后仍超时"]},
                latency_ms=1.0, input_tokens=2, output_tokens=3,
            )

    monkeypatch.setattr(
        "iot_diagnosis.diagnosis.DiagnosisLLMClient",
        SimpleNamespace(from_env=lambda: RecordingLLM()),
    )
    memory_context = [{
        "memory_id": "m-1", "revision": 2, "title": "历史经验", "excerpt": "e",
        "applicability": {}, "uncertainty": [], "retrieval_mode": "keyword",
    }]
    result = diagnose(
        repository, "ESP32_05", "MQTT keep alive timeout", None, True,
        memory_context=memory_context,
        repair_context={"previous_diagnosis_id": "DIA_0"},
    )
    assert calls["memory_context"] == memory_context
    assert calls["repair_context"] == {"previous_diagnosis_id": "DIA_0"}
    # 输出只保留引用与版本，不把记忆正文伪装成日志
    assert result["memory_refs"] == [{"memory_id": "m-1", "revision": 2}]


def test_diagnose_rejects_oversized_memory_context(tmp_path) -> None:
    """AC13：后端注入的记忆有界（12000 字符/6 条），超限拒绝。"""
    repository = DiagnosisRepository(str(tmp_path / "diagnosis.db"))
    oversized = [{"memory_id": "m", "revision": 1, "pad": "x" * 13000}]
    with pytest.raises(ValueError, match="MEMORY_CONTEXT_TOO_LARGE"):
        diagnose(repository, "ESP32_05", "查询", None, True, memory_context=oversized)
