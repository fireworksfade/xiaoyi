"""数据保留与清理（specs WP-07 / §6.4）。

默认只做 dry-run：输出每类候选数、最早/最晚时间，不删除任何行。
删除由 `DIAGNOSIS_RETENTION_DELETE_ENABLED=true` 显式开启；分批执行并输出统计。
未完成 outbox 永不自动删除；legacy 状态表由显式命令清理，不进入周期任务。
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("xiaoyi.iot_diagnosis.retention")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _env_days(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        logger.warning("invalid retention env %s; using default %s", name, default)
        return default


@dataclass
class RetentionConfig:
    telemetry_days: int = 14
    info_log_days: int = 14
    error_log_days: int = 90
    record_days: int = 180
    outbox_completed_days: int = 7
    interval_hours: int = 6
    batch_size: int = 1000
    delete_enabled: bool = False

    @classmethod
    def from_env(cls) -> "RetentionConfig":
        return cls(
            telemetry_days=_env_days("DIAGNOSIS_TELEMETRY_RETENTION_DAYS", 14),
            info_log_days=_env_days("DIAGNOSIS_INFO_LOG_RETENTION_DAYS", 14),
            error_log_days=_env_days("DIAGNOSIS_ERROR_LOG_RETENTION_DAYS", 90),
            record_days=_env_days("DIAGNOSIS_RECORD_RETENTION_DAYS", 180),
            outbox_completed_days=_env_days("DIAGNOSIS_OUTBOX_COMPLETED_RETENTION_DAYS", 7),
            interval_hours=_env_days("DIAGNOSIS_RETENTION_INTERVAL_HOURS", 6),
            batch_size=max(1, _env_days("DIAGNOSIS_RETENTION_BATCH_SIZE", 1000)),
            delete_enabled=os.getenv("DIAGNOSIS_RETENTION_DELETE_ENABLED", "false").lower()
            == "true",
        )

    def cutoff(self, days: int) -> str:
        return (utc_now() - timedelta(days=days)).isoformat()


# 类别 → (表, received/created 时间列, 等级列, 保留天数来源)
# received_at/timestamp 均为 ISO 文本，可直接字典序比较
@dataclass
class _Category:
    key: str
    table: str
    time_column: str
    days: int
    level_column: str | None = None
    levels: tuple[str, ...] = ()


_CATEGORIES_TMPL = lambda cfg: [  # noqa: E731
    _Category("telemetry", "device_telemetry", "received_at", cfg.telemetry_days),
    _Category(
        "logs_info",
        "device_log",
        "timestamp",
        cfg.info_log_days,
        level_column="level",
        levels=("INFO", "DEBUG"),
    ),
    _Category(
        "logs_error",
        "device_log",
        "timestamp",
        cfg.error_log_days,
        level_column="level",
        levels=("WARNING", "ERROR", "CRITICAL"),
    ),
]


def _where(category: _Category, cutoff: str, cfg: RetentionConfig) -> tuple[str, list[Any]]:
    where = [f"{category.time_column} IS NOT NULL", f"{category.time_column} < ?"]
    params: list[Any] = [cutoff]
    if category.level_column:
        placeholders = ", ".join("?" for _ in category.levels)
        where.append(f"{category.level_column} IN ({placeholders})")
        params.extend(category.levels)
    return " AND ".join(where), params


@dataclass
class RetentionReport:
    delete_enabled: bool
    dry_run: bool
    candidates: dict[str, dict[str, Any]] = field(default_factory=dict)
    deleted: dict[str, int] = field(default_factory=dict)
    failures: dict[str, str] = field(default_factory=dict)
    duration_ms: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "delete_enabled": self.delete_enabled,
            "dry_run": self.dry_run,
            "candidates": self.candidates,
            "deleted": self.deleted,
            "failures": self.failures,
            "duration_ms": self.duration_ms,
        }


class RetentionService:
    def __init__(self, path: str, config: RetentionConfig | None = None):
        self.path = path
        self.config = config or RetentionConfig.from_env()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        return connection

    def _table_exists(self, db: sqlite3.Connection, table: str) -> bool:
        return bool(
            db.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name = ?", (table,)
            ).fetchone()
        )

    def _candidates(self, db: sqlite3.Connection) -> dict[str, dict[str, Any]]:
        cfg = self.config
        categories = _CATEGORIES_TMPL(cfg) + [
            _Category("diagnosis_record", "diagnosis_record", "created_at", cfg.record_days),
            _Category(
                "outbox_completed",
                "external_sync_outbox",
                "completed_at",
                cfg.outbox_completed_days,
            ),
        ]
        report: dict[str, dict[str, Any]] = {}
        for category in categories:
            if not self._table_exists(db, category.table):
                continue
            where, params = _where(category, cfg.cutoff(category.days), cfg)
            row = db.execute(
                f"SELECT COUNT(*) AS n, MIN({category.time_column}) AS oldest, "
                f"MAX({category.time_column}) AS newest FROM {category.table} WHERE {where}",
                params,
            ).fetchone()
            if row["n"]:
                report[category.key] = {
                    "table": category.table,
                    "rows": row["n"],
                    "oldest": row["oldest"],
                    "newest": row["newest"],
                    "retention_days": category.days,
                }
        return report

    def _delete_in_batches(self, db: sqlite3.Connection, category: _Category, cutoff: str) -> int:
        cfg = self.config
        where, params = _where(category, cutoff, cfg)
        total = 0
        while True:
            with db:
                cursor = db.execute(
                    f"DELETE FROM {category.table} WHERE rowid IN "
                    f"(SELECT rowid FROM {category.table} WHERE {where} LIMIT ?)",
                    [*params, cfg.batch_size],
                )
                deleted = cursor.rowcount
            total += max(0, deleted)
            if deleted < cfg.batch_size:
                break
        return total

    def run(self, *, force_dry_run: bool = False) -> RetentionReport:
        started = utc_now()
        cfg = self.config
        dry_run = force_dry_run or not cfg.delete_enabled
        report = RetentionReport(delete_enabled=cfg.delete_enabled, dry_run=dry_run)
        db = self._connect()
        try:
            report.candidates = self._candidates(db)
            if dry_run:
                report.duration_ms = int((utc_now() - started).total_seconds() * 1000)
                return report
            categories = _CATEGORIES_TMPL(cfg)
            for category in categories:
                if category.key not in report.candidates:
                    continue
                try:
                    report.deleted[category.key] = self._delete_in_batches(
                        db, category, cfg.cutoff(category.days)
                    )
                except Exception as exc:
                    report.failures[category.key] = type(exc).__name__
                    logger.exception("retention delete failed for %s", category.key)
            # outbox：只删除已完成且过期
            try:
                report.deleted["outbox_completed"] = self._delete_in_batches(
                    db,
                    _Category(
                        "outbox_completed",
                        "external_sync_outbox",
                        "completed_at",
                        cfg.outbox_completed_days,
                    ),
                    cfg.cutoff(cfg.outbox_completed_days),
                )
            except Exception as exc:
                report.failures["outbox_completed"] = type(exc).__name__
            # diagnosis_record 默认保留（可能被案例/审计引用），删除需显式策略
            report.duration_ms = int((utc_now() - started).total_seconds() * 1000)
            logger.info("retention run", extra={"event": "retention_run", **report.to_dict()})
            return report
        finally:
            db.close()


def purge_legacy_status(
    path: str,
    *,
    dry_run: bool = True,
    batch_size: int = 1000,
) -> dict[str, Any]:
    """legacy device_status 表的显式去重/清理命令（不由周期任务调用）。"""
    db_path = Path(path)
    if not db_path.exists():
        return {"error": "DATABASE_NOT_FOUND", "path": str(db_path)}
    connection = sqlite3.connect(str(db_path), timeout=30)
    connection.row_factory = sqlite3.Row
    try:
        if not connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='device_status_legacy'"
        ).fetchone():
            return {"status": "no_legacy_table"}
        total = connection.execute("SELECT COUNT(*) FROM device_status_legacy").fetchone()[0]
        report: dict[str, Any] = {"legacy_rows": total, "dry_run": dry_run}
        if dry_run:
            return report
        deleted = 0
        while True:
            with connection:
                cursor = connection.execute(
                    "DELETE FROM device_status_legacy WHERE rowid IN "
                    "(SELECT rowid FROM device_status_legacy LIMIT ?)",
                    (batch_size,),
                )
                deleted += max(0, cursor.rowcount)
            if deleted >= total or cursor.rowcount == 0:
                break
        report["deleted"] = deleted
        return report
    finally:
        connection.close()


def report_to_json(report: dict[str, Any] | RetentionReport) -> str:
    if isinstance(report, RetentionReport):
        report = report.to_dict()
    return json.dumps(report, ensure_ascii=False, indent=2)
