"""主备检索档位测试：Qwen3 主档位不可用时回落 hash 兜底档位。"""

from __future__ import annotations

from urllib.error import URLError

from iot_diagnosis.embeddings import (
    HashEmbeddingProvider,
    ResilientEmbeddingProvider,
    embedding_provider_from_env,
)
from iot_diagnosis.external.manager import ExternalStores
from iot_diagnosis.external.resilient_store import ResilientVectorStore
from iot_diagnosis.reranker import RemoteReranker


class FakeProvider:
    def __init__(self, name: str, dimensions: int, *, fail: bool = False):
        self.name = name
        self.dimensions = dimensions
        self.fail = fail

    def embed(self, text: str, *, is_query: bool = False) -> list[float]:
        if self.fail:
            raise RuntimeError("EMBEDDING_REQUEST_FAILED")
        return [0.5] * self.dimensions

    def embed_many(self, texts: list[str], *, is_query: bool = False) -> list[list[float]]:
        return [self.embed(text, is_query=is_query) for text in texts]


class FakeStore:
    def __init__(self, name: str, dimensions: int, collection: str):
        self.embedding_provider = FakeProvider(name, dimensions)
        self.dimensions = dimensions
        self.collection = collection
        self.upserts: list[list[dict]] = []
        self.searches: list[dict] = []
        self.deleted: list[dict] = []
        self.fail_upsert = False
        self.fail_search = False
        self.fail_ping = False

    def upsert_many(self, items):
        if self.fail_upsert:
            raise RuntimeError("QDRANT_UNAVAILABLE")
        self.upserts.append(items)
        return True

    def search(self, query, sources, top_k, query_vector=None):
        if self.fail_search:
            raise RuntimeError("QDRANT_UNAVAILABLE")
        self.searches.append(
            {
                "query": query,
                "sources": sources,
                "top_k": top_k,
                "vector_dimensions": len(query_vector) if query_vector is not None else None,
            }
        )
        return [{"source": "mqtt_docs", "id": "guide", "title": "t", "content": "c", "score": 0.5}]

    def delete_document(self, item):
        self.deleted.append(item)
        return True

    def ping(self):
        return not self.fail_ping


def build_wrapper() -> tuple[ResilientVectorStore, FakeStore, FakeStore]:
    primary = FakeStore("openai_compatible", 512, "iot_diagnosis_qwen3_512")
    fallback = FakeStore("hash", 384, "iot_diagnosis_portable")
    return ResilientVectorStore(primary, fallback), primary, fallback


def test_resilient_embedding_uses_primary_when_available():
    provider = ResilientEmbeddingProvider(FakeProvider("openai_compatible", 512), FakeProvider("hash", 384))
    vector = provider.embed("MQTT 心跳超时", is_query=True)
    assert len(vector) == 512
    assert provider.name == "openai_compatible"
    assert provider.dimensions == 512


def test_resilient_embedding_falls_back_when_primary_fails():
    provider = ResilientEmbeddingProvider(
        FakeProvider("openai_compatible", 512, fail=True), FakeProvider("hash", 384)
    )
    vectors = provider.embed_many(["a", "b"], is_query=True)
    assert all(len(vector) == 384 for vector in vectors)


def test_resilient_embedding_rejects_equal_dimensions():
    try:
        ResilientEmbeddingProvider(FakeProvider("openai_compatible", 512), FakeProvider("hash", 512))
    except ValueError as exc:
        assert str(exc) == "EMBEDDING_FALLBACK_DIMENSIONS_CONFLICT"
    else:
        raise AssertionError("expected EMBEDDING_FALLBACK_DIMENSIONS_CONFLICT")


def test_search_routes_query_vector_by_dimensions():
    wrapper, primary, fallback = build_wrapper()
    wrapper.search("mqtt", ["mqtt_docs"], 5, query_vector=[0.1] * 512)
    assert len(primary.searches) == 1
    assert fallback.searches == []

    wrapper.search("mqtt", ["mqtt_docs"], 5, query_vector=[0.1] * 384)
    assert len(primary.searches) == 1
    assert fallback.searches[0]["vector_dimensions"] == 384


def test_search_falls_back_to_hash_collection_when_primary_down():
    wrapper, primary, fallback = build_wrapper()
    primary.fail_search = True
    primary.embedding_provider.fail = True  # 模型服务不可用

    vector = wrapper.embedding_provider.embed("wifi 断线", is_query=True)
    assert len(vector) == 384  # 查询向量回落 hash 兜底

    results = wrapper.search("wifi 断线", ["wifi_docs"], 5, query_vector=vector)
    assert results and results[0]["id"] == "guide"
    assert fallback.searches and primary.searches == []


def test_search_falls_back_when_primary_store_errors():
    wrapper, primary, fallback = build_wrapper()
    primary.fail_search = True

    results = wrapper.search("sensor 漂移", ["sensor_docs"], 3)
    assert results
    assert fallback.searches[0]["query"] == "sensor 漂移"


