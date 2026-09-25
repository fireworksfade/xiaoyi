"""检索配置与 Feature Flags（Spec §17、§35、§42）。

默认值与 Spec §42 的 Default Configuration 一致；允许通过环境变量分别
关闭组件用于测试和 fallback（Spec §35）。
"""

from __future__ import annotations

import os
from dataclasses import dataclass

STRATEGIES = ("dense", "sparse", "hybrid")


def _flag(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    return raw.strip().lower() not in {"0", "false", "no", "off"}


def _int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"{name.upper()}_INVALID") from exc


@dataclass(frozen=True)
class RetrievalConfig:
    strategy: str = "hybrid"
    dense_top_k: int = 40
    sparse_top_k: int = 40
    rrf_k: int = 60
    rerank_candidate_limit: int = 60
    enable_sparse: bool = True
    enable_rrf: bool = True
    enable_reranker: bool = True
    debug: bool = False

    def __post_init__(self) -> None:
        if self.strategy not in STRATEGIES:
            raise ValueError("RETRIEVAL_STRATEGY_INVALID")
        if self.dense_top_k <= 0 or self.sparse_top_k <= 0:
            raise ValueError("RETRIEVAL_TOP_K_INVALID")
        if self.rrf_k <= 0 or self.rerank_candidate_limit <= 0:
            raise ValueError("RETRIEVAL_CONFIG_INVALID")

    @classmethod
    def from_env(cls, strategy: str | None = None) -> "RetrievalConfig":
        env_strategy = os.getenv("RAG_RETRIEVAL_STRATEGY") or "hybrid"
        raw_strategy = strategy if strategy else env_strategy
        return cls(
            strategy=raw_strategy.strip().lower(),
            dense_top_k=_int("RAG_DENSE_TOP_K", 40),
            sparse_top_k=_int("RAG_SPARSE_TOP_K", 40),
            rrf_k=_int("RAG_RRF_K", 60),
            rerank_candidate_limit=_int("RAG_RERANK_CANDIDATE_LIMIT", 60),
            enable_sparse=_flag("RAG_ENABLE_SPARSE", True),
            enable_rrf=_flag("RAG_ENABLE_RRF", True),
            enable_reranker=_flag("RAG_ENABLE_RERANKER", True),
            debug=_flag("RAG_RETRIEVAL_DEBUG", False),
        )
