"""One request contract and response validator for sync and async embeddings."""

import math
from dataclasses import dataclass
from urllib.parse import urlsplit

from .http import AsyncJsonClient, JsonClient


@dataclass(frozen=True)
class EmbeddingConfig:
    base_url: str
    model: str
    dimensions: int
    api_key: str | None = None
    query_instruction: str = ""

    @property
    def api_base_url(self):
        base = self.base_url.rstrip("/")
        if base.endswith("/embeddings"):
            return base.removesuffix("/embeddings")
        return base + "/v1" if not urlsplit(base).path else base

    def payload(self, texts, *, is_query=False):
        return {
            "model": self.model,
            "dimensions": self.dimensions,
            "input": [
                f"Instruct: {self.query_instruction}\nQuery:{text}"
                if is_query and self.query_instruction
                else text
                for text in texts
            ],
        }

    def vectors(self, payload, count):
        rows = payload["data"]
        # Some compatible single-input services omit the optional index.
        indices = [
            int(row.get("index", 0)) if count == 1 else int(row["index"])
            for row in rows
        ]
        if len(rows) != count or set(indices) != set(range(count)):
            raise ValueError("EMBEDDING_RESPONSE_INDICES_INVALID")
        by_index = dict(zip(indices, rows, strict=True))
        vectors = [[float(v) for v in by_index[i]["embedding"]] for i in range(count)]
        if any(len(vector) != self.dimensions for vector in vectors):
            raise ValueError("EMBEDDING_DIMENSIONS_MISMATCH")
        if any(not math.isfinite(value) for vector in vectors for value in vector):
            raise ValueError("EMBEDDING_VALUES_INVALID")
        return vectors


class EmbeddingClient:
    def __init__(self, config, *, timeout_seconds=20, opener=None):
        self.config = config
        self.http = JsonClient(
            config.api_base_url,
            timeout_seconds=timeout_seconds,
            api_key=config.api_key,
            opener=opener,
        )

    def embed_many(self, texts, *, is_query=False):
        if not texts:
            return []
        response = self.http.request(
            "POST", "/embeddings", self.config.payload(texts, is_query=is_query)
        )
        return self.config.vectors(response, len(texts))


class AsyncEmbeddingClient:
    def __init__(self, config, client):
        self.config = config
        self.http = AsyncJsonClient(client, config.api_base_url, api_key=config.api_key)

    async def embed(self, text):
        response = await self.http.request(
            "POST", "/embeddings", self.config.payload([text])
        )
        return self.config.vectors(response, 1)[0]
