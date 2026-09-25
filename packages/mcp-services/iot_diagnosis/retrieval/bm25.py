"""SQLite FTS5 + BM25 稀疏检索（Spec §20-§22、§40）。

FTS5 的 bm25() 返回负值且越小越相关；本模块将其封装为正分数（越大越
相关），调用方不感知原始 score 的符号方向（Spec §20）。索引文本与查询
统一做下划线分隔与 CJK 二元组展开，保证 ERR_CONNECTION_RESET、
mosquitto.conf 等精确技术词以及中文短语可以命中（Spec §40）。
"""

from __future__ import annotations

import re
import sqlite3
from typing import Any

FTS_TABLE = "knowledge_chunks_fts"

# unicode61 tokenizer 的近似 token：unicode 字母数字串（下划线视为分隔）
_RUN_RE = re.compile(r"[^\W_]+", re.UNICODE)
_CJK_RE = re.compile(r"[\u3040-\u30FF\u3400-\u4DBF\u4E00-\u9FFF\uAC00-\uD7AF\uF900-\uFAFF]")
_CJK_RUN_RE = re.compile(r"[\u3040-\u30FF\u3400-\u4DBF\u4E00-\u9FFF\uAC00-\uD7AF\uF900-\uFAFF]+")


def _is_cjk_segment(segment: str) -> bool:
    return bool(_CJK_RUN_RE.fullmatch(segment))


def _split_scripts(run: str) -> list[str]:
    segments: list[str] = []
    current = ""
    current_cjk: bool | None = None
    for char in run:
        is_cjk = bool(_CJK_RE.match(char))
        if current and is_cjk != current_cjk:
            segments.append(current)
            current = ""
        current_cjk = is_cjk
        current += char
    if current:
        segments.append(current)
    return segments


def _expand_tokens(text: str) -> list[str]:
    tokens: list[str] = []
    for run in _RUN_RE.findall(text):
        for segment in _split_scripts(run):
            if _is_cjk_segment(segment) and len(segment) > 1:
                tokens.extend(segment[offset : offset + 2] for offset in range(len(segment) - 1))
            else:
                tokens.append(segment)
    return tokens


def expand_index_text(text: str) -> str:
    """生成 FTS 索引文本：下划线分隔 + CJK 二元组展开。"""
    return " ".join(_expand_tokens(text.replace("_", " ")))


def build_match_query(query: str) -> str:
    """构造 FTS5 MATCH 表达式：词项内 token 保持短语邻接，CJK 二元组取 OR。"""
    phrases: list[str] = []
    for term in query.split():
        latin_tokens: list[str] = []
        for run in _RUN_RE.findall(term.replace("_", " ")):
            for segment in _split_scripts(run):
                if _is_cjk_segment(segment) and len(segment) > 1:
                    phrases.extend(
                        f'"{segment[offset : offset + 2]}"' for offset in range(len(segment) - 1)
                    )
                else:
                    latin_tokens.append(segment)
        if latin_tokens:
            phrases.append('"' + " ".join(latin_tokens) + '"')
    return " OR ".join(dict.fromkeys(phrases))


def fts_ready(db: sqlite3.Connection) -> bool:
    try:
        row = db.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type = 'table' AND name = ?",
            (FTS_TABLE,),
        ).fetchone()
    except sqlite3.Error:
        return False
    return bool(row and row[0])


def search_bm25(
    db: sqlite3.Connection,
    query: str,
    sources: list[str],
    top_k: int,
) -> list[dict[str, Any]]:
    """FTS5 BM25 检索，返回按相关性降序的正分数候选（Spec §20/§22）。"""
    if top_k <= 0 or not sources or not query.strip() or not fts_ready(db):
        return []
    match_query = build_match_query(query)
    if not match_query:
        return []
    placeholders = ",".join("?" for _ in sources)
    rows = db.execute(
        f"""
        SELECT chunk_id, document_id, source, title, heading,
               bm25({FTS_TABLE}) AS rank_score
        FROM {FTS_TABLE}
        WHERE {FTS_TABLE} MATCH ? AND source IN ({placeholders})
        ORDER BY rank_score
        LIMIT ?
        """,
        [match_query, *sources, top_k],
    ).fetchall()
    results: list[dict[str, Any]] = []
    for row in rows:
        results.append(
            {
                "id": row["chunk_id"],
                "document_id": row["document_id"],
                "source": row["source"],
                "title": row["title"],
                "heading": row["heading"],
                # bm25() 越负越相关，封装为正分数（Spec §20）
                "score": round(-float(row["rank_score"]), 6),
            }
        )
    return results


def insert_fts_rows(db: sqlite3.Connection, items: list[dict[str, Any]]) -> None:
    if not items:
        return
    db.executemany(
        f"""
        INSERT INTO {FTS_TABLE}(chunk_id, document_id, source, title, heading, content)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        [
            (
                item["chunk_id"],
                item.get("document_id") or "",
                item["source"],
                expand_index_text(item.get("title") or ""),
                expand_index_text(item.get("heading") or ""),
                expand_index_text(item.get("content") or ""),
            )
            for item in items
        ],
    )


def delete_fts_document(db: sqlite3.Connection, source: str, document_id: str) -> None:
    db.execute(
        f"DELETE FROM {FTS_TABLE} WHERE source = ? AND document_id = ?",
        (source, document_id),
    )


def rebuild_fts(db: sqlite3.Connection) -> int:
    """清空并从 knowledge_document 全量重建 FTS 索引，返回索引行数。"""
    if not fts_ready(db):
        return 0
    db.execute(f"DELETE FROM {FTS_TABLE}")
    rows = db.execute(
        "SELECT source_id, COALESCE(document_id, ''), source, title,"
        " COALESCE(heading, ''), content FROM knowledge_document"
    ).fetchall()
    items = [
        {
            "chunk_id": row[0],
            "document_id": row[1],
            "source": row[2],
            "title": row[3],
            "heading": row[4],
            "content": row[5],
        }
        for row in rows
    ]
    insert_fts_rows(db, items)
    return len(items)
