"""Chunk / Block 数据模型（Spec §5、§9）。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# block_type 取值（Spec §5 推荐集合；heading 为解析期内部块，
# 不会作为最终 chunk 的 block_type 出现）。
BLOCK_TYPES = {
    "heading",
    "paragraph",
    "code",
    "log",
    "list",
    "steps",
    "table",
    "quote",
    "mixed",
}


@dataclass
class Block:
    """Structure-aware Parser 输出的结构块。"""

    block_type: str
    content: str
    heading_path: list[str] = field(default_factory=list)
    language: str | None = None
    level: int | None = None
    # table 块保留表头行，供超长表格按行分块时重复 header（Spec §12）
    table_header: str | None = None


@dataclass
class Chunk:
    """最终分块。content 已包含注入的 heading context（Spec §8）。"""

    content: str
    document_id: str
    chunk_index: int

    title: str | None = None
    heading_path: list[str] | None = None
    block_type: str | None = None
    token_count: int | None = None
    source: str | None = None

    metadata: dict[str, Any] | None = None

    def to_metadata_json(self) -> str:
        import json

        return json.dumps(
            {
                "heading_path": self.heading_path or [],
                "block_type": self.block_type,
                "token_count": self.token_count,
                "metadata": self.metadata or {},
            },
            ensure_ascii=False,
            sort_keys=True,
        )
