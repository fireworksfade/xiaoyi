import logging
import re
import time
from typing import Any

from iot_diagnosis.repository_common import iso
from iot_diagnosis.retrieval.bm25 import (
    delete_fts_document,
    fts_ready,
    insert_fts_rows,
    search_bm25,
)

logger = logging.getLogger("xiaoyi.iot_diagnosis.repository")


class KnowledgeDocumentMixin:
    def knowledge_documents(self, sources: list[str]) -> list[dict[str, Any]]:
        selected = [item for item in sources if item != "realtime_db"]
        if not selected:
            return []
        placeholders = ",".join("?" for _ in selected)
        with self._connect() as db:
            rows = db.execute(
                f"SELECT * FROM knowledge_document WHERE source IN ({placeholders})",
                selected,
            ).fetchall()
        return [dict(row) for row in rows]

    def list_knowledge_documents(
        self,
        source: str | None = None,
        device_type: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> dict[str, Any]:
        query = "SELECT * FROM knowledge_document"
        clauses: list[str] = []
        params: list[Any] = []
        if source:
            clauses.append("source = ?")
            params.append(source)
        if device_type:
            clauses.append("device_type = ?")
            params.append(device_type)
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY source, document_id, chunk_index, source_id"
        with self._connect() as db:
            rows = [dict(row) for row in db.execute(query, params).fetchall()]

        documents: dict[tuple[str, str], dict[str, Any]] = {}
        for row in rows:
            document_id = row.get("document_id") or row["source_id"].split("#", 1)[0]
            key = (row["source"], document_id)
            if key not in documents:
                documents[key] = {
                    "source": row["source"],
                    "document_id": document_id,
                    "title": re.sub(r" \(\d+/\d+\)$", "", row["title"]),
                    "device_type": row.get("device_type"),
                    "chunk_count": 0,
                    "content_chars": 0,
                    "created_at": row["created_at"],
                }
            item = documents[key]
            item["chunk_count"] += 1
            item["content_chars"] += len(row["content"])
            if row["created_at"] > item["created_at"]:
                item["created_at"] = row["created_at"]

        items = list(documents.values())
        total = len(items)
        return {
            "items": items[offset : offset + limit],
            "total": total,
            "limit": limit,
            "offset": offset,
        }

    def replace_knowledge_document(
        self,
        *,
        source: str,
        document_id: str,
        title: str,
        chunks: list[Any],
        device_type: str | None,
    ) -> dict[str, Any]:
        """整体替换一个逻辑文档；chunks 为 str 或含 content/heading/
        metadata_json/token_count 的 dict（Spec §5 chunk 数据模型）。"""
        created_at = iso()
        base_title = title.strip()
        total = len(chunks)
        items = []
        for index, chunk in enumerate(chunks):
            payload = {"content": chunk} if isinstance(chunk, str) else dict(chunk)
            items.append(
                {
                    "source": source,
                    "source_id": f"{document_id}#{index:04d}",
                    "document_id": document_id,
                    "chunk_index": index,
                    "title": (base_title if total == 1 else f"{base_title} ({index + 1}/{total})"),
                    "content": payload["content"],
                    "heading": str(payload.get("heading") or ""),
                    "metadata_json": str(payload.get("metadata_json") or "{}"),
                    "token_count": int(payload.get("token_count") or 0),
                    "device_type": device_type,
                    "created_at": created_at,
                }
            )
        with self._lock, self._connect() as db:
            db.execute(
                """DELETE FROM knowledge_document
                WHERE source = ? AND (
                    document_id = ? OR source_id = ? OR source_id LIKE ?
                )""",
                (source, document_id, document_id, f"{document_id}#%"),
            )
            db.executemany(
                """INSERT INTO knowledge_document
                (source, source_id, title, content, device_type, created_at, document_id,
                 chunk_index, heading, metadata_json, token_count)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                [
                    (
                        item["source"],
                        item["source_id"],
                        item["title"],
                        item["content"],
                        item["device_type"],
                        item["created_at"],
                        item["document_id"],
                        item["chunk_index"],
                        item["heading"],
                        item["metadata_json"],
                        item["token_count"],
                    )
                    for item in items
                ],
            )
            self._sync_fts(
                db,
                delete=(source, document_id),
                rows=[
                    {
                        "chunk_id": item["source_id"],
                        "document_id": document_id,
                        "source": source,
                        "title": item["title"],
                        "heading": item["heading"],
                        "content": item["content"],
                    }
                    for item in items
                ],
            )

        delete_payload = {"source": source, "document_id": document_id}
        vector_delete = self._external_write("qdrant", "delete_document", delete_payload)
        vector_items = [self._knowledge_vector_document(item) for item in items]
        indexed_count = self._qdrant_write_many(vector_items)
        vector_indexed = vector_delete and indexed_count == len(vector_items)
        sync_status = (
            "complete"
            if vector_indexed
            else ("pending" if self.external_sync_status()["pending"] else "local_only")
        )
        return {
            "source": source,
            "document_id": document_id,
            "chunk_count": len(items),
            "chunk_ids": [item["source_id"] for item in items],
            "vector_indexed": vector_indexed,
            "sync_status": sync_status,
        }

    def delete_knowledge_document(
        self,
        *,
        source: str,
        document_id: str,
    ) -> dict[str, Any]:
        allowed_sources = {"mqtt_docs", "wifi_docs", "sensor_docs", "device_docs"}
        if source not in allowed_sources:
            raise ValueError("INVALID_DOCUMENT_SOURCE")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,119}", document_id):
            raise ValueError("DOCUMENT_ID_INVALID")
        with self._lock, self._connect() as db:
            cursor = db.execute(
                """DELETE FROM knowledge_document
                WHERE source = ? AND (
                    document_id = ? OR source_id = ? OR source_id LIKE ?
                )""",
                (source, document_id, document_id, f"{document_id}#%"),
            )
            deleted = cursor.rowcount
            self._sync_fts(db, delete=(source, document_id), rows=[])
        delete_payload = {"source": source, "document_id": document_id}
        vector_deleted = self._external_write("qdrant", "delete_document", delete_payload)
        sync_status = (
            "complete"
            if vector_deleted
            else ("pending" if self.external_sync_status()["pending"] else "local_only")
        )
        return {
            "source": source,
            "document_id": document_id,
            "deleted_chunks": max(deleted, 0),
            "vector_deleted": vector_deleted,
            "sync_status": sync_status,
        }

    @staticmethod
    def _sync_fts(
        db: Any,
        *,
        delete: tuple[str, str] | None,
        rows: list[dict[str, Any]],
    ) -> None:
        """在同一事务内同步 FTS5 索引；FTS 表缺失（迁移前旧库）时跳过。"""
        if not fts_ready(db):
            return
        try:
            if delete:
                delete_fts_document(db, delete[0], delete[1])
            if rows:
                insert_fts_rows(db, rows)
        except Exception:
            logger.exception(
                "FTS5 index sync failed for %s/%s",
                delete[0] if delete else "-",
                delete[1] if delete else "-",
            )

    def bm25_available(self) -> bool:
        """FTS5 稀疏索引是否可用（不可用时 sparse 检索降级 lexical 兜底）。"""
        with self._connect() as db:
            return fts_ready(db)

    def bm25_search(self, query: str, sources: list[str], top_k: int) -> list[dict[str, Any]]:
        """BM25 检索知识分块，回表补齐真实 title/content 后返回。"""
        selected = [item for item in sources if item != "realtime_db"]
        if not selected:
            return []
        with self._connect() as db:
            hits = search_bm25(db, query, selected, top_k)
            if not hits:
                return []
            placeholders = ",".join("?" for _ in hits)
            rows = db.execute(
                f"""SELECT source_id, title, content FROM knowledge_document
                WHERE source_id IN ({placeholders})""",
                [hit["id"] for hit in hits],
            ).fetchall()
        by_id = {row["source_id"]: dict(row) for row in rows}
        results = []
        for hit in hits:
            row = by_id.get(hit["id"])
            if row is None:
                continue
            results.append({**hit, "title": row["title"], "content": row["content"]})
        return results

    def rebuild_vector_index(self, sources: list[str] | None = None) -> dict[str, Any]:
        allowed_sources = {
            "mqtt_docs",
            "wifi_docs",
            "sensor_docs",
            "device_docs",
        }
        selected = list(dict.fromkeys(sources or sorted(allowed_sources)))
        if set(selected) - allowed_sources:
            raise ValueError("INVALID_REQUEST")
        started = time.perf_counter()
        documents = [
            self._knowledge_vector_document(item)
            for item in self.knowledge_documents(selected)
        ]
        items = documents
        indexed = self._qdrant_write_many(items)
        pending = self.external_sync_status()["by_component"].get("qdrant", 0)
        target = self.external.qdrant
        provider = getattr(getattr(target, "embedding_provider", None), "name", "disabled")
        return {
            "sources": selected,
            "attempted": len(items),
            "indexed": indexed,
            "pending": pending,
            "embedding_provider": provider,
            "collection": getattr(target, "collection", None),
            "dimensions": getattr(target, "dimensions", None),
            "duration_ms": round((time.perf_counter() - started) * 1000, 2),
            "sync_status": (
                "complete"
                if indexed == len(items) and target is not None
                else "pending"
                if pending
                else "local_only"
            ),
        }
