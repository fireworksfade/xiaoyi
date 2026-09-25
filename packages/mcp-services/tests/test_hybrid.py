"""Hybrid Retrieval Tests（Spec《RAG 检索链路升级》§23-§27、§34-§37、§40、AC11-AC14）。"""

import pytest

from iot_diagnosis.embeddings import HashEmbeddingProvider
from iot_diagnosis.repository import DiagnosisRepository
from iot_diagnosis.retrieval import search_knowledge
from iot_diagnosis.retrieval.config import RetrievalConfig
from iot_diagnosis.retrieval.fusion import rrf_fuse
from scripts.evaluate_chunk_sizes import LocalDenseIndex

DOC_A = "# MQTT 超时排查\n\nMQTT_KEEPALIVE 心跳超时导致连接断开，检查 keep alive 配置。\n"
DOC_B = "# WiFi 弱信号\n\nRSSI 信号偏弱时 WiFi 会频繁掉线，检查信道与接入点距离。\n"
DOC_C = "# 传感器漂移\n\nADC 采样值随温度漂移，需要周期性校准传感器。\n"


class FakeQdrant:
    """进程内 cosine 检索，模拟 dense 通道（Spec §19）。"""

    collection = "fake_collection"
    dimensions = 384

    def __init__(self, items: list[dict]):
        self.items = list(items)
        self.embedding_provider = HashEmbeddingProvider(384)

    def search(self, query: str, sources: list[str], top_k: int, query_vector=None):
        vector = (
            query_vector
            if query_vector is not None
            else self.embedding_provider.embed(query, is_query=True)
        )
        selected = set(sources)
        scored = []
        for item in self.items:
            if selected and item["source"] not in selected:
                continue
            item_vector = self.embedding_provider.embed(item["content"])
            score = sum(a * b for a, b in zip(vector, item_vector, strict=True))
            scored.append((score, item))
        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [{**item, "score": round(score, 6)} for score, item in scored[:top_k]]


def _make_repository(tmp_path) -> DiagnosisRepository:
    repository = DiagnosisRepository(str(tmp_path / "diagnosis.db"))
    repository.replace_knowledge_document(
        source="mqtt_docs",
        document_id="doc-a",
        title="MQTT 超时排查",
        chunks=[
            {"content": DOC_A, "heading": "MQTT 超时排查", "metadata_json": "{}", "token_count": 30}
        ],
        device_type="ESP32",
    )
    repository.replace_knowledge_document(
        source="wifi_docs",
        document_id="doc-b",
        title="WiFi 弱信号",
        chunks=[
            {"content": DOC_B, "heading": "WiFi 弱信号", "metadata_json": "{}", "token_count": 30}
        ],
        device_type="ESP32",
    )
    return repository


def test_config_defaults_match_spec() -> None:
    config = RetrievalConfig.from_env()
    assert config.strategy == "hybrid"
    assert config.dense_top_k == 40
    assert config.sparse_top_k == 40
    assert config.rrf_k == 60
    assert config.rerank_candidate_limit == 60
    assert config.enable_sparse and config.enable_rrf and config.enable_reranker


def test_rrf_fusion_sums_channel_reciprocal_ranks() -> None:
    candidates = {
        ("mqtt_docs", "both"): {"dense_rank": 3, "sparse_rank": 7},
        ("mqtt_docs", "dense"): {"dense_rank": 1},
        ("mqtt_docs", "sparse"): {"sparse_rank": 1},
    }
    rrf_fuse(candidates, k=60)
    assert candidates[("mqtt_docs", "both")]["rrf_score"] == pytest.approx(
        1 / 63 + 1 / 67, abs=1e-6
    )
    # 双通道命中的候选排序高于单通道候选（Spec §24）
    assert (
        candidates[("mqtt_docs", "both")]["rrf_score"]
        > candidates[("mqtt_docs", "dense")]["rrf_score"]
    )


def test_hybrid_merges_dense_and_sparse_with_dedup(tmp_path) -> None:
    repository = _make_repository(tmp_path)
    repository.external.qdrant = FakeQdrant(
        [{"source": "mqtt_docs", "id": "doc-a#0000", "title": "MQTT 超时排查", "content": DOC_A}]
    )
    repository.external.configured["qdrant"] = True

    result = search_knowledge(repository, "MQTT_KEEPALIVE 超时", ["mqtt_docs", "wifi_docs"], 5)

    # doc-a 同时被 dense 与 sparse 命中，去重后只出现一次（Spec §23）
    ids = [item["id"] for item in result["results"]]
    assert ids.count("doc-a#0000") == 1
    assert result["strategy"] == "hybrid"
    assert result["dense_candidates"] == 1
    assert result["sparse_candidates"] >= 1
    # merged 候选数 == 去重后的唯一候选数（Spec §23）
    assert result["merged_candidates"] == len(set(ids))
    assert result["rerank_candidates"] == result["merged_candidates"]
    assert result["returned"] == len(ids)
    assert result["embedding_provider"] == "hash"
    assert result["latency_ms"]["total"] > 0
    assert {"embedding", "dense", "sparse", "fusion", "rerank"} <= set(result["latency_ms"])


