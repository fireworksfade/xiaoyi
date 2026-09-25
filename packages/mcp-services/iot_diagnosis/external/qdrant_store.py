"""Qdrant 向量存储集成。"""

from __future__ import annotations

import json
import logging
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from iot_diagnosis.embeddings import EmbeddingProvider, embedding_provider_from_env

logger = logging.getLogger("xiaoyi.iot_diagnosis.external")


class QdrantVectorStore:
    def __init__(
        self,
        url: str,
        collection: str,
        embedding_provider: EmbeddingProvider | None = None,
    ):
        self.url = url.rstrip("/")
        self.collection = collection
        self.embedding_provider = embedding_provider or embedding_provider_from_env()
        self.dimensions = self.embedding_provider.dimensions
        self._ensure_collection()

    def _ensure_collection(self) -> None:
        path = f"/collections/{self.collection}"
        try:
            response = self._request("GET", path)
            configured_size = (
                (((response.get("result") or {}).get("config") or {}).get("params") or {})
                .get("vectors", {})
                .get("size")
            )
            if configured_size is not None and int(configured_size) != self.dimensions:
                raise ValueError("QDRANT_COLLECTION_DIMENSIONS_MISMATCH")
            return
        except HTTPError as exc:
            if exc.code != 404:
                raise
        self._request(
            "PUT",
            path,
            {"vectors": {"size": self.dimensions, "distance": "Cosine"}},
        )

    def _request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> Any:
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        request = Request(
            f"{self.url}{path}",
            data=body,
            method=method,
            headers={"Content-Type": "application/json"},
        )
        with urlopen(request, timeout=10) as response:
            return json.loads(response.read().decode("utf-8"))

    def upsert(self, item: dict[str, Any]) -> bool:
        return self.upsert_many([item])

    def upsert_many(self, items: list[dict[str, Any]]) -> bool:
        if not items:
            return True
        embed_many = getattr(self.embedding_provider, "embed_many", None)
        contents = [str(item["content"]) for item in items]
        vectors = (
            embed_many(contents)
            if embed_many
            else [self.embedding_provider.embed(content) for content in contents]
        )
        if len(vectors) != len(items):
            raise RuntimeError("EMBEDDING_BATCH_SIZE_MISMATCH")
        points = []
        for item, vector in zip(items, vectors, strict=True):
            source = str(item["source"])
            source_id = str(item["id"])
            point_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{source}:{source_id}"))
            points.append({"id": point_id, "vector": vector, "payload": item})
        self._request(
            "PUT",
            f"/collections/{self.collection}/points?wait=true",
            {"points": points},
        )
        return True

    def delete_document(self, item: dict[str, Any]) -> bool:
        self._request(
            "POST",
            f"/collections/{self.collection}/points/delete?wait=true",
            {
                "filter": {
                    "must": [
                        {"key": "source", "match": {"value": item["source"]}},
                        {"key": "document_id", "match": {"value": item["document_id"]}},
                    ]
                }
            },
        )
        return True

    def search(
        self,
        query: str,
        sources: list[str],
        top_k: int,
        query_vector: list[float] | None = None,
    ) -> list[dict[str, Any]]:
        vector = (
            query_vector
            if query_vector is not None
            else self.embedding_provider.embed(query, is_query=True)
        )
        payload: dict[str, Any] = {
            "query": vector,
            "limit": top_k,
            "with_payload": True,
        }
        if sources:
            payload["filter"] = {"must": [{"key": "source", "match": {"any": sources}}]}
        response = self._request("POST", f"/collections/{self.collection}/points/query", payload)
        points = (response.get("result") or {}).get("points") or []
        return [
            {**dict(point.get("payload") or {}), "score": float(point.get("score") or 0.0)}
            for point in points
        ]

    def ping(self) -> bool:
        response = self._request("GET", f"/collections/{self.collection}")
        return response.get("status") == "ok"


