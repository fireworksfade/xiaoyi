"""知识向量的 Qdrant 存储与降级路由。

功能已拆分到：
- qdrant_store.py: Qdrant 向量存储
- manager.py: ExternalStores 统一管理

知识向量从 SQLite 同步到 Qdrant。
"""

from .manager import ExternalStores
from .qdrant_store import QdrantVectorStore
from .resilient_store import ResilientVectorStore

__all__ = ["QdrantVectorStore", "ExternalStores", "ResilientVectorStore"]

