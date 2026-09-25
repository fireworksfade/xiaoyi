"""IoT Control MCP 本地存储：设备命令与修复提案，SQLite 为事实源。"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from common.migrations import SQLiteMigrationRunner, load_migrations_from_dir

logger = logging.getLogger("xiaoyi.iot_control.repository")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso(value: datetime | None = None) -> str:
    return (value or utc_now()).isoformat()


def new_command_id() -> str:
    return f"CMD_{utc_now().strftime('%Y%m%d')}_{uuid.uuid4().hex[:8].upper()}"


def new_proposal_id() -> str:
    return f"RPR_{utc_now().strftime('%Y%m%d')}_{uuid.uuid4().hex[:8].upper()}"


class ControlRepository:
    def __init__(
        self,
        path: str,
        command_timeout_seconds: int = 30,
        verify_window_seconds: int = 60,
        proposal_ttl_minutes: int = 30,
        *,
        auto_migrate: bool = True,
    ):
        self.path = path
        self.command_timeout_seconds = max(1, command_timeout_seconds)
        self.verify_window_seconds = max(1, verify_window_seconds)
        self.proposal_ttl_minutes = max(1, proposal_ttl_minutes)
        self._lock = threading.RLock()
        # 恢复验证观察窗口：applied 后的设备状态/日志采样，仅在内存中保留，
        # 最终结论会写回命令与提案行。
        self._watches: dict[str, dict[str, Any]] = {}
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._initialize(auto_migrate=auto_migrate)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    @staticmethod
    def migration_runner() -> SQLiteMigrationRunner:
        return SQLiteMigrationRunner(
            load_migrations_from_dir(Path(__file__).resolve().parent / "migrations"),
            service="iot_control",
        )

    def _initialize(self, *, auto_migrate: bool = True) -> None:
        """Repository 构造只做初始化/验证：空库执行迁移，已有库验证版本。"""
        runner = self.migration_runner()
        if auto_migrate:
            runner.initialize(self.path)
        else:
            runner.verify(self.path)

    # ------------------------------------------------------------------ 命令

    def create_command(
        self,
        device_id: str,
        action: str,
        risk_level: str,
        diagnosis_id: str,
        parameters: dict[str, Any] | None = None,
        reason: str = "",
        issued_by: str = "",
        proposal_id: str | None = None,
    ) -> dict[str, Any]:
        now = iso()
        command = {
            "command_id": new_command_id(),
            "device_id": device_id,
            "action": action,
            "parameters": parameters or {},
            "reason": reason,
            "issued_by": issued_by,
            "risk_level": risk_level,
            "proposal_id": proposal_id,
            "diagnosis_id": diagnosis_id,
            "status": "pending",
            "verify_status": None,
            "ack": None,
            "case_status": None,
            "case_id": None,
            "case_attempts": 0,
            "created_at": now,
            "updated_at": now,
            "acked_at": None,
        }
        with self._lock, self._connect() as db:
            db.execute(
                """INSERT INTO device_command
                (command_id, device_id, action, parameters_json, reason, issued_by,
                 risk_level, proposal_id, diagnosis_id, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)""",
                (
                    command["command_id"],
                    device_id,
                    action,
                    json.dumps(command["parameters"], ensure_ascii=False),
                    reason,
                    issued_by,
                    risk_level,
                    proposal_id,
                    diagnosis_id,
                    now,
                    now,
                ),
            )
        return command

    def get_command(self, command_id: str) -> dict[str, Any] | None:
        with self._lock, self._connect() as db:
            row = db.execute(
                "SELECT * FROM device_command WHERE command_id = ?", (command_id,)
            ).fetchone()
        return self._command_from_row(row) if row else None

    def mark_command_ack(
        self, command_id: str, status: str, ack: dict[str, Any]
    ) -> dict[str, Any] | None:
        """设备回执：pending -> acked；applied 时启动恢复验证观察窗口。"""
        now = iso()
        with self._lock, self._connect() as db:
            row = db.execute(
                "SELECT * FROM device_command WHERE command_id = ?", (command_id,)
            ).fetchone()
            if not row or row["status"] not in ("pending", "acked"):
                return None
            next_status = "applied" if status == "applied" else "failed"
            db.execute(
                """UPDATE device_command
                SET status = ?, ack_json = ?, acked_at = ?, updated_at = ?
                WHERE command_id = ?""",
                (next_status, json.dumps(ack, ensure_ascii=False), now, now, command_id),
            )
            row = db.execute(
                "SELECT * FROM device_command WHERE command_id = ?", (command_id,)
            ).fetchone()
        command = self._command_from_row(row)
        if command is not None and next_status == "applied":
            self._start_watch(command)
        return command

    def _start_watch(self, command: dict[str, Any]) -> None:
        now = utc_now()
        with self._lock:
            self._watches[command["device_id"]] = {
                "command_id": command["command_id"],
                "proposal_id": command.get("proposal_id"),
                "deadline": now + timedelta(seconds=self.verify_window_seconds),
                "status_seen": False,
                "error_seen": False,
            }

    def record_status_sample(self, device_id: str, online: Any) -> None:
        with self._lock:
            watch = self._watches.get(device_id)
            if watch and online:
                watch["status_seen"] = True

    def record_log_sample(self, device_id: str, level: str) -> None:
        with self._lock:
            watch = self._watches.get(device_id)
            if watch and str(level).upper() in ("ERROR", "CRITICAL"):
                watch["error_seen"] = True

    def mark_timed_out_commands(self) -> list[str]:
        deadline = iso(utc_now() - timedelta(seconds=self.command_timeout_seconds))
        timed_out: list[str] = []
        with self._lock, self._connect() as db:
            rows = db.execute(
                """SELECT command_id FROM device_command
                WHERE status = 'pending' AND created_at < ?""",
                (deadline,),
            ).fetchall()
            for row in rows:
                db.execute(
                    """UPDATE device_command
                    SET status = 'timeout', updated_at = ? WHERE command_id = ?""",
                    (iso(), row["command_id"]),
                )
                timed_out.append(row["command_id"])
        return timed_out

    def finalize_watches(self, now: datetime | None = None) -> list[dict[str, Any]]:
        """观察窗口到期后给出恢复结论，并同步关联提案的任务状态。"""
        finalized: list[dict[str, Any]] = []
        now = now or utc_now()
        with self._lock:
            due = [
                (device_id, watch)
                for device_id, watch in self._watches.items()
                if watch["deadline"] <= now
            ]
            for device_id, _watch in due:
                self._watches.pop(device_id, None)
            for device_id, watch in due:
                verify_status = (
                    "succeeded" if watch["status_seen"] and not watch["error_seen"] else "failed"
                )
                finalized.append(
                    {
                        "device_id": device_id,
                        "command_id": watch["command_id"],
                        "proposal_id": watch.get("proposal_id"),
                        "verify_status": verify_status,
                    }
                )
        for item in finalized:
            self._store_verify_result(item["command_id"], item["verify_status"])
        return finalized

    def _store_verify_result(self, command_id: str, verify_status: str) -> None:
        now = iso()
        with self._lock, self._connect() as db:
            db.execute(
                "UPDATE device_command SET verify_status = ?, updated_at = ? WHERE command_id = ?",
                (verify_status, now, command_id),
            )
            db.execute(
                """UPDATE remediation_proposal SET task_status = ?, updated_at = ?
                WHERE command_id = ? AND status = 'approved'""",
                (verify_status, now, command_id),
            )
            # 成功的命令等待诊断服务回发案例确认（case_status: pending -> archived）
            if verify_status == "succeeded":
                db.execute(
                    """UPDATE device_command SET case_status = 'pending'
                    WHERE command_id = ? AND case_status IS NULL""",
                    (command_id,),
                )

    def mark_case_archived(self, command_id: str, case_id: str) -> None:
        """收到诊断服务的案例确认事件后，把 case_id 关联回命令。"""
        now = iso()
        with self._lock, self._connect() as db:
            db.execute(
                """UPDATE device_command
                SET case_status = 'archived', case_id = ?, updated_at = ?
                WHERE command_id = ?""",
                (case_id, now, command_id),
            )

    def process_timeouts(self) -> list[dict[str, Any]]:
        """由 server lifespan 周期调用：命令超时与验证窗口收敛。

        返回本轮收敛出最终结论的命令，供上层发布修复完成事件。
        """
        self.mark_timed_out_commands()
        return self.finalize_watches()

    # ------------------------------------------------------------------ 提案

    def create_proposal(
        self,
        device_id: str,
        action: str,
        diagnosis_id: str,
        parameters: dict[str, Any] | None = None,
        reason: str = "",
        impact: str = "",
    ) -> dict[str, Any]:
        now = utc_now()
        proposal = {
            "proposal_id": new_proposal_id(),
            "device_id": device_id,
            "action": action,
            "parameters": parameters or {},
            "reason": reason,
            "impact": impact,
            "status": "pending",
            "version": 1,
            "expires_at": iso(now + timedelta(minutes=self.proposal_ttl_minutes)),
            "task_status": None,
            "command_id": None,
            "diagnosis_id": diagnosis_id,
            "decided_by": None,
            "decided_at": None,
            "created_at": iso(now),
            "updated_at": iso(now),
        }
        with self._lock, self._connect() as db:
            db.execute(
                """INSERT INTO remediation_proposal
                (proposal_id, device_id, action, parameters_json, reason, impact,
                 status, version, expires_at, diagnosis_id, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, 'pending', 1, ?, ?, ?, ?)""",
                (
                    proposal["proposal_id"],
                    device_id,
                    action,
                    json.dumps(proposal["parameters"], ensure_ascii=False),
                    reason,
                    impact,
                    proposal["expires_at"],
                    diagnosis_id,
                    proposal["created_at"],
                    proposal["updated_at"],
                ),
            )
        return proposal

    def _expire_stale(self, db: sqlite3.Connection) -> None:
        db.execute(
            """UPDATE remediation_proposal SET status = 'expired', updated_at = ?
            WHERE status = 'pending' AND expires_at < ?""",
            (iso(), iso()),
        )

    def list_proposals(
        self, status: str | None = None, limit: int = 50, offset: int = 0
    ) -> dict[str, Any]:
        with self._lock, self._connect() as db:
            self._expire_stale(db)
            clauses = ["status = ?"] if status else ["1=1"]
            params: list[Any] = [status] if status else []
            total = db.execute(
                f"SELECT COUNT(*) FROM remediation_proposal WHERE {' AND '.join(clauses)}",
                params,
            ).fetchone()[0]
            rows = db.execute(
                f"""SELECT * FROM remediation_proposal WHERE {" AND ".join(clauses)}
                ORDER BY created_at DESC, proposal_id DESC LIMIT ? OFFSET ?""",
                [*params, limit, offset],
            ).fetchall()
        return {"items": [self._proposal_from_row(row) for row in rows], "total": total}

    def get_proposal(self, proposal_id: str) -> dict[str, Any] | None:
        with self._lock, self._connect() as db:
            self._expire_stale(db)
            row = db.execute(
                "SELECT * FROM remediation_proposal WHERE proposal_id = ?", (proposal_id,)
            ).fetchone()
        return self._proposal_from_row(row) if row else None

    def decide_proposal(
        self,
        proposal_id: str,
        decision: str,
        decided_by: str,
        expected_version: int,
        risk_level_of,
    ) -> tuple[dict[str, Any], dict[str, Any] | None]:
        """乐观锁决策；approved 时创建高风险命令（由调用方负责发布到设备）。"""
        now = iso()
        with self._lock, self._connect() as db:
            self._expire_stale(db)
            row = db.execute(
                "SELECT * FROM remediation_proposal WHERE proposal_id = ?", (proposal_id,)
            ).fetchone()
            if not row:
                raise LookupError("PROPOSAL_NOT_FOUND")
            if row["status"] != "pending":
                raise ValueError("PROPOSAL_NOT_PENDING")
            if row["version"] != expected_version:
                raise ValueError("VERSION_CONFLICT")
            next_status = "approved" if decision == "approved" else "rejected"
            command: dict[str, Any] | None = None
            if next_status == "approved":
                command = {
                    "command_id": new_command_id(),
                    "device_id": row["device_id"],
                    "action": row["action"],
                    "parameters": json.loads(row["parameters_json"] or "{}"),
                    "reason": row["reason"],
                    "issued_by": decided_by,
                    "risk_level": risk_level_of(row["action"]),
                    "proposal_id": proposal_id,
                    "diagnosis_id": row["diagnosis_id"],
                    "status": "pending",
                    "verify_status": None,
                    "ack": None,
                    "case_status": None,
                    "case_id": None,
                    "case_attempts": 0,
                    "created_at": now,
                    "updated_at": now,
                    "acked_at": None,
                }
                db.execute(
                    """INSERT INTO device_command
                    (command_id, device_id, action, parameters_json, reason, issued_by,
                     risk_level, proposal_id, diagnosis_id, status, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)""",
                    (
                        command["command_id"],
                        command["device_id"],
                        command["action"],
                        json.dumps(command["parameters"], ensure_ascii=False),
                        command["reason"],
                        command["issued_by"],
                        command["risk_level"],
                        proposal_id,
                        row["diagnosis_id"],
                        now,
                        now,
                    ),
                )
            db.execute(
                """UPDATE remediation_proposal
                SET status = ?, version = version + 1, task_status = ?, command_id = ?,
                    decided_by = ?, decided_at = ?, updated_at = ?
                WHERE proposal_id = ? AND version = ?""",
                (
                    next_status,
                    "running" if next_status == "approved" else None,
                    command["command_id"] if command else None,
                    decided_by,
                    now,
                    now,
                    proposal_id,
                    expected_version,
                ),
            )
            if db.execute("SELECT changes()").fetchone()[0] == 0:
                raise ValueError("VERSION_CONFLICT")
            row = db.execute(
                "SELECT * FROM remediation_proposal WHERE proposal_id = ?", (proposal_id,)
            ).fetchone()
        return self._proposal_from_row(row), command

    # ------------------------------------------------------------------ 序列化

    def _command_from_row(self, row: sqlite3.Row) -> dict[str, Any]:
        keys = row.keys()
        return {
            "command_id": row["command_id"],
            "device_id": row["device_id"],
            "action": row["action"],
            "parameters": json.loads(row["parameters_json"] or "{}"),
            "reason": row["reason"],
            "issued_by": row["issued_by"],
            "risk_level": row["risk_level"],
            "proposal_id": row["proposal_id"],
            "diagnosis_id": row["diagnosis_id"] if "diagnosis_id" in keys else None,
            "status": row["status"],
            "verify_status": row["verify_status"],
            "ack": json.loads(row["ack_json"]) if row["ack_json"] else None,
            "case_status": row["case_status"] if "case_status" in keys else None,
            "case_id": row["case_id"] if "case_id" in keys else None,
            "case_attempts": row["case_attempts"] if "case_attempts" in keys else 0,
            "case_error": row["case_error"] if "case_error" in keys else None,
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "acked_at": row["acked_at"],
        }

    def _proposal_from_row(self, row: sqlite3.Row) -> dict[str, Any]:
        keys = row.keys()
        return {
            "proposal_id": row["proposal_id"],
            "device_id": row["device_id"],
            "action": row["action"],
            "parameters": json.loads(row["parameters_json"] or "{}"),
            "reason": row["reason"],
            "impact": row["impact"],
            "status": row["status"],
            "version": row["version"],
            "expires_at": row["expires_at"],
            "task_status": row["task_status"],
            "command_id": row["command_id"],
            "diagnosis_id": row["diagnosis_id"] if "diagnosis_id" in keys else None,
            "decided_by": row["decided_by"],
            "decided_at": row["decided_at"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }
