from __future__ import annotations

import hashlib
import math
import os
import re
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

from xiaoyi_retrieval.embeddings import EmbeddingClient, EmbeddingConfig


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
        client = EmbeddingClient(
            EmbeddingConfig(
                self.base_url, self.model, self.dimensions, self.api_key, self.query_instruction
            ),
            timeout_seconds=self.timeout_seconds,
            opener=urlopen,
        )
        try:
            return client.embed_many(texts, is_query=is_query)
        except (
            HTTPError,
            URLError,
            TimeoutError,
            ValueError,
            KeyError,
            IndexError,
            TypeError,
        ) as exc:
            if str(exc) == "EMBEDDING_DIMENSIONS_MISMATCH":
                raise RuntimeError("EMBEDDING_DIMENSIONS_MISMATCH") from exc
            raise RuntimeError("EMBEDDING_REQUEST_FAILED") from exc


class ResilientEmbeddingProvider:
    """主 embedding 不可用时回落到本地确定性 provider（兜底档位）。

    仅在运行期请求失败时切换；构造期配置缺失仍然直接报错，避免把
    配置错误静默降级。两个 provider 维度必须不同，向量存储依赖维度
    区分向量来源并路由到对应集合。
    """

    def __init__(self, primary: EmbeddingProvider, fallback: EmbeddingProvider):
        if primary.dimensions == fallback.dimensions:
            raise ValueError("EMBEDDING_FALLBACK_DIMENSIONS_CONFLICT")
        self.primary = primary
        self.fallback = fallback
        self.name = primary.name
        self.dimensions = primary.dimensions
        self.fallback_dimensions = fallback.dimensions

    def embed(self, text: str, *, is_query: bool = False) -> list[float]:
        try:
            return self.primary.embed(text, is_query=is_query)
        except Exception:
            return self.fallback.embed(text, is_query=is_query)

    def embed_many(self, texts: list[str], *, is_query: bool = False) -> list[list[float]]:
        try:
            return self.primary.embed_many(texts, is_query=is_query)
        except Exception:
            return self.fallback.embed_many(texts, is_query=is_query)


def embedding_provider_from_env() -> EmbeddingProvider:
    provider = os.getenv("DIAGNOSIS_EMBEDDING_PROVIDER", "hash").strip().lower()
    dimensions = int(
        os.getenv("DIAGNOSIS_EMBEDDING_DIMENSIONS")
        or (
            os.getenv("RETRIEVAL_EMBEDDING_DIMENSIONS")
            if provider in {"openai", "openai_compatible"}
            else None
        )
        or "384"
    )
    if provider == "hash":
        return HashEmbeddingProvider(dimensions)
    if provider in {"openai", "openai_compatible"}:
        return OpenAICompatibleEmbeddingProvider(
            api_key=os.getenv("DIAGNOSIS_EMBEDDING_API_KEY")
            or os.getenv("RETRIEVAL_EMBEDDING_API_KEY", ""),
            base_url=os.getenv("DIAGNOSIS_EMBEDDING_BASE_URL")
            or os.getenv("RETRIEVAL_EMBEDDING_BASE_URL", "https://api.openai.com/v1"),
            model=os.getenv("DIAGNOSIS_EMBEDDING_MODEL")
            or os.getenv("RETRIEVAL_EMBEDDING_MODEL", ""),
            dimensions=dimensions,
            timeout_seconds=float(os.getenv("DIAGNOSIS_EMBEDDING_TIMEOUT_SECONDS", "20")),
        )
    raise ValueError("EMBEDDING_PROVIDER_INVALID")
