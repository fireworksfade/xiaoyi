"""ExternalStores 统一管理类 - 简化版（仅 Qdrant）。"""

from __future__ import annotations

import logging
import os
from typing import Any

from iot_diagnosis.embeddings import HashEmbeddingProvider, OpenAICompatibleEmbeddingProvider

from .qdrant_store import QdrantVectorStore
from .resilient_store import ResilientVectorStore

logger = logging.getLogger("xiaoyi.iot_diagnosis.external")


class ExternalStores:
    def __init__(self):
        self.qdrant: QdrantVectorStore | ResilientVectorStore | None = None
        self.qdrant_fallback: QdrantVectorStore | None = None
        self.qdrant_local_fallback: QdrantVectorStore | None = None
        self.errors: dict[str, str] = {}
        self.qdrant_url = (
            os.getenv("DIAGNOSIS_QDRANT_URL") or os.getenv("RETRIEVAL_QDRANT_URL", "")
        ).strip()
        self.qdrant_collection = os.getenv("DIAGNOSIS_QDRANT_COLLECTION", "iot_diagnosis_knowledge")
        self.configured = {
            "qdrant": bool(self.qdrant_url),
        }
        self.ensure_connected("qdrant")

    def _build_fallback_store(
        self, primary: QdrantVectorStore
    ) -> QdrantVectorStore | ResilientVectorStore | None:
        """API -> local Qwen -> hash, with an independent collection at each tier."""
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
            portable = QdrantVectorStore(
                self.qdrant_url, collection, HashEmbeddingProvider(dimensions)
            )
            self.qdrant_fallback = portable
        except Exception as exc:
            logger.warning("Fallback vector store unavailable: %s", type(exc).__name__)
            portable = None
        enabled_local = os.getenv("DIAGNOSIS_LOCAL_EMBEDDING_FALLBACK", "false").strip().lower()
        if enabled_local not in {"1", "true", "yes"}:
            return portable
        local_dimensions = int(os.getenv("DIAGNOSIS_LOCAL_EMBEDDING_DIMENSIONS", "512"))
        local_collection = os.getenv("DIAGNOSIS_LOCAL_QDRANT_COLLECTION", "iot_diagnosis_qwen3_512")
        if local_dimensions in {primary.dimensions, dimensions} or local_collection in {
            primary.collection,
            collection,
        }:
            logger.warning("Local fallback must have distinct dimensions and collection; skipped")
            return portable
        try:
            provider = OpenAICompatibleEmbeddingProvider(
                api_key=os.getenv("DIAGNOSIS_LOCAL_EMBEDDING_API_KEY", "local-model-service"),
                base_url=os.getenv(
                    "DIAGNOSIS_LOCAL_EMBEDDING_BASE_URL", "http://retrieval-models:9010/v1"
                ),
                model=os.getenv("DIAGNOSIS_LOCAL_EMBEDDING_MODEL", "Qwen/Qwen3-Embedding-0.6B"),
                dimensions=local_dimensions,
                timeout_seconds=float(os.getenv("DIAGNOSIS_LOCAL_EMBEDDING_TIMEOUT_SECONDS", "20")),
                query_instruction=os.getenv(
                    "DIAGNOSIS_LOCAL_EMBEDDING_QUERY_INSTRUCTION",
                    "Given an IoT fault diagnosis query, retrieve relevant technical passages and verified cases",
                ),
            )
            provider.name = "qwen3_local"
            local = QdrantVectorStore(self.qdrant_url, local_collection, provider)
            self.qdrant_local_fallback = local
            return local if portable is None else ResilientVectorStore(local, portable)
        except Exception as exc:
            logger.warning("Local fallback store unavailable: %s", type(exc).__name__)
            return portable

    def ensure_connected(self, component: str) -> bool:
        if not self.configured.get(component):
            return False
        if getattr(self, component, None) is not None:
            return True
        try:
            if component == "qdrant":
                primary = QdrantVectorStore(self.qdrant_url, self.qdrant_collection)
                fallback = self._build_fallback_store(primary)
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
        local_status = "disabled"
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
        if self.qdrant_local_fallback is not None:
            try:
                local_status = "connected" if self.qdrant_local_fallback.ping() else "unavailable"
            except Exception as exc:
                local_status = "unavailable"
                self.errors.setdefault("qdrant_local_fallback", type(exc).__name__)
        return {
            "sqlite": "connected",
            "qdrant": qdrant_status,
            "qdrant_fallback": fallback_status,
            "qdrant_local_fallback": local_status,
            "errors": self.errors,
        }