def test_upsert_writes_both_collections_when_primary_healthy():
    wrapper, primary, fallback = build_wrapper()
    items = [{"source": "mqtt_docs", "id": "guide#0", "content": "心跳"}]

    assert wrapper.upsert_many(items)
    assert primary.upserts == [items]
    assert fallback.upserts == [items]


def test_upsert_falls_back_and_reraises_primary_error_for_outbox():
    wrapper, primary, fallback = build_wrapper()
    primary.fail_upsert = True
    items = [{"source": "mqtt_docs", "id": "guide#0", "content": "心跳"}]

    try:
        wrapper.upsert_many(items)
    except RuntimeError as exc:
        assert str(exc) == "QDRANT_UNAVAILABLE"  # 主集合异常抛出，outbox 稍后补齐
    else:
        raise AssertionError("expected primary error to propagate")
    assert fallback.upserts == [items]  # 兜底集合已先行落库


def test_delete_and_ping_cover_both_collections():
    wrapper, primary, fallback = build_wrapper()
    item = {"source": "mqtt_docs", "document_id": "guide"}

    assert wrapper.delete_document(item)
    assert primary.deleted == [item]
    assert fallback.deleted == [item]

    assert wrapper.ping() is True
    primary.fail_ping = True
    assert wrapper.ping() is True  # 主集合失联但兜底可用
    fallback.fail_ping = True
    assert wrapper.ping() is False


class FakeManagerStore(FakeStore):
    def __init__(self, url, collection, provider=None):
        if provider is None:
            provider = embedding_provider_from_env()
        super().__init__(provider.name, provider.dimensions, collection)


def _configure_qwen_env(monkeypatch, provider="openai_compatible"):
    monkeypatch.setenv("DIAGNOSIS_QDRANT_URL", "http://qdrant:6333")
    monkeypatch.setenv("DIAGNOSIS_QDRANT_COLLECTION", "iot_diagnosis_qwen3_512")
    monkeypatch.setenv("DIAGNOSIS_EMBEDDING_PROVIDER", provider)
    monkeypatch.setenv("DIAGNOSIS_EMBEDDING_API_KEY", "test-key")
    monkeypatch.setenv("DIAGNOSIS_EMBEDDING_MODEL", "Qwen/Qwen3-Embedding-0.6B")
    monkeypatch.setenv("DIAGNOSIS_EMBEDDING_DIMENSIONS", "512")


def test_manager_builds_resilient_store_for_remote_primary(monkeypatch):
    _configure_qwen_env(monkeypatch)
    monkeypatch.setattr("iot_diagnosis.external.manager.QdrantVectorStore", FakeManagerStore)

    stores = ExternalStores()
    wrapper = stores.qdrant
    assert isinstance(wrapper, ResilientVectorStore)
    assert wrapper.primary.collection == "iot_diagnosis_qwen3_512"
    assert wrapper.fallback.collection == "iot_diagnosis_portable"
    assert wrapper.fallback.embedding_provider.name == "hash"
    assert stores.qdrant_fallback is wrapper.fallback

    status = stores.status()
    assert status["qdrant"] == "connected"
    assert status["qdrant_fallback"] == "connected"


def test_manager_keeps_plain_store_for_hash_primary(monkeypatch):
    _configure_qwen_env(monkeypatch, provider="hash")
    monkeypatch.setattr("iot_diagnosis.external.manager.QdrantVectorStore", FakeManagerStore)

    stores = ExternalStores()
    assert isinstance(stores.qdrant, FakeManagerStore)
    assert stores.qdrant_fallback is None


def test_manager_respects_fallback_disable_switch(monkeypatch):
    _configure_qwen_env(monkeypatch)
    monkeypatch.setenv("DIAGNOSIS_EMBEDDING_FALLBACK", "false")
    monkeypatch.setattr("iot_diagnosis.external.manager.QdrantVectorStore", FakeManagerStore)

    stores = ExternalStores()
    assert not isinstance(stores.qdrant, ResilientVectorStore)
    assert stores.qdrant_fallback is None


def test_remote_reranker_falls_back_to_weighted_when_unreachable(monkeypatch):
    def raise_url_error(*_args, **_kwargs):
        raise URLError("connection refused")

    monkeypatch.setattr("iot_diagnosis.reranker.urlopen", raise_url_error)
    reranker = RemoteReranker("http://retrieval-models:9010/rerank")
    candidates = [
        {"source": "mqtt_docs", "id": "a", "content": "MQTT keep alive 超时", "retrieval_score": 0.9},
        {"source": "wifi_docs", "id": "b", "content": "RSSI 信号弱", "retrieval_score": 0.5},
    ]

    ranked = reranker.rerank("mqtt 心跳超时", candidates, expected_source="mqtt_docs", top_k=2)
    assert reranker.used_fallback is True
    assert [item["id"] for item in ranked] == ["a", "b"]


def test_hash_fallback_provider_matches_portable_dimensions():
    provider = HashEmbeddingProvider(384)
    vector = provider.embed("设备离线", is_query=True)
    assert len(vector) == 384
    assert max(abs(value) for value in vector) <= 1.0
