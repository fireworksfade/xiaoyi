"""IoT Control MCP 本地存储：设备命令与修复提案，SQLite 为事实源。"""

from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
import threading
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from common.migrations import SQLiteMigrationRunner, load_migrations_from_dir
from iot_control.verification import evaluate

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
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._initialize(auto_migrate=auto_migrate)

    def recover_delivery(self) -> None:
        """A crash during publish leaves an ambiguous result, never a safe retry."""
        with self._lock, self._connect() as db:
            db.execute("UPDATE command_outbox SET delivery_status = 'unknown' "
                       "WHERE delivery_status = 'dispatching'")

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            with connection:
                yield connection
        finally:
            connection.close()

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
        correlation_key: str | None = None,
        verification_baseline: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        now = iso()
        command: dict[str, Any] = {
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
            "created_at": now,
            "updated_at": now,
            "acked_at": None,
        }
        fingerprint = hashlib.sha256(json.dumps([device_id, action, diagnosis_id, parameters or {}, reason, issued_by, proposal_id], sort_keys=True).encode()).hexdigest()
        with self._lock, self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if correlation_key:
                prior = db.execute("SELECT * FROM action_correlation WHERE correlation_key = ?", (correlation_key,)).fetchone()
                if prior:
                    if prior["parameters_hash"] != fingerprint:
                        raise ValueError("ACTION_CORRELATION_CONFLICT")
                    return {**self._require_command(prior["command_id"]), "replayed": True}
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
            if correlation_key:
                db.execute("INSERT INTO action_correlation(correlation_key, parameters_hash, command_id) VALUES (?, ?, ?)", (correlation_key, fingerprint, command["command_id"]))
            db.execute("UPDATE command_outbox SET baseline_json = ? WHERE command_id = ?",
                       (json.dumps(verification_baseline or {}), command["command_id"]))
        return self._require_command(command["command_id"])

    def _require_command(self, command_id: str) -> dict[str, Any]:
        command = self.get_command(command_id)
        if command is None:
            raise LookupError("COMMAND_NOT_FOUND")
        return command

    def get_command(self, command_id: str) -> dict[str, Any] | None:
        with self._lock, self._connect() as db:
            row = db.execute(
                """SELECT c.*, o.delivery_status, o.expires_at, o.attempted_at,
                    o.confirmed_at FROM device_command c LEFT JOIN command_outbox o
                    ON o.command_id = c.command_id WHERE c.command_id = ?""", (command_id,)
            ).fetchone()
        return self._command_from_row(row) if row else None

    def mark_command_ack(
        self, command_id: str, status: str, ack: dict[str, Any], device_id: str | None = None
    ) -> dict[str, Any] | None:
        """Commit the ACK and its observation window in one transaction."""
        now = iso()
        with self._lock, self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT * FROM device_command WHERE command_id = ?", (command_id,)
            ).fetchone()
            if not row or row["status"] not in ("pending", "acked"):
                return None
            if device_id is not None and row["device_id"] != device_id:
                return None
            if status not in {"applied", "failed"}:
                return None
            next_status = "applied" if status == "applied" else "failed"
            db.execute(
                """UPDATE device_command
                SET status = ?, ack_json = ?, acked_at = ?, updated_at = ?
                WHERE command_id = ?""",
                (next_status, json.dumps(ack, ensure_ascii=False), now, now, command_id),
            )
            db.execute("UPDATE command_outbox SET delivery_status = 'device_acked' "
                       "WHERE command_id = ?", (command_id,))
            if next_status == "applied":
                db.execute("""INSERT OR IGNORE INTO command_verification
                    (command_id, device_id, started_at, deadline) VALUES (?, ?, ?, ?)""",
                    (command_id, row["device_id"], now,
                     iso(utc_now() + timedelta(seconds=self.verify_window_seconds))))
            db.execute("UPDATE remediation_proposal SET task_status = ?, updated_at = ? "
                       "WHERE command_id = ?", ("verifying" if next_status == "applied"
                                                else "failed", now, command_id))
            row = db.execute(
                "SELECT * FROM device_command WHERE command_id = ?", (command_id,)
            ).fetchone()
        command = self._command_from_row(row)
        return command

    @staticmethod
    def _sample_time(payload: dict[str, Any]) -> str | None:
        if not payload.get("timestamp"):
            return iso()
        try:
            value = datetime.fromisoformat(str(payload["timestamp"]).replace("Z", "+00:00"))
            if value.tzinfo is None or value > utc_now() + timedelta(seconds=5):
                return None
            return value.astimezone(timezone.utc).isoformat()
        except ValueError:
            return None

    def record_status_sample(self, device_id: str, payload: Any) -> None:
        # Legacy boolean samples do not carry action-specific evidence.
        state = payload if isinstance(payload, dict) else {"online": payload}
        sampled_at = self._sample_time(state)
        if sampled_at is None:
            return
        with self._lock, self._connect() as db:
            db.execute("""UPDATE command_verification SET status_json = ?
                WHERE device_id = ? AND started_at <= ? AND deadline >= ?
                AND COALESCE(json_extract(status_json, '$._sampled_at'), '') <= ?""",
                (json.dumps({**state, "_sampled_at": sampled_at}), device_id,
                 sampled_at, iso(), sampled_at))

    def record_log_sample(self, device_id: str, level: str, payload: dict | None = None) -> None:
        sampled_at = self._sample_time(payload or {})
        if sampled_at is None or str(level).upper() not in ("ERROR", "CRITICAL"):
            return
        with self._lock, self._connect() as db:
            db.execute("""UPDATE command_verification SET error_seen = 1
                WHERE device_id = ? AND started_at <= ? AND deadline >= ?""",
                (device_id, sampled_at, iso()))

    def mark_timed_out_commands(self) -> list[str]:
        deadline = iso(utc_now() - timedelta(seconds=self.command_timeout_seconds))
        timed_out: list[str] = []
        with self._lock, self._connect() as db:
            rows = db.execute(
                """SELECT c.command_id FROM device_command c JOIN command_outbox o
                ON o.command_id = c.command_id WHERE c.status = 'pending'
                AND ((o.delivery_status IN ('broker_confirmed', 'unknown')
                    AND COALESCE(o.confirmed_at, o.attempted_at, c.created_at) < ?)
                    OR o.expires_at < ?)""",
                (deadline, iso()),
            ).fetchall()
            for row in rows:
                db.execute(
                    """UPDATE device_command
                    SET status = 'timeout', updated_at = ? WHERE command_id = ?""",
                    (iso(), row["command_id"]),
                )
                timed_out.append(row["command_id"])
                db.execute("UPDATE remediation_proposal SET task_status = 'inconclusive', "
                           "updated_at = ? WHERE command_id = ?", (iso(), row["command_id"]))
        return timed_out

    def finalize_watches(self, now: datetime | None = None) -> list[dict[str, Any]]:
        """观察窗口到期后给出恢复结论，并同步关联提案的任务状态。"""
        finalized: list[dict[str, Any]] = []
        with self._lock, self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            due = db.execute("""SELECT v.*, c.action, c.parameters_json, c.proposal_id,
                o.baseline_json FROM command_verification v JOIN device_command c
                ON c.command_id = v.command_id JOIN command_outbox o
                ON o.command_id = c.command_id WHERE v.deadline <= ?""",
                (iso(now),)).fetchall()
            for watch in due:
                verify_status = "failed" if watch["error_seen"] else evaluate(
                    watch["action"], json.loads(watch["parameters_json"]),
                    json.loads(watch["status_json"]), json.loads(watch["baseline_json"]))
                finalized.append(
                    {
                        "device_id": watch["device_id"],
                        "command_id": watch["command_id"],
                        "proposal_id": watch["proposal_id"],
                        "verify_status": verify_status,
                    }
                )
                db.execute("UPDATE device_command SET verify_status = ?, updated_at = ? "
                           "WHERE command_id = ?", (verify_status, iso(), watch["command_id"]))
                db.execute("UPDATE remediation_proposal SET task_status = ?, updated_at = ? "
                           "WHERE command_id = ? AND status = 'approved'",
                           (verify_status, iso(), watch["command_id"]))
                db.execute("DELETE FROM command_verification WHERE command_id = ?",
                           (watch["command_id"],))
        return finalized

    def dispatch_command(self, command_id: str, sender) -> dict[str, Any]:
        """Claim once. Only a definitive non-send may return to the retry queue."""
        now = iso()
        with self._lock, self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            claimed = db.execute("""UPDATE command_outbox SET delivery_status = 'dispatching',
                attempts = attempts + 1, attempted_at = ? WHERE command_id = ?
                AND delivery_status = 'pending' AND next_attempt_at <= ? AND expires_at > ?
                AND EXISTS (SELECT 1 FROM device_command c
                    WHERE c.command_id = command_outbox.command_id AND c.status = 'pending')""",
                (now, command_id, now, now)).rowcount
        if not claimed:
            return self._require_command(command_id)
        command = self._require_command(command_id)
        try:
            delivery = sender(command["device_id"], command)
            if delivery not in {"pending", "broker_confirmed", "unknown"}:
                delivery = "unknown"
        except Exception:
            logger.exception("Command delivery result unknown: %s", command_id)
            delivery = "unknown"
        with self._lock, self._connect() as db:
            db.execute("""UPDATE command_outbox SET delivery_status = ?, confirmed_at = ?,
                next_attempt_at = ? WHERE command_id = ? AND delivery_status = 'dispatching'""",
                (delivery, iso() if delivery == "broker_confirmed" else None,
                 iso(utc_now() + timedelta(seconds=5)), command_id))
            db.execute("UPDATE action_correlation SET delivery_status = ? WHERE command_id = ? "
                       "OR proposal_id = (SELECT proposal_id FROM device_command WHERE command_id = ?)",
                       ("delivered" if delivery == "broker_confirmed" else "unknown",
                        command_id, command_id))
        return self._require_command(command_id)

    def dispatch_pending(self, sender, limit: int = 10) -> None:
        now = iso()
        with self._connect() as db:
            rows = db.execute("""SELECT command_id FROM command_outbox
                WHERE delivery_status = 'pending' AND next_attempt_at <= ? AND expires_at > ?
                ORDER BY next_attempt_at, command_id LIMIT ?""", (now, now, limit)).fetchall()
        for row in rows:
            self.dispatch_command(row["command_id"], sender)

    def set_correlation_delivery(self, correlation_key: str, delivered: bool) -> None:
        """记录关联键对应的 MQTT 投递结果；unknown 表示结果未知，不是失败。"""
        status = "delivered" if delivered else "unknown"
        with self._lock, self._connect() as db:
            db.execute(
                "UPDATE action_correlation SET delivery_status = ? WHERE correlation_key = ?",
                (status, correlation_key),
            )

    def process_timeouts(self) -> list[dict[str, Any]]:
        """由 server lifespan 周期调用：命令超时与验证窗口收敛。"""
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
        correlation_key: str | None = None,
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
        fingerprint = hashlib.sha256(json.dumps([device_id, action, diagnosis_id, parameters or {}, reason, impact], sort_keys=True).encode()).hexdigest()
        with self._lock, self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if correlation_key:
                prior = db.execute("SELECT * FROM action_correlation WHERE correlation_key = ?", (correlation_key,)).fetchone()
                if prior:
                    if prior["parameters_hash"] != fingerprint:
                        raise ValueError("ACTION_CORRELATION_CONFLICT")
                    row = db.execute("SELECT * FROM remediation_proposal WHERE proposal_id = ?", (prior["proposal_id"],)).fetchone()
                    return {**self._proposal_from_row(row), "replayed": True, "delivery_status": prior["delivery_status"]}
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
            if correlation_key:
                db.execute("INSERT INTO action_correlation(correlation_key, parameters_hash, proposal_id) VALUES (?, ?, ?)", (correlation_key, fingerprint, proposal["proposal_id"]))
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
        verification_baseline: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any] | None]:
        """乐观锁决策；approved 时创建高风险命令（由调用方负责发布到设备）。"""
        if decision not in {"approved", "rejected"}:
            raise ValueError("INVALID_DECISION")
        now = iso()
        with self._lock, self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
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
                db.execute("UPDATE command_outbox SET baseline_json = ? WHERE command_id = ?",
                           (json.dumps(verification_baseline or {}), command["command_id"]))
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
        return self._proposal_from_row(row), self.get_command(command["command_id"]) if command else None

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
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "acked_at": row["acked_at"],
            "delivery_status": row["delivery_status"] if "delivery_status" in keys else (
                "device_acked" if row["acked_at"] else "unknown"),
            "expires_at": row["expires_at"] if "expires_at" in keys else None,
            "broker_confirmed_at": row["confirmed_at"] if "confirmed_at" in keys else None,
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

    def get_action_by_correlation(self, correlation_key):
        with self._lock, self._connect() as db:
            row = db.execute("SELECT * FROM action_correlation WHERE correlation_key = ?", (correlation_key,)).fetchone()
        if not row:
            return None
        proposal = self.get_proposal(row["proposal_id"]) if row["proposal_id"] else None
        command_id = row["command_id"] or (proposal or {}).get("command_id")
        command = self.get_command(command_id) if command_id else None
        delivered = command and command["delivery_status"] in {"broker_confirmed", "device_acked"}
        return {"proposal": proposal, "command": command,
                "delivery_status": "delivered" if delivered else row["delivery_status"]}
