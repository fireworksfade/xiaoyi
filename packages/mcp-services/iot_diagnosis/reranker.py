from __future__ import annotations

import json
import math
import os
import re
from collections import Counter
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def _tokens(text: str) -> list[str]:
    lowered = text.lower()
    words = re.findall(r"[a-z0-9_]+|[\u4e00-\u9fff]", lowered)
    compact = re.sub(r"\s+", "", lowered)
    return words + [compact[index : index + 3] for index in range(max(0, len(compact) - 2))]


def lexical_similarity(query: str, content: str) -> float:
    left = Counter(_tokens(query))
    right = Counter(_tokens(content))
    if not left or not right:
        return 0.0
    dot = sum(value * right.get(token, 0) for token, value in left.items())
    norm_left = math.sqrt(sum(value * value for value in left.values()))
    norm_right = math.sqrt(sum(value * value for value in right.values()))
    return dot / (norm_left * norm_right) if norm_left and norm_right else 0.0


class Reranker(Protocol):
    def rerank(
        self,
        query: str,
        candidates: list[dict[str, Any]],
        *,
        expected_source: str,
        top_k: int,
    ) -> list[dict[str, Any]]: ...


class WeightedReranker:
    """Deterministic default that can be replaced by a learned reranker."""

    name = "weighted"
    used_fallback = False

    def rerank(
        self,
        query: str,
        candidates: list[dict[str, Any]],
        *,
        expected_source: str,
        top_k: int,
    ) -> list[dict[str, Any]]:
        ranked = []
        for candidate in candidates:
            retrieval_score = min(max(float(candidate.get("retrieval_score") or 0.0), 0.0), 1.0)
            lexical_score = lexical_similarity(query, str(candidate.get("content") or ""))
            source_bonus = 0.05 if candidate.get("source") == expected_source else 0.0
            score = min(
                1.0,
                0.72 * retrieval_score + 0.20 * lexical_score + source_bonus,
            )
            item = {**candidate, "score": round(score, 4)}
            item.pop("retrieval_score", None)
            ranked.append(item)
        ranked.sort(key=lambda item: item["score"], reverse=True)
        return ranked[:top_k]


