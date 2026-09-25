"""外部存储集成 - 向后兼容导入层。

所有功能已迁移到 external/ 包。
注意: MySQL 镜像已移除
"""

from .external import ExternalStores, QdrantVectorStore

__all__ = ["ExternalStores", "QdrantVectorStore"]

