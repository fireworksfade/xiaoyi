import hashlib
import json
import logging
import os
import uuid
from datetime import timedelta
from typing import Any

from iot_diagnosis.repository_common import iso, utc_now

logger = logging.getLogger("xiaoyi.iot_diagnosis.repository")


class ExternalSyncMixin:
    def _external_call(self, component: str, method: str, *args) -> bool:
        self.external.ensure_connected(component)
        target = getattr(self.external, component, None)
        if not target:
            return False
        try:
            result = getattr(target, method)(*args)
            self.external.errors.pop(component, None)
            return result is not False
        except Exception as exc:
            self.external.errors[component] = type(exc).__name__
            logger.exception("External %s operation %s failed", component, method)
            return False

    def _dispatch_external(self, component: str, operation: str, payload: dict[str, Any]) -> bool:
        if operation == "upsert_device_status":
            return self._external_call(
                component,
                operation,
                payload["device"],
                payload["status"],
            )
        return self._external_call(component, operation, payload)

    def _enqueue_external_sync(
        self,
        component: str,
        operation: str,
        payload: dict[str, Any],
    ) -> None:
        payload_json = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        dedupe_key = hashlib.sha256(
            f"{component}:{operation}:{payload_json}".encode("utf-8")
        ).hexdigest()
        now = iso()
        with self._lock, self._connect() as db:
            db.execute(
                """INSERT INTO external_sync_outbox
                (id, dedupe_key, component, operation, payload_json, attempts,
                 last_error, created_at, updated_at, completed_at)
                VALUES (?, ?, ?, ?, ?, 0, ?, ?, ?, NULL)
                ON CONFLICT(dedupe_key) DO UPDATE SET
                    payload_json=excluded.payload_json,
                    last_error=excluded.last_error,
                    updated_at=excluded.updated_at,
                    completed_at=NULL,
                    claimed_at=NULL""",
                (
                    str(uuid.uuid4()),
                    dedupe_key,
                    component,
                    operation,
                    payload_json,
                    self.external.errors.get(component, "UNAVAILABLE"),
                    now,
                    now,
                ),
            )

    def _external_write(
        self,
        component: str,
        operation: str,
        payload: dict[str, Any],
    ) -> bool:
        if not self.external.is_configured(component):
            return False
        delivered = self._dispatch_external(component, operation, payload)
        if not delivered:
            self._enqueue_external_sync(component, operation, payload)
        return delivered

    def retry_external_sync(self, limit: int = 100, lease_seconds: int = 300) -> dict[str, int]:
        # 单条 UPDATE 原子认领（带租约）：多个进程/线程同时重试时不会重复
        # 派发同一批待同步记录；崩溃进程的租约过期后可被其他进程接管。
        now = iso()
        lease_deadline = iso(utc_now() - timedelta(seconds=lease_seconds))
        with self._lock, self._connect() as db:
            rows = db.execute(
                """UPDATE external_sync_outbox
                SET claimed_at=?, attempts=attempts+1, updated_at=?
                WHERE id IN (
                    SELECT id FROM external_sync_outbox
                    WHERE completed_at IS NULL
                      AND (claimed_at IS NULL OR claimed_at < ?)
                    ORDER BY created_at, id
                    LIMIT ?
                )
                RETURNING id, component, operation, payload_json""",
                (now, now, lease_deadline, max(1, min(limit, 1000))),
            ).fetchall()

        delivered = 0
        failed = 0
        for row in rows:
            payload = json.loads(row["payload_json"])
            success = self._dispatch_external(row["component"], row["operation"], payload)
            finished = iso()
            with self._lock, self._connect() as db:
                if success:
                    delivered += 1
                    db.execute(
                        """UPDATE external_sync_outbox
                        SET last_error=NULL, updated_at=?, completed_at=?, claimed_at=NULL
                        WHERE id=?""",
                        (finished, finished, row["id"]),
                    )
                else:
                    failed += 1
                    db.execute(
                        """UPDATE external_sync_outbox
                        SET last_error=?, updated_at=?, claimed_at=NULL
                        WHERE id=?""",
                        (
                            self.external.errors.get(row["component"], "UNAVAILABLE"),
                            finished,
                            row["id"],
                        ),
                    )
        return {"processed": len(rows), "delivered": delivered, "failed": failed}

    def external_sync_status(self) -> dict[str, Any]:
        with self._connect() as db:
            pending = db.execute(
                """SELECT component, COUNT(*) AS count, MAX(attempts) AS max_attempts
                FROM external_sync_outbox
                WHERE completed_at IS NULL
                GROUP BY component"""
            ).fetchall()
            oldest_pending = db.execute(
                "SELECT MIN(created_at) FROM external_sync_outbox WHERE completed_at IS NULL"
            ).fetchone()[0]
            last_delivery = db.execute(
                "SELECT MAX(completed_at) FROM external_sync_outbox WHERE completed_at IS NOT NULL"
            ).fetchone()[0]
        by_component = {row["component"]: row["count"] for row in pending}
        return {
            "pending": sum(by_component.values()),
            "by_component": by_component,
            "max_attempts": max((row["max_attempts"] for row in pending), default=0),
            "oldest_pending_at": oldest_pending,
            "last_delivery_at": last_delivery,
        }

    @staticmethod
    def _case_document(item: dict[str, Any]) -> dict[str, Any]:
        content = "；".join(
            [
                item["fault_name"],
                *item["symptoms"],
                *item["logs"],
                item["cause"],
                item["solution"],
            ]
        )
        return {
            "source": "fault_cases",
            "id": item["fault_id"],
            # Qdrant 删除按 payload 的 document_id 过滤，案例删除链路依赖该字段
            "document_id": item["fault_id"],
            "title": item["fault_name"],
            "content": content,
            "device_type": item["device_type"],
        }

    @staticmethod
    def _knowledge_vector_document(item: dict[str, Any]) -> dict[str, Any]:
        metadata: dict[str, Any] = {}
        raw = item.get("metadata_json")
        if raw:
            try:
                metadata = json.loads(raw)
            except (TypeError, ValueError):
                metadata = {}
        return {
            "source": item["source"],
            "id": item["source_id"],
            "document_id": item.get("document_id") or item["source_id"].split("#", 1)[0],
            "chunk_index": int(item.get("chunk_index") or 0),
            "title": item["title"],
            "heading_path": metadata.get("heading_path") or [],
            "block_type": metadata.get("block_type"),
            "token_count": int(metadata.get("token_count") or item.get("token_count") or 0),
            "content": item["content"],
            "device_type": item.get("device_type"),
        }

    def _qdrant_write_many(self, items: list[dict[str, Any]]) -> int:
        if not items or not self.external.is_configured("qdrant"):
            return 0
        batch_size = max(1, min(int(os.getenv("DIAGNOSIS_VECTOR_BATCH_SIZE", "32")), 100))
        indexed = 0
        for offset in range(0, len(items), batch_size):
            batch = items[offset : offset + batch_size]
            if self._external_call("qdrant", "upsert_many", batch):
                indexed += len(batch)
                continue
            for item in batch:
                self._enqueue_external_sync("qdrant", "upsert", item)
        return indexed

    @staticmethod
    def _diagnosis_record_from_row(item: dict[str, Any]) -> dict[str, Any]:
        contexts = json.loads(item["retrieved_documents_json"])
        record = {
            "diagnosis_id": item["diagnosis_id"],
            "request_id": item["request_id"],
            "device_id": item["device_id"],
            "query": item["query"],
            "fault_type": item["fault_type"],
            "fault_name": item["fault_name"],
            "cause": item["cause"],
            "solutions": json.loads(item["solutions_json"]),
            "confidence": item["confidence"],
            "route": {
                "router": item["router_type"],
                "selected_sources": json.loads(item["selected_sources_json"]),
            },
            "sources": contexts,
            "trace_contexts": contexts,
            "observability": {
                "retrieval_count": item["retrieval_count"],
                "rerank_count": item["rerank_count"],
                "retrieval_latency_ms": item["retrieval_latency_ms"],
                "llm_latency_ms": item["llm_latency_ms"],
                "total_latency_ms": item["total_latency_ms"],
                "input_tokens": item["input_tokens"],
                "output_tokens": item["output_tokens"],
                "error": item["error"],
            },
            "created_at": item["created_at"],
        }
        result_json = item.get("result_json")
        if result_json:
            record["result"] = json.loads(result_json)
        else:
            record["result"] = {
                key: record[key]
                for key in (
                    "diagnosis_id",
                    "device_id",
                    "fault_type",
                    "fault_name",
                    "cause",
                    "solutions",
                    "confidence",
                    "route",
                    "sources",
                    "observability",
                )
            }
        return record

    def vector_search(
        self,
        query: str,
        sources: list[str],
        top_k: int,
        query_vector: list[float] | None = None,
    ) -> list[dict[str, Any]]:
        target = self.external.qdrant
        if not target:
            return []
        try:
            if query_vector is None:
                return target.search(query, sources, top_k)
            return target.search(query, sources, top_k, query_vector=query_vector)
        except Exception as exc:
            self.external.errors["qdrant"] = type(exc).__name__
            logger.exception("Qdrant search failed")
            return []

    def storage_status(self) -> dict[str, Any]:
        return {**self.external.status(), "outbox": self.external_sync_status()}