class RemoteReranker:
    """Cross-encoder reranker served by a local service or compatible API.

    Qwen 的相关性概率在技术文档候选上经常集中在 0.99 附近，直接按微小的
    浮点差异排序会破坏已经可靠的 RRF 次序。最终排序因此使用 rank-level
    稳定化：Qwen rank 为主、进入 reranker 前的 retrieval rank 为辅。
    """

    name = "qwen3_remote"

    def __init__(
        self,
        url: str,
        timeout_seconds: float = 30,
        *,
        api_key: str = "",
        model: str = "",
        api_format: str = "compatible",
        fallback: Reranker | None = None,
    ):
        self.url = url
        self.timeout_seconds = timeout_seconds
        self.api_key = api_key
        self.model = model
        if api_format not in {"compatible", "dashscope"}:
            raise ValueError("RERANKER_API_FORMAT_INVALID")
        self.api_format = api_format
        if api_format == "dashscope":
            self.name = "dashscope_remote"
        self.fallback = fallback if fallback is not None else WeightedReranker()
        self.used_fallback = False
        self.active_provider = self.name
        self.rank_fusion_k = int(os.getenv("RAG_RERANKER_RANK_FUSION_K", "60"))
        self.reranker_rank_weight = float(os.getenv("RAG_RERANKER_RANK_WEIGHT", "2.0"))
        if self.rank_fusion_k <= 0 or self.reranker_rank_weight <= 0:
            raise ValueError("RERANKER_RANK_CONFIG_INVALID")

    def rerank(
        self,
        query: str,
        candidates: list[dict[str, Any]],
        *,
        expected_source: str,
        top_k: int,
    ) -> list[dict[str, Any]]:
        self.used_fallback = False
        self.active_provider = self.name
        if not candidates:
            return []
        request_body: dict[str, Any] = {
            "query": query,
            "documents": [str(item.get("content") or "") for item in candidates],
            # 排名融合需要取得全部候选的模型排名。
            "top_n": len(candidates),
        }
        if self.model:
            request_body["model"] = self.model
        if self.api_format == "dashscope":
            request_body = {
                "model": self.model,
                "input": {"query": query, "documents": request_body["documents"]},
                "parameters": {"top_n": len(candidates), "return_documents": False},
            }
        payload = json.dumps(
            request_body,
            ensure_ascii=False,
        ).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        request = Request(
            self.url,
            data=payload,
            method="POST",
            headers=headers,
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                result = json.loads(response.read().decode("utf-8"))
            results = (
                result["output"]["results"] if self.api_format == "dashscope" else result["results"]
            )
            if not isinstance(results, list) or len(results) != len(candidates):
                raise ValueError("RERANKER_RESULTS_INCOMPLETE")
            ranked = []
            seen = set()
            for reranker_rank, item in enumerate(results, 1):
                retrieval_index = item["index"]
                if (
                    type(retrieval_index) is not int
                    or not 0 <= retrieval_index < len(candidates)
                    or retrieval_index in seen
                ):
                    raise ValueError("RERANKER_INDEX_INVALID")
                seen.add(retrieval_index)
                score = float(
                    item["relevance_score"] if "relevance_score" in item else item["score"]
                )
                if not math.isfinite(score):
                    raise ValueError("RERANKER_SCORE_INVALID")
                candidate = dict(candidates[retrieval_index])
                candidate["score"] = round(score, 4)
                candidate.pop("retrieval_score", None)
                candidate["_rerank_fusion_score"] = self.reranker_rank_weight / (
                    self.rank_fusion_k + reranker_rank
                ) + 1 / (self.rank_fusion_k + retrieval_index + 1)
                ranked.append(candidate)
            ranked.sort(key=lambda item: item["_rerank_fusion_score"], reverse=True)
            for candidate in ranked:
                candidate.pop("_rerank_fusion_score", None)
            return ranked[:top_k]
        except (
            HTTPError,
            URLError,
            TimeoutError,
            ValueError,
            KeyError,
            IndexError,
            TypeError,
        ):
            self.used_fallback = True
            ranked = self.fallback.rerank(
                query,
                candidates,
                expected_source=expected_source,
                top_k=top_k,
            )
            self.active_provider = getattr(
                self.fallback, "active_provider", getattr(self.fallback, "name", "weighted")
            )
            return ranked


def reranker_from_env() -> Reranker:
    provider = os.getenv("DIAGNOSIS_RERANKER_PROVIDER", "weighted").strip().lower()
    if provider == "weighted":
        return WeightedReranker()
    if provider in {"remote", "qwen3", "dashscope"}:
        url = os.getenv("DIAGNOSIS_RERANKER_URL", "").strip()
        api_key = os.getenv("DIAGNOSIS_RERANKER_API_KEY", "").strip()
        model = os.getenv("DIAGNOSIS_RERANKER_MODEL", "").strip()
        if not url or (provider == "dashscope" and (not api_key or not model)):
            raise ValueError("RERANKER_PROVIDER_NOT_CONFIGURED")
        fallback = None
        local_enabled = os.getenv("DIAGNOSIS_LOCAL_RERANKER_FALLBACK", "false").strip().lower()
        if local_enabled in {"1", "true", "yes"}:
            local_url = os.getenv(
                "DIAGNOSIS_LOCAL_RERANKER_URL", "http://retrieval-models:9010/rerank"
            ).strip()
            if local_url != url:
                fallback = RemoteReranker(
                    local_url,
                    float(os.getenv("DIAGNOSIS_LOCAL_RERANKER_TIMEOUT_SECONDS", "30")),
                    api_key=os.getenv("DIAGNOSIS_LOCAL_RERANKER_API_KEY", "").strip(),
                    model=os.getenv(
                        "DIAGNOSIS_LOCAL_RERANKER_MODEL", "Qwen/Qwen3-Reranker-0.6B"
                    ).strip(),
                )
                fallback.name = "qwen3_local"
        return RemoteReranker(
            url,
            float(os.getenv("DIAGNOSIS_RERANKER_TIMEOUT_SECONDS", "30")),
            api_key=api_key,
            model=model,
            api_format="dashscope" if provider == "dashscope" else "compatible",
            fallback=fallback,
        )
    raise ValueError("RERANKER_PROVIDER_INVALID")
