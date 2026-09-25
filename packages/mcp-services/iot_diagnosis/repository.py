from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from common.migrations import SQLiteMigrationRunner, load_migrations_from_dir
from iot_diagnosis.external import ExternalStores
from iot_diagnosis.repositories import (
    DeviceStateMixin,
    DiagnosisRecordMixin,
    ExternalSyncMixin,
    KnowledgeCaseMixin,
    LogRepositoryMixin,
)
from iot_diagnosis.repository_common import iso
from iot_diagnosis.retrieval.bm25 import fts_ready, insert_fts_rows


class DiagnosisRepository(
    DeviceStateMixin,
    LogRepositoryMixin,
    KnowledgeCaseMixin,
    DiagnosisRecordMixin,
    ExternalSyncMixin,
):
    def __init__(self, path: str, offline_after_seconds: int = 120, *, auto_migrate: bool = True):
        self.path = path
        self.offline_after_seconds = max(1, offline_after_seconds)
        self._lock = threading.RLock()
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._initialize(auto_migrate=auto_migrate)
        # 启动只做本地初始化；外部同步交给 outbox 增量重试与显式 rebuild（WP-08）
        self.external = ExternalStores()

    @staticmethod
    def migration_runner() -> SQLiteMigrationRunner:
        return SQLiteMigrationRunner(
            load_migrations_from_dir(Path(__file__).resolve().parent / "migrations"),
            service="iot_diagnosis",
        )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _initialize(self, *, auto_migrate: bool = True) -> None:
        """Repository 构造只做初始化/验证：空库执行迁移，已有库验证版本。"""
        runner = self.migration_runner()
        if auto_migrate:
            runner.initialize(self.path)
        else:
            runner.verify(self.path)
        with self._connect() as db:
            db.execute("PRAGMA optimize")
            self._seed(db)

    def _seed(self, db: sqlite3.Connection) -> None:
        now = iso()
        db.execute(
            """INSERT OR IGNORE INTO device
            (device_id, device_type, name, firmware_version, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)""",
            ("ESP32_05", "ESP32", "实验室节点 05", "1.2.0", now, now),
        )
        if not db.execute("SELECT 1 FROM device_current_state LIMIT 1").fetchone():
            db.execute(
                """INSERT INTO device_current_state
                (device_id, online, wifi_status, rssi, mqtt_status, temperature, uptime,
                 device_timestamp, received_at, last_event_kind, payload_hash)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'status', ?)""",
                ("ESP32_05", 1, "connected", -47, "disconnected", 26.3, 86400, now, now, "seed"),
            )
            db.execute(
                "INSERT INTO device_log(device_id, level, module, message, timestamp) VALUES (?, ?, ?, ?, ?)",
                ("ESP32_05", "ERROR", "mqtt", "MQTT keep alive timeout", now),
            )
        documents = (
            (
                "mqtt_docs",
                "MQTT_DOC_03",
                "MQTT Keep Alive 与连接超时",
                "客户端必须在 Keep Alive 窗口内发送控制报文。频繁出现 keep alive timeout 时，应检查客户端心跳、Broker 超时和网络延迟。",
            ),
            (
                "wifi_docs",
                "WIFI_DOC_02",
                "ESP32 WiFi 弱信号诊断",
                "RSSI 低于 -75 dBm 时连接稳定性会明显下降。检查天线、供电、信道拥塞与接入点距离。",
            ),
            (
                "sensor_docs",
                "SENSOR_DOC_01",
                "传感器异常值排查",
                "传感器读数异常时先检查接线、供电、采样周期和量程，并与已知参考值交叉验证。",
            ),
            (
                "device_docs",
                "ESP32_DOC_01",
                "ESP32 运行状态检查",
                "设备重启、内存不足或长时间运行异常时，应核对 uptime、复位原因、空闲堆和固件版本。",
            ),
        )
        for source, source_id, title, content in documents:
            cursor = db.execute(
                """INSERT OR IGNORE INTO knowledge_document
                (source, source_id, title, content, device_type, created_at, document_id, chunk_index)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (source, source_id, title, content, "ESP32", now, source_id, 0),
            )
            if cursor.rowcount and fts_ready(db):
                insert_fts_rows(
                    db,
                    [
                        {
                            "chunk_id": source_id,
                            "document_id": source_id,
                            "source": source,
                            "title": title,
                            "heading": "",
                            "content": content,
                        }
                    ],
                )

    # ---------------------------------------------------------------- 设备状态

    @staticmethod
    def _payload_hash(payload: dict[str, Any]) -> str:
        canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @staticmethod
    def _parse_datetime(value: object) -> datetime | None:
        text = str(value or "")
        if not text:
            return None
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
