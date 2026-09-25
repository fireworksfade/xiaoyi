from typing import Any

from iot_diagnosis.repository_common import iso


class LogRepositoryMixin:
    def add_log(self, device_id: str, payload: dict[str, Any]) -> None:
        received_at = iso()
        self.upsert_device_metadata(device_id, {}, received_at)
        item = {
            "device_id": device_id,
            "level": str(payload.get("level") or "INFO").upper(),
            "module": str(payload.get("module") or "device"),
            "message": str(payload.get("message") or ""),
            "timestamp": str(payload.get("timestamp") or received_at),
        }
        with self._lock, self._connect() as db:
            db.execute(
                "INSERT INTO device_log(device_id, level, module, message, timestamp) VALUES (?, ?, ?, ?, ?)",
                (
                    item["device_id"],
                    item["level"],
                    item["module"],
                    item["message"],
                    item["timestamp"],
                ),
            )
        # MySQL 镜像已移除 - 日志仅存储在 SQLite

    def add_fault(self, device_id: str, payload: dict[str, Any]) -> None:
        fault_type = str(payload.get("fault_type") or payload.get("type") or "unknown")
        message = str(payload.get("message") or payload.get("description") or fault_type)
        self.add_log(
            device_id,
            {
                "timestamp": payload.get("timestamp") or iso(),
                "level": payload.get("level") or "ERROR",
                "module": f"fault:{fault_type}",
                "message": message,
            },
        )
