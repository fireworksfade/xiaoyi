"""设备状态生命周期拆分（specs WP-06 / §6.1）。

- 新增 device_current_state（每设备一行，upsert 最新可查询状态）与
  device_telemetry（历史测量，唯一键 device_id + device_timestamp + payload_hash）。
- device 增加 updated_at 记录最后一次元数据变化。
- 旧 device_status 重命名为 device_status_legacy（观察期后由显式命令清理），
  并为每台设备按 timestamp DESC, id DESC 构建最新快照。
- 旧 timestamp 解析失败时保留原值，received_at 使用迁移时间（异常计数记录在
  runtime_state_notes）。
"""

import sqlite3

version = 2
name = "state_lifecycle"

_TABLES = """
CREATE TABLE IF NOT EXISTS device_current_state (
    device_id TEXT PRIMARY KEY REFERENCES device(device_id),
    online INTEGER NOT NULL,
    wifi_status TEXT,
    rssi INTEGER,
    mqtt_status TEXT,
    temperature REAL,
    uptime INTEGER,
    device_timestamp TEXT,
    received_at TEXT NOT NULL,
    last_event_kind TEXT NOT NULL,
    payload_hash TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS device_telemetry (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id TEXT NOT NULL REFERENCES device(device_id),
    temperature REAL,
    rssi INTEGER,
    uptime INTEGER,
    wifi_status TEXT,
    mqtt_status TEXT,
    device_timestamp TEXT,
    received_at TEXT NOT NULL,
    payload_hash TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_device_telemetry_sample
    ON device_telemetry(device_id, device_timestamp, payload_hash);
CREATE INDEX IF NOT EXISTS ix_device_telemetry_device
    ON device_telemetry(device_id, received_at DESC);
"""

_FIELDS = ("online", "wifi_status", "rssi", "mqtt_status", "temperature", "uptime")


def _parse_timestamp(raw: object, migration_time: str) -> tuple[str, str]:
    """返回 (device_timestamp 原值, received_at)。解析失败用迁移时间。"""
    text = str(raw or "")
    if text:
        try:
            from datetime import datetime, timezone

            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return text, parsed.astimezone(timezone.utc).isoformat()
        except ValueError:
            return text, migration_time
    return text, migration_time


def upgrade(db) -> None:  # noqa: ANN001 - sqlite3.Connection
    from datetime import datetime, timezone

    migration_time = datetime.now(timezone.utc).isoformat()
    existing_columns = {row[1] for row in db.execute("PRAGMA table_info(device)").fetchall()}
    if "updated_at" not in existing_columns:
        db.execute("ALTER TABLE device ADD COLUMN updated_at TEXT")
    db.executescript(_TABLES)

    tables = {
        row[0]
        for row in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='device_status'"
        ).fetchall()
    }
    if tables:
        # 每设备取最新一行构建 current state（timestamp DESC, id DESC）
        rows = db.execute(
            "SELECT device_id, online, wifi_status, rssi, mqtt_status, temperature, uptime, "
            "timestamp FROM device_status ORDER BY device_id, timestamp DESC, id DESC"
        ).fetchall()
        latest: dict[str, sqlite3.Row] = {}
        parse_failures = 0
        for row in rows:
            if row["device_id"] not in latest:
                latest[row["device_id"]] = row
        for device_id, row in latest.items():
            device_timestamp, received_at = _parse_timestamp(row["timestamp"], migration_time)
            if received_at == migration_time and device_timestamp:
                parse_failures += 1
            payload_hash = f"legacy-{device_timestamp or migration_time}"
            db.execute(
                """INSERT OR IGNORE INTO device_current_state
                (device_id, online, wifi_status, rssi, mqtt_status, temperature, uptime,
                 device_timestamp, received_at, last_event_kind, payload_hash)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'legacy', ?)""",
                (
                    device_id,
                    int(row["online"]),
                    row["wifi_status"],
                    row["rssi"],
                    row["mqtt_status"],
                    row["temperature"],
                    row["uptime"],
                    device_timestamp or None,
                    received_at,
                    payload_hash,
                ),
            )
        db.execute("ALTER TABLE device_status RENAME TO device_status_legacy")
    db.commit()
