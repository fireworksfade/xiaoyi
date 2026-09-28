"""检索链路包：dense / sparse(BM25) / hybrid(RRF + Reranker)。

`search_knowledge` 保持原 `iot_diagnosis.retrieval` 模块的公开接口
（Spec §34 Backward Compatibility）。旧故障案例检索已随案例库退役。
"""

from iot_diagnosis.retrieval.config import RetrievalConfig
from iot_diagnosis.retrieval.hybrid import search_knowledge

__all__ = ["RetrievalConfig", "search_knowledge"]
