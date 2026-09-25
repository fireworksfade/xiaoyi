"""Hybrid Retrieval：Dense + BM25 + RRF + Reranker（Spec §5、§23-§27、§34、§36）。

检索策略支持 dense / sparse / hybrid（Spec §34），默认 hybrid；
Dense 与 BM25 候选按 chunk_id 去重后经 RRF 融合（Spec §23/§24），
最多 60 个候选进入 Qwen3-Reranker-0.6B 重排（Spec §25/§26）。
"""

from __future__ import annotations

import time
from typing import Any

from iot_diagnosis.reranker import lexical_similarity, reranker_from_env
from iot_diagnosis.retrieval.config import RetrievalConfig
from iot_diagnosis.retrieval.dense import dense_retrieve, embed_query
from iot_diagnosis.retrieval.fusion import RANK_CHANNELS, rrf_fuse
from iot_diagnosis.router import infer_fault_type, route_query, validate_sources

# 候选内部使用的通道分数/排名，不进入最终结果（debug 模式按 Spec §37 透出）
_INTERNAL_KEYS = frozenset(
    {*RANK_CHANNELS, "dense_score", "sparse_score", "lexical_score", "rrf_score", "_primary"}
)
_STRIP_KEYS = _INTERNAL_KEYS | {"retrieval_score", "heading"}


def rewrite_query(
    query: str,
    state: dict[str, Any] | None,
    logs: list[str] | None,
) -> str:
    context = [query]
    if state:
        context.extend(
            [
                f"WiFi={state.get('wifi_status')}",
                f"RSSI={state.get('rssi')}",
                f"MQTT={state.get('mqtt_status')}",
                f"温度={state.get('temperature')}",
            ]
        )
    context.extend((logs or [])[:10])
    return "；".join(str(item) for item in context if item)


def _ensure_candidate(
    candidates: dict[tuple[str, str], dict[str, Any]],
    item: dict[str, Any],
) -> dict[str, Any]:
    key = (str(item["source"]), str(item["id"]))
    candidate = candidates.get(key)
    if candidate is None:
        candidate = {
            "source": item["source"],
            "id": item["id"],
            "title": item.get("title"),
            "content": item.get("content"),
        }
        candidates[key] = candidate
    elif candidate.get("content") is None and item.get("content") is not None:
        candidate["content"] = item["content"]
    return candidate


def _lexical_candidates(
    repository: Any,
    query: str,
    selected: list[str],
    state: dict[str, Any] | None,
    doc_sources: list[str],
) -> list[dict[str, Any]]:
    """fault_cases / realtime_db 及 FTS 不可用时的文档 lexical 兜底候选。"""
    items: list[dict[str, Any]] = []
    if "fault_cases" in selected:
        for case in repository.fault_cases():
            content = "；".join(
                [
                    case["fault_name"],
                    *case["symptoms"],
                    *case["logs"],
                    case["cause"],
                    case["solution"],
                ]
            )
            items.append(
                {
                    "source": "fault_cases",
                    "id": case["fault_id"],
                    "title": case["fault_name"],
                    "content": content,
                    "score": lexical_similarity(query, content),
                }
            )
    if "realtime_db" in selected and state:
        content = (
            f"设备在线={state.get('online')}；WiFi={state.get('wifi_status')}；"
            f"RSSI={state.get('rssi')}；MQTT={state.get('mqtt_status')}；"
            f"温度={state.get('temperature')}"
        )
        items.append(
            {
                "source": "realtime_db",
                "id": str(state["device_id"]),
                "title": "当前设备状态",
                "content": content,
                "score": lexical_similarity(query, content),
            }
        )
    if doc_sources:
        for document in repository.knowledge_documents(doc_sources):
            items.append(
                {
                    "source": document["source"],
                    "id": document["source_id"],
                    "title": document["title"],
                    "content": document["content"],
                    "score": lexical_similarity(query, document["content"]),
                }
            )
    return items


