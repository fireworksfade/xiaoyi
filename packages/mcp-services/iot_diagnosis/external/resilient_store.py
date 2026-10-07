"""主备向量存储：Qwen3 主档位不可用时自动回落到本地 hash 兜底档位。

主集合（openai_compatible embedding）与兜底集合（hash embedding）保持
独立，两种向量不混入同一集合；查询向量按维度路由到对应集合。主集合
始终是权威数据源：主档位写入失败时兜底集合先行落库保证检索可用，主
集合由调用方的 outbox 机制稍后补齐。
"""

from __future__ import annotations

import logging
from contextvars import ContextVar
from typing import Any

from iot_diagnosis.embeddings import ResilientEmbeddingProvider

logger = logging.getLogger("xiaoyi.iot_diagnosis.external")


class ResilientVectorStore:
    def __init__(self, primary: Any, fallback: Any):
        self.primary = primary
        self.fallback = fallback
        self.embedding_provider = ResilientEmbeddingProvider(
            primary.embedding_provider, fallback.embedding_provider
        )
        self.dimensions = primary.dimensions
        self.collection = primary.collection
        self._active_store: ContextVar[Any] = ContextVar("retrieval_active_store", default=primary)

    @property
    def active_provider(self) -> str:
        store = self._active_store.get()
        return getattr(store, "active_provider", store.embedding_provider.name)

    @property
    def active_collection(self) -> str:
        store = self._active_store.get()
        return getattr(store, "active_collection", store.collection)

    def upsert(self, item: dict[str, Any]) -> bool:
        return self.upsert_many([item])

    def upsert_many(self, items: list[dict[str, Any]]) -> bool:
        try:
            result = self.primary.upsert_many(items)
        except Exception as primary_error:
            # 兜底集合立即写入，主集合异常继续抛出，由 outbox 稍后补齐
            try:
                self.fallback.upsert_many(items)
            except Exception:
                logger.exception("Fallback collection upsert failed")
            raise primary_error from None
        try:
            self.fallback.upsert_many(items)
        except Exception:
            # 兜底集合允许暂时落后，重建向量索引时可补齐
            logger.exception("Fallback collection upsert failed")
        return result

    def delete_document(self, item: dict[str, Any]) -> bool:
        result = self.primary.delete_document(item)
        try:
            self.fallback.delete_document(item)
        except Exception:
            logger.exception("Fallback collection delete failed")
        return result

    def search(
        self,
        query: str,
        sources: list[str],
        top_k: int,
        query_vector: list[float] | None = None,
    ) -> list[dict[str, Any]]:
        self._active_store.set(self.primary)
        if query_vector is not None and len(query_vector) != self.primary.dimensions:
            self._active_store.set(self.fallback)
            return self.fallback.search(query, sources, top_k, query_vector=query_vector)
        try:
            return self.primary.search(query, sources, top_k, query_vector=query_vector)
        except Exception:
            # 主集合不可用：用兜底 provider 现算查询向量检索兜底集合
            self._active_store.set(self.fallback)
            return self.fallback.search(query, sources, top_k)

    def ping(self) -> bool:
        try:
            if self.primary.ping():
                return True
        except Exception:
            pass
        try:
            return bool(self.fallback.ping())
        except Exception:
            return False
