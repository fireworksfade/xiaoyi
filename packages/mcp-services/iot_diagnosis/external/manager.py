"""ExternalStores 统一管理类 - 简化版（仅 Qdrant）。"""

from __future__ import annotations

import logging
import os
from typing import Any

from .qdrant_store import QdrantVectorStore

logger = logging.getLogger("xiaoyi.iot_diagnosis.external")


class ExternalStores:
    def __init__(self):
        self.qdrant: QdrantVectorStore | None = None
        self.errors: dict[str, str] = {}
        self.qdrant_url = os.getenv("DIAGNOSIS_QDRANT_URL", "").strip()
        self.qdrant_collection = os.getenv("DIAGNOSIS_QDRANT_COLLECTION", "iot_diagnosis_knowledge")
        self.configured = {
            "qdrant": bool(self.qdrant_url),
        }
        self.ensure_connected("qdrant")

    def ensure_connected(self, component: str) -> bool:
        if not self.configured.get(component):
            return False
        if getattr(self, component, None) is not None:
            return True
        try:
            if component == "qdrant":
                self.qdrant = QdrantVectorStore(
                    self.qdrant_url,
                    self.qdrant_collection,
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
        self.ensure_connected("qdrant")
        if self.qdrant:
            try:
                qdrant_status = "connected" if self.qdrant.ping() else "fallback"
                if qdrant_status == "connected":
                    self.errors.pop("qdrant", None)
            except Exception as exc:
                qdrant_status = "fallback"
                self.errors["qdrant"] = type(exc).__name__
        return {
            "sqlite": "connected",
            "qdrant": qdrant_status,
            "errors": self.errors,
        }

