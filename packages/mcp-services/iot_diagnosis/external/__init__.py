"""外部存储集成 - 向后兼容导入层。

功能已拆分到：
- qdrant_store.py: Qdrant 向量存储
- manager.py: ExternalStores 统一管理

注意: MySQL 镜像已移除，数据直接从 SQLite → Qdrant 同步
"""

from .qdrant_store import QdrantVectorStore
from .manager import ExternalStores

__all__ = ["QdrantVectorStore", "ExternalStores"]

