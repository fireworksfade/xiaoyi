"""检索链路包：dense / sparse(BM25) / hybrid(RRF + Reranker)。

`search_knowledge` / `search_fault_cases` 保持原 `iot_diagnosis.retrieval`
模块的公开接口不变（Spec §34 Backward Compatibility）。
"""

from iot_diagnosis.retrieval.config import RetrievalConfig
from iot_diagnosis.retrieval.hybrid import search_fault_cases, search_knowledge

__all__ = ["RetrievalConfig", "search_fault_cases", "search_knowledge"]
