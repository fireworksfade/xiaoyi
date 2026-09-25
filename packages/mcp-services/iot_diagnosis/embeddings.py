from __future__ import annotations

import hashlib
import json
import math
import os
import re
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class EmbeddingProvider(Protocol):
    name: str
    dimensions: int

    def embed(self, text: str, *, is_query: bool = False) -> list[float]: ...

    def embed_many(self, texts: list[str], *, is_query: bool = False) -> list[list[float]]: ...


class HashEmbeddingProvider:
    name = "hash"

    def __init__(self, dimensions: int = 384):
        self.dimensions = dimensions

    def embed(self, text: str, *, is_query: bool = False) -> list[float]:
        tokens = re.findall(r"[a-z0-9_]+|[\u4e00-\u9fff]", text.lower())
        compact = re.sub(r"\s+", "", text.lower())
        tokens.extend(compact[index : index + 3] for index in range(max(0, len(compact) - 2)))
        vector = [0.0] * self.dimensions
        for token in tokens:
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
            bucket = int.from_bytes(digest[:4], "big") % self.dimensions
            sign = 1.0 if digest[4] & 1 else -1.0
            vector[bucket] += sign
        norm = math.sqrt(sum(value * value for value in vector))
        return [value / norm for value in vector] if norm else vector

    def embed_many(self, texts: list[str], *, is_query: bool = False) -> list[list[float]]:
        return [self.embed(text, is_query=is_query) for text in texts]


class OpenAICompatibleEmbeddingProvider:
    name = "openai_compatible"

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        dimensions: int,
        timeout_seconds: float = 20,
    ):
        if not api_key or not model:
            raise ValueError("EMBEDDING_PROVIDER_NOT_CONFIGURED")
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.dimensions = dimensions
        self.timeout_seconds = timeout_seconds
        self.query_instruction = os.getenv(
            "DIAGNOSIS_EMBEDDING_QUERY_INSTRUCTION",
            "Given an IoT fault diagnosis query, retrieve relevant technical passages and verified cases",
        ).strip()

    def embed(self, text: str, *, is_query: bool = False) -> list[float]:
        return self.embed_many([text], is_query=is_query)[0]

    def embed_many(self, texts: list[str], *, is_query: bool = False) -> list[list[float]]:
        if not texts:
            return []
        embedding_input = [
            f"Instruct: {self.query_instruction}\nQuery:{text}"
            if is_query and self.query_instruction
            else text
            for text in texts
        ]
        body = json.dumps(
            {"model": self.model, "input": embedding_input, "dimensions": self.dimensions}
        ).encode("utf-8")
        request = Request(
            f"{self.base_url}/embeddings",
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
            rows = payload["data"]
            by_index = {int(row["index"]): row["embedding"] for row in rows}
            if set(by_index) != set(range(len(texts))) or len(rows) != len(texts):
                raise ValueError("invalid embedding response indices")
            vectors = [[float(value) for value in by_index[index]] for index in range(len(texts))]
        except (
            HTTPError,
            URLError,
            TimeoutError,
            ValueError,
            KeyError,
            IndexError,
            TypeError,
        ) as exc:
            raise RuntimeError("EMBEDDING_REQUEST_FAILED") from exc
        if any(len(vector) != self.dimensions for vector in vectors):
            raise RuntimeError("EMBEDDING_DIMENSIONS_MISMATCH")
        return vectors


def embedding_provider_from_env() -> EmbeddingProvider:
    provider = os.getenv("DIAGNOSIS_EMBEDDING_PROVIDER", "hash").strip().lower()
    dimensions = int(os.getenv("DIAGNOSIS_EMBEDDING_DIMENSIONS", "384"))
    if provider == "hash":
        return HashEmbeddingProvider(dimensions)
    if provider in {"openai", "openai_compatible"}:
        return OpenAICompatibleEmbeddingProvider(
            api_key=os.getenv("DIAGNOSIS_EMBEDDING_API_KEY", ""),
            base_url=os.getenv("DIAGNOSIS_EMBEDDING_BASE_URL", "https://api.openai.com/v1"),
            model=os.getenv("DIAGNOSIS_EMBEDDING_MODEL", ""),
            dimensions=dimensions,
            timeout_seconds=float(os.getenv("DIAGNOSIS_EMBEDDING_TIMEOUT_SECONDS", "20")),
        )
    raise ValueError("EMBEDDING_PROVIDER_INVALID")


def retrieval_model_status() -> dict[str, Any]:
    provider = os.getenv("DIAGNOSIS_EMBEDDING_PROVIDER", "hash").strip().lower()
    health_url = os.getenv("DIAGNOSIS_RETRIEVAL_MODEL_HEALTH_URL", "").strip()
    if provider == "hash" and not health_url:
        return {"status": "disabled", "provider": "hash"}
    if not health_url:
        return {"status": "unavailable", "provider": provider, "error": "NOT_CONFIGURED"}
    request = Request(health_url, method="GET", headers={"Accept": "application/json"})
    try:
        with urlopen(
            request,
            timeout=float(os.getenv("DIAGNOSIS_RETRIEVAL_MODEL_HEALTH_TIMEOUT_SECONDS", "3")),
        ) as response:
            payload = json.loads(response.read().decode("utf-8"))
        status = "ready" if payload.get("status") == "ready" else "unavailable"
        return {
            "status": status,
            "provider": provider,
            "device": payload.get("device"),
            "embedding_model": payload.get("embedding_model"),
            "reranker_model": payload.get("reranker_model"),
            "dimensions": payload.get("dimensions"),
        }
    except (HTTPError, URLError, TimeoutError, ValueError, TypeError) as exc:
        return {
            "status": "unavailable",
            "provider": provider,
            "error": type(exc).__name__,
        }