def search_knowledge(
    repository: Any,
    query: str,
    sources: list[str] | None = None,
    top_k: int = 5,
    *,
    state: dict[str, Any] | None = None,
    logs: list[str] | None = None,
    strategy: str | None = None,
    debug: bool | None = None,
) -> dict[str, Any]:
    config = RetrievalConfig.from_env(strategy)
    if debug is None:
        debug = config.debug
    selected = validate_sources(
        sources
        or route_query(
            query,
            state,
            logs,
            embedding_provider=getattr(
                getattr(getattr(repository, "external", None), "qdrant", None),
                "embedding_provider",
                None,
            ),
        ).sources
    )
    rewritten = rewrite_query(query, state, logs)
    started_total = time.perf_counter()
    latency = {"embedding": 0.0, "dense": 0.0, "sparse": 0.0, "fusion": 0.0, "rerank": 0.0}
    candidates: dict[tuple[str, str], dict[str, Any]] = {}
    dense_items: list[dict[str, Any]] = []
    sparse_items: list[dict[str, Any]] = []

    use_dense = config.strategy in ("dense", "hybrid")
    use_sparse = config.strategy in ("sparse", "hybrid") and config.enable_sparse
    doc_sources = [item for item in selected if item not in {"fault_cases", "realtime_db"}]

    if use_dense:
        query_vector, latency["embedding"] = embed_query(repository, rewritten)
        started = time.perf_counter()
        dense_items = dense_retrieve(
            repository, rewritten, selected, config.dense_top_k, query_vector=query_vector
        )
        latency["dense"] = (time.perf_counter() - started) * 1000
        for rank, item in enumerate(dense_items, 1):
            candidate = _ensure_candidate(candidates, item)
            candidate["dense_rank"] = rank
            candidate["dense_score"] = item["dense_score"]

    sparse_available = True
    if use_sparse:
        started = time.perf_counter()
        sparse_items = repository.bm25_search(query, doc_sources, config.sparse_top_k)
        latency["sparse"] = (time.perf_counter() - started) * 1000
        sparse_available = bool(sparse_items) or repository.bm25_available()
        for rank, item in enumerate(sparse_items, 1):
            candidate = _ensure_candidate(candidates, item)
            candidate["sparse_rank"] = rank
            candidate["sparse_score"] = float(item.get("score") or 0.0)

    # fault_cases / realtime_db 没有 FTS 分块，继续走 lexical 通道。知识文档
    # 仅在 FTS5 结构性不可用时才使用 legacy lexical 兜底；正常 hybrid 不得
    # 引入第三条 lexical 通道（Spec G6 / AC10）。关闭 sparse 时则只保留
    # dense 通道，实现 AC12 要求的 Dense fallback。
    lexical_fallback = use_sparse and not sparse_available
    include_doc_lexical = lexical_fallback
    if "fault_cases" in selected or "realtime_db" in selected or include_doc_lexical:
        started = time.perf_counter()
        lexical_items = _lexical_candidates(
            repository,
            rewritten,
            selected,
            state,
            doc_sources if include_doc_lexical else [],
        )
        lexical_items.sort(key=lambda item: float(item["score"]), reverse=True)
        for rank, item in enumerate(lexical_items, 1):
            candidate = _ensure_candidate(candidates, item)
            candidate["lexical_rank"] = rank
            candidate["lexical_score"] = float(item["score"])
        latency["sparse"] += (time.perf_counter() - started) * 1000

    if config.strategy == "hybrid" and config.enable_rrf:
        started = time.perf_counter()
        rrf_fuse(candidates, config.rrf_k)
        latency["fusion"] = (time.perf_counter() - started) * 1000

    for candidate in candidates.values():
        if config.strategy == "hybrid" and config.enable_rrf:
            candidate["_primary"] = float(candidate.get("rrf_score") or 0.0)
        elif config.strategy == "dense":
            candidate["_primary"] = float(candidate.get("dense_score") or 0.0)
        elif config.strategy == "sparse":
            candidate["_primary"] = float(
                candidate.get("sparse_score") or candidate.get("lexical_score") or 0.0
            )
        else:  # hybrid 且关闭 RRF：退化为通道最高分（仅用于测试/fallback）
            candidate["_primary"] = max(
                float(candidate.get(key) or 0.0)
                for key in ("dense_score", "sparse_score", "lexical_score", "rrf_score")
            )

    # 知识库增大后候选可能远超重排服务的批量上限；先按融合分截取头部
    pool = sorted(candidates.values(), key=lambda item: item["_primary"], reverse=True)
    pool = pool[: config.rerank_candidate_limit]
    max_primary = pool[0]["_primary"] if pool else 0.0
    for candidate in pool:
        if config.strategy == "dense":
            candidate["retrieval_score"] = min(max(candidate["_primary"], 0.0), 1.0)
        else:
            candidate["retrieval_score"] = (
                candidate["_primary"] / max_primary if max_primary > 0 else 0.0
            )

    fault_type = infer_fault_type(" ".join([query, *(logs or [])]))
    expected_source = f"{fault_type}_docs"
    if config.enable_reranker:
        reranker = reranker_from_env()
        started = time.perf_counter()
        ranked = reranker.rerank(rewritten, pool, expected_source=expected_source, top_k=top_k)
        latency["rerank"] = (time.perf_counter() - started) * 1000
        reranker_meta = {
            "provider": getattr(reranker, "name", type(reranker).__name__),
            "fallback": bool(getattr(reranker, "used_fallback", False)),
        }
    else:
        ranked = [
            {**candidate, "score": round(candidate["retrieval_score"], 4)}
            for candidate in pool[:top_k]
        ]
        reranker_meta = {"provider": "disabled", "fallback": False}

    results = []
    for item in ranked:
        clean = {key: value for key, value in item.items() if key not in _STRIP_KEYS}
        if debug:
            candidate = candidates.get((str(item["source"]), str(item["id"])), {})
            for key in (
                "dense_rank",
                "dense_score",
                "sparse_rank",
                "sparse_score",
                "lexical_rank",
                "lexical_score",
                "rrf_score",
            ):
                if key in candidate:
                    clean[key] = candidate[key]
            clean["reranker_score"] = item.get("score")
        results.append(clean)

    qdrant = getattr(getattr(repository, "external", None), "qdrant", None)
    embedding_provider = getattr(getattr(qdrant, "embedding_provider", None), "name", None)
    return {
        "query": query,
        "rewritten_query": rewritten,
        "selected_sources": selected,
        "strategy": config.strategy,
        "candidate_count": len(candidates),
        "dense_candidates": len(dense_items),
        "sparse_candidates": len(sparse_items),
        "merged_candidates": len(candidates),
        "rerank_candidates": len(pool),
        "returned": len(results),
        "embedding_provider": embedding_provider or "local_lexical",
        "reranker": reranker_meta,
        "latency_ms": {
            **{key: round(value, 3) for key, value in latency.items()},
            "total": round((time.perf_counter() - started_total) * 1000, 3),
        },
        "results": results,
    }


def search_fault_cases(
    repository: Any,
    query: str,
    device_type: str | None,
    fault_type: str | None,
    top_k: int,
) -> list[dict[str, Any]]:
    results = []
    for case in repository.fault_cases(device_type, fault_type):
        content = "；".join(
            [case["fault_name"], *case["symptoms"], *case["logs"], case["cause"], case["solution"]]
        )
        results.append(
            {
                "fault_id": case["fault_id"],
                "fault_name": case["fault_name"],
                "symptoms": case["symptoms"],
                "cause": case["cause"],
                "solution": case["solution"],
                "verified": True,
                "similarity": round(lexical_similarity(query, content), 4),
            }
        )
    return sorted(results, key=lambda item: item["similarity"], reverse=True)[:top_k]
