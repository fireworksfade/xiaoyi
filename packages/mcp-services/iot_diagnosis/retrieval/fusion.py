"""RRF（Reciprocal Rank Fusion）融合（Spec §24）。

Dense cosine 与 BM25 score 不同分布，禁止直接 raw score 相加；统一按
RRF(d) = Σ 1 / (k + rank_i(d)) 融合，默认 k = 60。
"""

from __future__ import annotations

from typing import Any

# 候选上允许参与 RRF 的排名通道；lexical_rank 用于 fault_cases /
# realtime_db 等非分块候选，与 Spec §24 的 dense/sparse 公式一致地求和。
RANK_CHANNELS = ("dense_rank", "sparse_rank", "lexical_rank")


def rrf_fuse(candidates: dict[tuple[str, str], dict[str, Any]], k: int = 60) -> None:
    """原地为每个候选计算 rrf_score。"""
    for candidate in candidates.values():
        score = 0.0
        for channel in RANK_CHANNELS:
            rank = candidate.get(channel)
            if rank is not None:
                score += 1 / (k + rank)
        candidate["rrf_score"] = round(score, 6)
