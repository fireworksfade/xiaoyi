from datetime import timedelta
from typing import Any

from iot_diagnosis.repository_common import iso, utc_now


class DeviceStateMixin:
    def get_device_status(self, device_id: str) -> dict[str, Any] | None:
        """最新状态：device + device_current_state，新鲜度按 received_at 判定。"""
        with self._connect() as db:
            device = db.execute("SELECT * FROM device WHERE device_id = ?", (device_id,)).fetchone()
            if not device:
                return None
            state = db.execute(
                "SELECT * FROM device_current_state WHERE device_id = ?",
                (device_id,),
            ).fetchone()
        if not state:
            return None
        received_at = self._parse_datetime(state["received_at"]) or utc_now()
        heartbeat_fresh = utc_now() - received_at <= timedelta(seconds=self.offline_after_seconds)
        reported_online = bool(state["online"])
        return {
            "device_id": device_id,
            "device_type": device["device_type"],
            "name": device["name"],
            "firmware_version": device["firmware_version"],
            "online": reported_online and heartbeat_fresh,
            "reported_online": reported_online,
            "heartbeat_fresh": heartbeat_fresh,
            "wifi_status": state["wifi_status"],
            "rssi": state["rssi"],
            "mqtt_status": state["mqtt_status"],
            "temperature": state["temperature"],
            "uptime": state["uptime"],
            "last_seen": state["device_timestamp"] or state["received_at"],
            "last_event_kind": state["last_event_kind"],
        }

    def list_devices(
        self,
        device_type: str | None = None,
        online: bool | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> dict[str, Any]:
        """集合查询（LEFT JOIN current state），避免逐设备 N+1 查询。"""
        where = ["1 = 1"]
        params: list[Any] = []
        if device_type:
            where.append("d.device_type = ?")
            params.append(device_type)
        query = (
            "SELECT d.device_id, d.device_type, d.name, d.firmware_version, "
            "cs.online, cs.wifi_status, cs.rssi, cs.mqtt_status, cs.temperature, "
            "cs.uptime, cs.device_timestamp, cs.received_at "
            "FROM device d LEFT JOIN device_current_state cs ON cs.device_id = d.device_id "
            f"WHERE {' AND '.join(where)} ORDER BY d.device_id"
        )
        with self._connect() as db:
            rows = [dict(row) for row in db.execute(query, params).fetchall()]

        items = []
        for row in rows:
            received_at = self._parse_datetime(row.get("received_at"))
            fresh = bool(
                received_at
                and utc_now() - received_at <= timedelta(seconds=self.offline_after_seconds)
            )
            reported_online = bool(row.get("online"))
            effective = reported_online and fresh
            if online is not None and effective is not online:
                continue
            items.append(
                {
                    "device_id": row["device_id"],
                    "device_type": row["device_type"],
                    "name": row["name"],
                    "firmware_version": row["firmware_version"],
                    "online": effective,
                    "reported_online": reported_online if received_at else None,
                    "heartbeat_fresh": fresh,
                    "wifi_status": row.get("wifi_status"),
                    "rssi": row.get("rssi"),
                    "mqtt_status": row.get("mqtt_status"),
                    "temperature": row.get("temperature"),
                    "uptime": row.get("uptime"),
                    "last_seen": row.get("device_timestamp") or row.get("received_at"),
                }
            )
        total = len(items)
        return {
            "items": items[offset : offset + limit],
            "total": total,
            "limit": limit,
            "offset": offset,
        }

    def get_device_logs(
        self, device_id: str, limit: int = 50, level: str | None = None
    ) -> list[dict[str, Any]] | None:
        with self._connect() as db:
            known = db.execute("SELECT 1 FROM device WHERE device_id = ?", (device_id,)).fetchone()
        if not known:
            return None
        query = "SELECT timestamp, level, module, message FROM device_log WHERE device_id = ?"
        params: list[Any] = [device_id]
        if level:
            query += " AND level = ?"
            params.append(level.upper())
        query += " ORDER BY timestamp DESC, id DESC LIMIT ?"
        params.append(limit)
        with self._connect() as db:
            return [dict(row) for row in db.execute(query, params).fetchall()]

    def upsert_device_metadata(
        self, device_id: str, payload: dict[str, Any], received_at: str | None = None
    ) -> None:
        """非空字段才覆盖；'unknown' 不覆盖已有非 unknown 值；变化时更新 updated_at。"""
        now = received_at or iso()
        with self._lock, self._connect() as db:
            row = db.execute(
                "SELECT device_type, name, firmware_version FROM device WHERE device_id = ?",
                (device_id,),
            ).fetchone()
            if not row:
                db.execute(
                    "INSERT INTO device VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        device_id,
                        str(payload.get("device_type") or "ESP32"),
                        str(payload.get("name") or device_id),
                        str(payload.get("firmware_version") or "unknown"),
                        now,
                        now,
                    ),
                )
                return
            current = {
                "device_type": row["device_type"],
                "name": row["name"],
                "firmware_version": row["firmware_version"],
            }
            changed = False
            for field in ("device_type", "name", "firmware_version"):
                incoming = payload.get(field)
                if incoming is None or str(incoming) == "":
                    continue
                incoming = str(incoming)
                existing = current[field]
                if incoming == existing:
                    continue
                if existing == "unknown" or existing is None:
                    current[field] = incoming
                    changed = True
                elif incoming != "unknown":
                    current[field] = incoming
                    changed = True
            if changed:
                db.execute(
                    "UPDATE device SET device_type = ?, name = ?, firmware_version = ?, "
                    "updated_at = ? WHERE device_id = ?",
                    (
                        current["device_type"],
                        current["name"],
                        current["firmware_version"],
                        now,
                        device_id,
                    ),
                )

    def apply_status(
        self, device_id: str, payload: dict[str, Any], received_at: str | None = None
    ) -> None:
        """/status：更新 current state 与元数据；不写历史序列。"""
        received_at = received_at or iso()
        payload_hash = self._payload_hash(payload)
        online = int(bool(payload.get("online", True)))
        wifi_status = payload.get("wifi_status", payload.get("wifi"))
        mqtt_status = payload.get("mqtt_status", payload.get("mqtt"))
        rssi = payload.get("rssi")
        temperature = payload.get("temperature")
        uptime = payload.get("uptime")
        device_timestamp = str(payload.get("timestamp") or "") or None

        self.upsert_device_metadata(device_id, payload, received_at)
        with self._lock, self._connect() as db:
            db.execute(
                """INSERT INTO device_current_state
                (device_id, online, wifi_status, rssi, mqtt_status, temperature, uptime,
                 device_timestamp, received_at, last_event_kind, payload_hash)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'status', ?)
                ON CONFLICT(device_id) DO UPDATE SET
                online = excluded.online,
                wifi_status = COALESCE(excluded.wifi_status, device_current_state.wifi_status),
                rssi = COALESCE(excluded.rssi, device_current_state.rssi),
                mqtt_status = COALESCE(excluded.mqtt_status, device_current_state.mqtt_status),
                temperature = COALESCE(excluded.temperature, device_current_state.temperature),
                uptime = COALESCE(excluded.uptime, device_current_state.uptime),
                device_timestamp = COALESCE(excluded.device_timestamp, device_current_state.device_timestamp),
                received_at = excluded.received_at,
                last_event_kind = 'status',
                payload_hash = excluded.payload_hash""",
                (
                    device_id,
                    online,
                    wifi_status,
                    rssi,
                    mqtt_status,
                    temperature,
                    uptime,
                    device_timestamp,
                    received_at,
                    payload_hash,
                ),
            )
        device = {
            "device_id": device_id,
            "device_type": str(payload.get("device_type") or "ESP32"),
            "name": str(payload.get("name") or device_id),
            "firmware_version": str(payload.get("firmware_version") or "unknown"),
            "created_at": received_at,
        }
        status = {
            "device_id": device_id,
            "online": online,
            "wifi_status": wifi_status or "unknown",
            "rssi": rssi,
            "mqtt_status": mqtt_status or "unknown",
            "temperature": temperature,
            "uptime": uptime,
            "timestamp": device_timestamp or received_at,
        }
        # MySQL 镜像已移除 - 设备状态仅存储在 SQLite

    def append_telemetry(
        self, device_id: str, payload: dict[str, Any], received_at: str | None = None
    ) -> None:
        """/telemetry：追加历史测量（去重），并合并 current state。"""
        received_at = received_at or iso()
        self.upsert_device_metadata(device_id, payload, received_at)
        device_timestamp = str(payload.get("timestamp") or "") or None
        measurement = {
            "temperature": payload.get("temperature"),
            "rssi": payload.get("rssi"),
            "uptime": payload.get("uptime"),
            "wifi_status": payload.get("wifi_status", payload.get("wifi")),
            "mqtt_status": payload.get("mqtt_status", payload.get("mqtt")),
        }
        payload_hash = self._payload_hash(measurement)
        with self._lock, self._connect() as db:
            db.execute(
                """INSERT OR IGNORE INTO device_telemetry
                (device_id, temperature, rssi, uptime, wifi_status, mqtt_status,
                 device_timestamp, received_at, payload_hash)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    device_id,
                    measurement["temperature"],
                    measurement["rssi"],
                    measurement["uptime"],
                    measurement["wifi_status"],
                    measurement["mqtt_status"],
                    device_timestamp,
                    received_at,
                    payload_hash,
                ),
            )
            db.execute(
                """INSERT INTO device_current_state
                (device_id, online, wifi_status, rssi, mqtt_status, temperature, uptime,
                 device_timestamp, received_at, last_event_kind, payload_hash)
                VALUES (?, 1, ?, ?, ?, ?, ?, ?, ?, 'telemetry', ?)
                ON CONFLICT(device_id) DO UPDATE SET
                wifi_status = COALESCE(excluded.wifi_status, device_current_state.wifi_status),
                rssi = COALESCE(excluded.rssi, device_current_state.rssi),
                mqtt_status = COALESCE(excluded.mqtt_status, device_current_state.mqtt_status),
                temperature = COALESCE(excluded.temperature, device_current_state.temperature),
                uptime = COALESCE(excluded.uptime, device_current_state.uptime),
                device_timestamp = COALESCE(excluded.device_timestamp, device_current_state.device_timestamp),
                received_at = MAX(device_current_state.received_at, excluded.received_at),
                last_event_kind = 'telemetry',
                payload_hash = excluded.payload_hash""",
                (
                    device_id,
                    measurement["wifi_status"],
                    measurement["rssi"],
                    measurement["mqtt_status"],
                    measurement["temperature"],
                    measurement["uptime"],
                    device_timestamp,
                    received_at,
                    payload_hash,
                ),
            )

    def touch_heartbeat(
        self, device_id: str, payload: dict[str, Any], received_at: str | None = None
    ) -> None:
        """/heartbeat：只更新 last seen / online / uptime，不复制整行历史状态。"""
        received_at = received_at or iso()
        device_timestamp = str(payload.get("timestamp") or "") or None
        uptime = payload.get("uptime")
        self.upsert_device_metadata(device_id, {}, received_at)
        with self._lock, self._connect() as db:
            db.execute(
                """INSERT INTO device_current_state
                (device_id, online, wifi_status, rssi, mqtt_status, temperature, uptime,
                 device_timestamp, received_at, last_event_kind, payload_hash)
                VALUES (?, 1, NULL, NULL, NULL, NULL, ?, ?, ?, 'heartbeat', ?)
                ON CONFLICT(device_id) DO UPDATE SET
                online = 1,
                uptime = COALESCE(excluded.uptime, device_current_state.uptime),
                device_timestamp = COALESCE(excluded.device_timestamp, device_current_state.device_timestamp),
                received_at = excluded.received_at,
                last_event_kind = 'heartbeat',
                payload_hash = excluded.payload_hash""",
                (
                    device_id,
                    uptime,
                    device_timestamp,
                    received_at,
                    f"heartbeat-{device_timestamp or received_at}",
                ),
            )

    def upsert_status(self, device_id: str, payload: dict[str, Any]) -> None:
        """兼容旧调用（测试/脚本）：等价于 apply_status，不采样遥测。

        未显式传入 received_at 时以载荷 timestamp 兜底，保持旧的"过期心跳判离线"
        语义；MQTT 路径始终传服务端 received_at。
        """
        self.apply_status(device_id, payload, payload.get("timestamp"))