def test_dense_only_hit_via_qdrant(tmp_path) -> None:
    repository = _make_repository(tmp_path)
    # doc-c 只存在于向量库，FTS/SQLite 均无 → dense-only hit（Spec §40）
    doc_c = "# 网络延迟\n\npacket loss 与 RTT 延迟异常的排查方法。\n"
    repository.external.qdrant = FakeQdrant(
        [
            {"source": "device_docs", "id": "doc-c#0000", "title": "网络延迟", "content": doc_c},
            {"source": "mqtt_docs", "id": "doc-a#0000", "title": "MQTT 超时排查", "content": DOC_A},
        ]
    )
    repository.external.configured["qdrant"] = True

    result = search_knowledge(repository, "packet loss 延迟", ["device_docs", "mqtt_docs"], 5)
    ids = [item["id"] for item in result["results"]]
    assert "doc-c#0000" in ids


def test_bm25_only_hit_without_dense(tmp_path) -> None:
    repository = _make_repository(tmp_path)
    # 无 Qdrant：dense 通道为空，BM25 仍能命中（Spec §40 BM25-only）
    result = search_knowledge(repository, "RSSI 信号弱 掉线", ["wifi_docs"], 5)
    ids = [item["id"] for item in result["results"]]
    assert "doc-b#0000" in ids
    assert result["dense_candidates"] == 0


def test_hybrid_falls_back_to_lexical_without_fts(tmp_path, monkeypatch) -> None:
    repository = DiagnosisRepository(str(tmp_path / "diagnosis.db"))
    # 旧库没有 FTS 表：sparse 结构性缺失时文档由 lexical 通道兜底（AC12）
    import sqlite3

    with sqlite3.connect(repository.path) as db:
        db.execute("DROP TABLE knowledge_chunks_fts")
    repository.replace_knowledge_document(
        source="mqtt_docs",
        document_id="doc-a",
        title="MQTT 超时排查",
        chunks=["MQTT_KEEPALIVE 心跳超时导致连接断开"],
        device_type="ESP32",
    )
    result = search_knowledge(repository, "MQTT_KEEPALIVE 超时", ["mqtt_docs"], 5)
    assert result["results"][0]["id"] == "doc-a#0000"


def test_strategy_param_selects_channel(tmp_path, monkeypatch) -> None:
    repository = _make_repository(tmp_path)
    monkeypatch.delenv("RAG_RETRIEVAL_STRATEGY", raising=False)

    dense = search_knowledge(repository, "RSSI 弱", ["wifi_docs"], 5, strategy="dense")
    assert dense["strategy"] == "dense"
    assert dense["sparse_candidates"] == 0

    sparse = search_knowledge(repository, "RSSI 信号弱 掉线", ["wifi_docs"], 5, strategy="sparse")
    assert sparse["strategy"] == "sparse"
    assert sparse["dense_candidates"] == 0
    assert sparse["results"][0]["id"] == "doc-b#0000"

    with pytest.raises(ValueError):
        search_knowledge(repository, "x", ["mqtt_docs"], 5, strategy="invalid")


def test_feature_flags_disable_components(tmp_path, monkeypatch) -> None:
    repository = _make_repository(tmp_path)
    repository.external.qdrant = FakeQdrant(
        [{"source": "mqtt_docs", "id": "doc-a#0000", "title": "MQTT 超时排查", "content": DOC_A}]
    )
    repository.external.configured["qdrant"] = True
    monkeypatch.setenv("RAG_ENABLE_RERANKER", "false")

    result = search_knowledge(repository, "MQTT_KEEPALIVE 超时", ["mqtt_docs"], 5)
    assert result["reranker"] == {"provider": "disabled", "fallback": False}
    assert result["results"]
    assert all("retrieval_score" not in item for item in result["results"])

    monkeypatch.setenv("RAG_ENABLE_RERANKER", "true")
    monkeypatch.setenv("RAG_ENABLE_SPARSE", "false")
    sparse_off = search_knowledge(repository, "MQTT_KEEPALIVE 超时", ["mqtt_docs"], 5)
    assert sparse_off["sparse_candidates"] == 0
    assert sparse_off["dense_candidates"] == 1
    assert sparse_off["merged_candidates"] == 1
    assert "lexical_rank" not in sparse_off["results"][0]


def test_disabling_sparse_falls_back_to_dense_not_legacy_lexical(tmp_path, monkeypatch) -> None:
    repository = _make_repository(tmp_path)
    monkeypatch.setenv("RAG_ENABLE_SPARSE", "false")
    monkeypatch.setenv("RAG_ENABLE_RERANKER", "false")
    monkeypatch.setenv("RAG_RETRIEVAL_DEBUG", "true")

    # 没有 dense backend 时不能由旧文档 lexical 偷偷返回结果。
    no_dense = search_knowledge(repository, "MQTT_KEEPALIVE 超时", ["mqtt_docs"], 5)
    assert no_dense["results"] == []

    repository.external.qdrant = FakeQdrant(
        [{"source": "mqtt_docs", "id": "doc-a#0000", "title": "MQTT 超时排查", "content": DOC_A}]
    )
    repository.external.configured["qdrant"] = True
    dense_only = search_knowledge(repository, "MQTT_KEEPALIVE 超时", ["mqtt_docs"], 5)
    assert [item["id"] for item in dense_only["results"]] == ["doc-a#0000"]
    assert "dense_rank" in dense_only["results"][0]
    assert "lexical_rank" not in dense_only["results"][0]


