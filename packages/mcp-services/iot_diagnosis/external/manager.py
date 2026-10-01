"""ExternalStores 统一管理类 - 简化版（仅 Qdrant）。"""

from __future__ import annotations

import logging
import os
from typing import Any

from iot_diagnosis.embeddings import HashEmbeddingProvider

from .qdrant_store import QdrantVectorStore
from .resilient_store import ResilientVectorStore

logger = logging.getLogger("xiaoyi.iot_diagnosis.external")


class ExternalStores:
    def __init__(self):
        self.qdrant: QdrantVectorStore | ResilientVectorStore | None = None
        self.qdrant_fallback: QdrantVectorStore | None = None
        self.errors: dict[str, str] = {}
        self.qdrant_url = (
            os.getenv("DIAGNOSIS_QDRANT_URL") or os.getenv("RETRIEVAL_QDRANT_URL", "")
        ).strip()
        self.qdrant_collection = os.getenv("DIAGNOSIS_QDRANT_COLLECTION", "iot_diagnosis_knowledge")
        self.configured = {
            "qdrant": bool(self.qdrant_url),
        }
        self.ensure_connected("qdrant")

    def _build_fallback_store(self, primary: QdrantVectorStore) -> QdrantVectorStore | None:
        """主档位为远程模型时构建本地 hash 兜底集合；主档位即 hash 时不重复构建。"""
        enabled = os.getenv("DIAGNOSIS_EMBEDDING_FALLBACK", "true").strip().lower()
        if enabled in {"0", "false", "no"}:
            return None
        if primary.embedding_provider.name == "hash":
            return None
        dimensions = int(os.getenv("DIAGNOSIS_EMBEDDING_FALLBACK_DIMENSIONS", "384"))
        if dimensions == primary.dimensions:
            logger.warning("Fallback embedding dimensions equal primary; fallback disabled")
            return None
        collection = os.getenv("DIAGNOSIS_QDRANT_FALLBACK_COLLECTION", "iot_diagnosis_portable")
        try:
            return QdrantVectorStore(self.qdrant_url, collection, HashEmbeddingProvider(dimensions))
        except Exception as exc:
            logger.warning("Fallback vector store unavailable: %s", type(exc).__name__)
            return None

    def ensure_connected(self, component: str) -> bool:
        if not self.configured.get(component):
            return False
        if getattr(self, component, None) is not None:
            return True
        try:
            if component == "qdrant":
                primary = QdrantVectorStore(self.qdrant_url, self.qdrant_collection)
                fallback = self._build_fallback_store(primary)
                self.qdrant_fallback = fallback
                self.qdrant = (
                    primary if fallback is None else ResilientVectorStore(primary, fallback)
                )
            else:
                return False
            self.errors.pop(component, None)
            return True
        except Exception as exc:
            self.errors[component] = type(exc).__name__
            logger.warning("External %s connection unavailable: %s", component, type(exc).__name__)
            return False

    def is_configured(self, component: str) -> bool:
        return bool(self.configured.get(component) or getattr(self, component, None))

    def status(self) -> dict[str, Any]:
        qdrant_status = "disabled"
        fallback_status = "disabled"
        self.ensure_connected("qdrant")
        if self.qdrant:
            # connected/fallback 标签始终描述主集合；主集合失联而兜底可用时
            # 显示 fallback，与存量的降级语义保持一致
            primary_target = getattr(self.qdrant, "primary", self.qdrant)
            try:
                qdrant_status = "connected" if primary_target.ping() else "fallback"
                if qdrant_status == "connected":
                    self.errors.pop("qdrant", None)
            except Exception as exc:
                qdrant_status = "fallback"
                self.errors["qdrant"] = type(exc).__name__
        if self.qdrant_fallback is not None:
            try:
                fallback_status = "connected" if self.qdrant_fallback.ping() else "unavailable"
            except Exception as exc:
                fallback_status = "unavailable"
                self.errors.setdefault("qdrant_fallback", type(exc).__name__)
        return {
            "sqlite": "connected",
            "qdrant": qdrant_status,
            "qdrant_fallback": fallback_status,
            "errors": self.errors,
        }
