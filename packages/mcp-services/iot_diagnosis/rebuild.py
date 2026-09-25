"""外部存储显式重建服务（specs WP-08 / §7.2）。

启动路径不再执行全量外部同步；计数不一致时用本服务显式重建：
- 分页读取（每页最多 batch_size），进程内存不随总行数线性增长。
- 稳定游标（status/log 递增 id，document/case/diagnosis 稳定主键），
  进度写入 rebuild_job 表，中断后可从游标继续。
- Qdrant 重建复用 repository.rebuild_vector_index（以 SQLite 为事实源）。
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timezone
from typing import Any, Callable

logger = logging.getLogger("xiaoyi.iot_diagnosis.rebuild")

ENTITIES = ("device_status", "device_log", "knowledge_document", "fault_case", "diagnosis_record")


def iso(value=None):
    return (value or datetime.now(timezone.utc)).isoformat()


class RebuildService:
    def __init__(self, repository, *, batch_size: int = 500):  # noqa: ANN001 - DiagnosisRepository
        self.repository = repository
        self.batch_size = max(1, batch_size)
        # rebuild_job 由迁移 0003 创建；此处只验证
        from common.migrations import MigrationError

        try:
            repository.migration_runner().verify(repository.path)
        except MigrationError:
            repository.migration_runner().initialize(repository.path)

    def _connect(self) -> sqlite3.Connection:
        return self.repository._connect()

    # ------------------------------------------------------------------ jobs

    def job_status(self) -> dict[str, Any]:
        with self._connect() as db:
            rows = [dict(row) for row in db.execute("SELECT * FROM rebuild_job").fetchall()]
        return {row["entity"]: row for row in rows}

    def _update_job(self, db: sqlite3.Connection, entity: str, **fields: Any) -> None:
        assignments = ", ".join(f"{key} = ?" for key in fields)
        db.execute(
            f"UPDATE rebuild_job SET {assignments}, updated_at = ? WHERE entity = ?",
            [*fields.values(), iso(), entity],
        )

    # -------------------------------------------------------------- dispatch

    def _build_status_payload(self, row: dict[str, Any]) -> dict[str, Any]:
        device = self.repository.get_device_status(row["device_id"]) or {}
        device_row = {
            "device_id": row["device_id"],
            "device_type": device.get("device_type", "ESP32"),
            "name": device.get("name", row["device_id"]),
            "firmware_version": device.get("firmware_version"),
            "created_at": row["received_at"],
        }
        status = {
            "device_id": row["device_id"],
            "online": row["online"],
            "wifi_status": row["wifi_status"] or "unknown",
            "rssi": row["rssi"],
            "mqtt_status": row["mqtt_status"] or "unknown",
            "temperature": row["temperature"],
            "uptime": row["uptime"],
            "timestamp": row["device_timestamp"] or row["received_at"],
        }
        return {"device": device_row, "status": status}

    @staticmethod
    def _case_from_row(row: dict[str, Any]) -> dict[str, Any]:
        item = dict(row)
        item["symptoms"] = json.loads(item.pop("symptoms_json"))
        item["logs"] = json.loads(item.pop("logs_json"))
        item["verified"] = bool(item["verified"])
        return item

    def _batch_query(
        self, entity: str, cursor: str | None
    ) -> tuple[list[dict[str, Any]], Callable[[dict], str]]:
        """按实体分页读取，返回 (行列表, 行 → 游标函数)。"""
        repo = self.repository
        batch = self.batch_size
        with repo._connect() as db:
            if entity == "device_status":
                rows = [
                    dict(row)
                    for row in db.execute(
                        "SELECT * FROM device_current_state WHERE device_id > ? "
                        "ORDER BY device_id LIMIT ?",
                        (cursor or "", batch),
                    ).fetchall()
                ]
                return rows, lambda row: row["device_id"]
            if entity == "device_log":
                rows = [
                    dict(row)
                    for row in db.execute(
                        "SELECT * FROM device_log WHERE id > ? ORDER BY id LIMIT ?",
                        (int(cursor or 0), batch),
                    ).fetchall()
                ]
                return rows, lambda row: str(row["id"])
            if entity == "knowledge_document":
                rows = [
                    dict(row)
                    for row in db.execute(
                        "SELECT * FROM knowledge_document WHERE (source, source_id) > (?, ?) "
                        "ORDER BY source, source_id LIMIT ?",
                        (*_split_cursor(cursor), batch),
                    ).fetchall()
                ]
                return rows, lambda row: _join_cursor(row["source"], row["source_id"])
            if entity == "fault_case":
                rows = [
                    dict(row)
                    for row in db.execute(
                        "SELECT * FROM fault_case WHERE fault_id > ? ORDER BY fault_id LIMIT ?",
                        (cursor or "", batch),
                    ).fetchall()
                ]
                return rows, lambda row: row["fault_id"]
            if entity == "diagnosis_record":
                rows = [
                    dict(row)
                    for row in db.execute(
                        "SELECT * FROM diagnosis_record WHERE diagnosis_id > ? "
                        "ORDER BY diagnosis_id LIMIT ?",
                        (cursor or "", batch),
                    ).fetchall()
                ]
                return rows, lambda row: row["diagnosis_id"]
        raise ValueError(f"UNKNOWN_REBUILD_ENTITY: {entity}")

    def _dispatch(self, entity: str, row: dict[str, Any]) -> bool:
        # MySQL 镜像已移除 - 此方法不再使用
        raise ValueError(f"UNKNOWN_REBUILD_ENTITY: {entity}")


def _join_cursor(source: str, source_id: str) -> str:
    return f"{source}|{source_id}"


def _split_cursor(cursor: str | None) -> tuple[str, str]:
    if not cursor:
        return ("", "")
    source, _, source_id = cursor.partition("|")
    return (source, source_id)
