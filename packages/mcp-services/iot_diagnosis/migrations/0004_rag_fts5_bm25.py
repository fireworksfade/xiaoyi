"""RAG 检索链路升级：knowledge_document 结构元数据 + SQLite FTS5 BM25 索引。

- knowledge_document 增加 heading / metadata_json / token_count 三列
  （Spec §5/§6 chunk 数据模型；老库幂等补列）。
- 创建 FTS5 虚拟表 knowledge_chunks_fts（Spec §20），并从存量行全量回填。
  FTS5 模块不可用时跳过建表：sparse 检索降级为 lexical 兜底，不阻塞启动。
- FTS 内容为下划线分隔 + CJK 二元组展开的派生文本（retrieval/bm25.py）。
"""

version = 4
name = "rag_fts5_bm25"

from iot_diagnosis.retrieval.bm25 import FTS_TABLE, rebuild_fts  # noqa: E402

_COMPAT_COLUMNS = {
    "heading": "TEXT NOT NULL DEFAULT ''",
    "metadata_json": "TEXT NOT NULL DEFAULT '{}'",
    "token_count": "INTEGER NOT NULL DEFAULT 0",
}

_FTS_DDL = f"""
CREATE VIRTUAL TABLE IF NOT EXISTS {FTS_TABLE} USING fts5(
    chunk_id UNINDEXED,
    document_id UNINDEXED,
    source UNINDEXED,
    title,
    heading,
    content
);
"""


def _fts5_supported(db) -> bool:  # noqa: ANN001 - sqlite3.Connection
    try:
        db.execute("CREATE VIRTUAL TABLE temp.rag_fts5_probe USING fts5(x)")
        db.execute("DROP TABLE IF EXISTS temp.rag_fts5_probe")
    except Exception:
        return False
    return True


def upgrade(db) -> None:  # noqa: ANN001 - sqlite3.Connection
    existing = {row[1] for row in db.execute("PRAGMA table_info(knowledge_document)").fetchall()}
    for column, definition in _COMPAT_COLUMNS.items():
        if column not in existing:
            db.execute(f"ALTER TABLE knowledge_document ADD COLUMN {column} {definition}")
    if _fts5_supported(db):
        db.execute(_FTS_DDL)
        rebuild_fts(db)
    db.commit()
