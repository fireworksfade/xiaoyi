"""Dense Retrieval（Qdrant + Qwen3-Embedding-0.6B，Spec §19）。

查询向量化与检索计时在此拆分（Spec §30/§36 的 latency 分解）；
Qdrant 未配置或检索失败时返回空列表，由上层 fallback。
"""

from __future__ import annotations

import time
from typing import Any


def embed_query(repository: Any, query: str) -> tuple[list[float] | None, float]:
    """用 dense 通道的 embedding provider 向量化查询，返回 (向量, 耗时ms)。"""
    provider = getattr(getattr(repository, "external", None), "qdrant", None)
    provider = getattr(provider, "embedding_provider", None)
    if provider is None:
        return None, 0.0
    started = time.perf_counter()
    vector = provider.embed(query, is_query=True)
    return vector, (time.perf_counter() - started) * 1000


def dense_retrieve(
    repository: Any,
    query: str,
    sources: list[str],
    top_k: int,
    query_vector: list[float] | None = None,
) -> list[dict[str, Any]]:
    """Qdrant dense 检索，返回带 dense_score 的候选。"""
    if query_vector is None:
        items = repository.vector_search(query, sources, top_k)
    else:
        items = repository.vector_search(query, sources, top_k, query_vector=query_vector)
    results = []
    for item in items:
        if not all(key in item for key in ("source", "id", "title", "content")):
            continue
        results.append({**item, "dense_score": float(item.get("score") or 0.0)})
    return results
