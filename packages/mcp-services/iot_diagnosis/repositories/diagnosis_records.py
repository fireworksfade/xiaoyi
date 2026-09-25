import json
import uuid
from typing import Any

from iot_diagnosis.repository_common import iso, utc_now


class DiagnosisRecordMixin:
    def save_diagnosis(self, record: dict[str, Any]) -> None:
        created_at = iso()
        with self._lock, self._connect() as db:
            db.execute(
                """INSERT INTO diagnosis_record
                (diagnosis_id, request_id, device_id, query, fault_type, fault_name, cause,
                 solutions_json, confidence, router_type, selected_sources_json,
                 retrieved_documents_json, result_json, retrieval_count, rerank_count,
                 retrieval_latency_ms, llm_latency_ms, total_latency_ms, input_tokens,
                 output_tokens, error, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    record["diagnosis_id"],
                    record["request_id"],
                    record["device_id"],
                    record["query"],
                    record["fault_type"],
                    record["fault_name"],
                    record["cause"],
                    json.dumps(record["solutions"], ensure_ascii=False),
                    record["confidence"],
                    record["route"]["router"],
                    json.dumps(record["route"]["selected_sources"], ensure_ascii=False),
                    json.dumps(
                        record.get("trace_contexts", record["sources"]),
                        ensure_ascii=False,
                    ),
                    json.dumps(
                        {
                            key: value
                            for key, value in record.items()
                            if key not in {"trace_contexts", "request_id"}
                        },
                        ensure_ascii=False,
                    ),
                    record["observability"]["retrieval_count"],
                    record["observability"]["rerank_count"],
                    record["observability"]["retrieval_latency_ms"],
                    record["observability"]["llm_latency_ms"],
                    record["observability"]["total_latency_ms"],
                    record["observability"]["input_tokens"],
                    record["observability"]["output_tokens"],
                    record["observability"]["error"],
                    created_at,
                ),
            )
        # MySQL 镜像已移除 - 诊断记录仅存储在 SQLite

    def save_diagnosis_error(
        self,
        device_id: str,
        query: str,
        code: str,
        message: str,
    ) -> dict[str, str]:
        diagnosis_id = f"DIA_{utc_now():%Y%m%d}_{uuid.uuid4().hex[:8].upper()}"
        request_id = str(uuid.uuid4())
        record = {
            "diagnosis_id": diagnosis_id,
            "request_id": request_id,
            "device_id": device_id,
            "query": query,
            "fault_type": "unknown",
            "fault_name": "Diagnosis failed",
            "cause": message,
            "solutions": [],
            "confidence": 0.0,
            "route": {"router": "failed", "selected_sources": []},
            "sources": [],
            "trace_contexts": [],
            "observability": {
                "retrieval_count": 0,
                "rerank_count": 0,
                "retrieval_latency_ms": 0.0,
                "llm_latency_ms": 0.0,
                "total_latency_ms": 0.0,
                "input_tokens": 0,
                "output_tokens": 0,
                "error": code,
            },
        }
        self.save_diagnosis(record)
        return {"diagnosis_id": diagnosis_id, "request_id": request_id}

    def get_diagnosis_trace(self, diagnosis_id: str) -> dict[str, Any] | None:
        with self._connect() as db:
            row = db.execute(
                "SELECT * FROM diagnosis_record WHERE diagnosis_id = ?",
                (diagnosis_id,),
            ).fetchone()
        if not row:
            return None
        item = self._diagnosis_record_from_row(dict(row))
        item["contexts"] = item.pop("trace_contexts")
        item.pop("sources")
        return item

    def list_diagnoses(
        self,
        device_id: str | None = None,
        fault_type: str | None = None,
        status: str = "all",
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        query = "SELECT * FROM diagnosis_record"
        clauses: list[str] = []
        params: list[Any] = []
        if device_id:
            clauses.append("device_id = ?")
            params.append(device_id)
        if fault_type:
            clauses.append("fault_type = ?")
            params.append(fault_type)
        if status == "succeeded":
            clauses.append("error IS NULL")
        elif status == "failed":
            clauses.append("error IS NOT NULL")
        if clauses:
            query += " WHERE " + " AND ".join(clauses)

        count_query = f"SELECT COUNT(*) FROM ({query})"
        query += " ORDER BY created_at DESC, diagnosis_id DESC LIMIT ? OFFSET ?"
        with self._connect() as db:
            total = int(db.execute(count_query, params).fetchone()[0])
            rows = db.execute(query, [*params, limit, offset]).fetchall()

        return {
            "items": [
                {
                    "diagnosis_id": row["diagnosis_id"],
                    "device_id": row["device_id"],
                    "query": row["query"],
                    "fault_type": row["fault_type"],
                    "fault_name": row["fault_name"],
                    "confidence": row["confidence"],
                    "router": row["router_type"],
                    "selected_sources": json.loads(row["selected_sources_json"]),
                    "status": "failed" if row["error"] else "succeeded",
                    "error": row["error"],
                    "total_latency_ms": row["total_latency_ms"],
                    "created_at": row["created_at"],
                }
                for row in rows
            ],
            "total": total,
            "limit": limit,
            "offset": offset,
        }