def test_local_dense_eval_index_returns_retrieval_id() -> None:
    provider = HashEmbeddingProvider(384)
    index = LocalDenseIndex(provider)
    index.add(
        [
            {
                "source": "mqtt_docs",
                "source_id": "doc-a#0000",
                "title": "MQTT 超时排查",
                "content": DOC_A,
            }
        ]
    )

    results = index.search("MQTT_KEEPALIVE", ["mqtt_docs"], 5)

    assert results[0]["id"] == "doc-a#0000"


def test_debug_metadata_exposes_ranks_and_scores(tmp_path, monkeypatch) -> None:
    repository = _make_repository(tmp_path)
    repository.external.qdrant = FakeQdrant(
        [{"source": "mqtt_docs", "id": "doc-a#0000", "title": "MQTT 超时排查", "content": DOC_A}]
    )
    repository.external.configured["qdrant"] = True
    monkeypatch.setenv("RAG_RETRIEVAL_DEBUG", "true")

    result = search_knowledge(repository, "MQTT_KEEPALIVE 超时", ["mqtt_docs"], 5)
    top = result["results"][0]
    assert top["dense_rank"] == 1
    assert top["sparse_rank"] == 1
    assert top["rrf_score"] > 0
    assert top["reranker_score"] == top["score"]

    monkeypatch.setenv("RAG_RETRIEVAL_DEBUG", "false")
    clean = search_knowledge(repository, "MQTT_KEEPALIVE 超时", ["mqtt_docs"], 5)
    assert "rrf_score" not in clean["results"][0]
    assert "dense_rank" not in clean["results"][0]


def test_reranker_reorders_candidates(tmp_path, monkeypatch) -> None:
    import iot_diagnosis.retrieval.hybrid as hybrid

    class LexicalFirstReranker:
        """确定性 stub：按 lexical 分数重排，验证 reranker 对最终排序的决定作用。"""

        name = "stub"
        used_fallback = False

        def rerank(self, query, candidates, *, expected_source, top_k):
            ranked = sorted(
                candidates,
                key=lambda candidate: hybrid.lexical_similarity(
                    query, str(candidate.get("content") or "")
                ),
                reverse=True,
            )[:top_k]
            return [
                {
                    **candidate,
                    "score": round(hybrid.lexical_similarity(query, candidate["content"]), 4),
                }
                for candidate in ranked
            ]

    repository = _make_repository(tmp_path)
    repository.replace_knowledge_document(
        source="sensor_docs",
        document_id="doc-c",
        title="传感器漂移",
        chunks=[
            {"content": DOC_C, "heading": "传感器漂移", "metadata_json": "{}", "token_count": 30}
        ],
        device_type="ESP32",
    )
    repository.external.qdrant = FakeQdrant(
        [
            {
                "source": "sensor_docs",
                "id": "doc-c#0000",
                "title": "传感器漂移",
                "content": DOC_C,
            },
            {
                "source": "mqtt_docs",
                "id": "doc-a#0000",
                "title": "MQTT 超时排查",
                "content": DOC_A,
            },
        ]
    )
    repository.external.configured["qdrant"] = True
    # RRF 排序中 doc-a 更高（sparse 命中）；stub reranker 依据 lexical 分数
    # 把 doc-c 重排到首位（Spec §26/§40 reranker reorder）
    monkeypatch.setattr(hybrid, "reranker_from_env", lambda: LexicalFirstReranker())
    monkeypatch.setattr(
        hybrid,
        "lexical_similarity",
        lambda query, content: 0.9 if "漂移" in content else 0.0,
    )

    result = search_knowledge(repository, "MQTT_KEEPALIVE", ["mqtt_docs", "sensor_docs"], 2)
    assert [item["id"] for item in result["results"]] == ["doc-c#0000", "doc-a#0000"]
    assert result["reranker"]["provider"] == "stub"
    assert result["results"][0]["score"] == pytest.approx(0.9)


def test_backward_compatible_call_and_realtime_source(tmp_path) -> None:
    repository = _make_repository(tmp_path)
    state = repository.get_device_status("ESP32_05")
    # 旧调用方式不变（Spec §34/AC14）
    result = search_knowledge(repository, "MQTT_KEEPALIVE 超时", ["mqtt_docs", "realtime_db"], 5)
    assert result["selected_sources"] == ["mqtt_docs", "realtime_db"]
    assert result["results"]

    realtime = search_knowledge(repository, "MQTT_KEEPALIVE 超时", ["realtime_db"], 1, state=state)
    assert realtime["results"][0]["source"] == "realtime_db"
