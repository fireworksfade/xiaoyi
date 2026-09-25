"""MCP SQLite 迁移框架测试。

覆盖：空库升级、重复升级幂等、旧库缺列补齐、checksum 校验、
中途失败版本不前进、Repository 验证路径、CLI、backup。
"""

import sqlite3
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from common.migrations import (
    Migration,
    MigrationError,
    MySQLMigrationRunner,
    SQLiteMigrationRunner,
    load_migrations_from_dir,
)
from iot_control.repository import ControlRepository
from iot_diagnosis.repository import DiagnosisRepository
from scripts.migrate import get_runner

_ROOT = Path(__file__).resolve().parent.parent


def _runner(service: str) -> SQLiteMigrationRunner:
    directory = (
        _ROOT / ("iot_diagnosis" if service == "diagnosis" else "iot_control") / "migrations"
    )
    return SQLiteMigrationRunner(load_migrations_from_dir(directory), service=service)


@pytest.mark.parametrize("service", ["diagnosis", "control"])
def test_empty_db_upgrade_creates_schema(tmp_path: Path, service: str) -> None:
    db_path = str(tmp_path / f"{service}.db")
    runner = _runner(service)
    result = runner.upgrade(db_path)
    expected = {
        "diagnosis": [1, 2, 3, 4, 5],
        "control": [1, 2],
    }[service]
    assert result["applied"] == expected
    assert result["head"] == result["applied"][-1]
    with sqlite3.connect(db_path) as db:
        tables = {
            row[0]
            for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
    assert "schema_migrations" in tables
    expected = {"device", "knowledge_document"} if service == "diagnosis" else {"device_command"}
    assert expected <= tables
    # 重复升级幂等
    result = runner.upgrade(db_path)
    assert result["applied"] == []


def test_control_rejects_new_rows_without_diagnosis_id(tmp_path: Path) -> None:
    db_path = str(tmp_path / "control.db")
    _runner("control").upgrade(db_path)
    with sqlite3.connect(db_path) as db:
        with pytest.raises(sqlite3.IntegrityError, match="DIAGNOSIS_ID_REQUIRED"):
            db.execute(
                """INSERT INTO device_command
                (command_id, device_id, action, parameters_json, reason, issued_by,
                 risk_level, status, created_at, updated_at)
                VALUES ('CMD_1', 'ESP32_05', 'reconnect_mqtt', '{}', '', 'agent',
                        'low', 'pending', 'now', 'now')"""
            )


@pytest.mark.parametrize("service", ["diagnosis", "control"])
def test_verify_rejects_behind_db(tmp_path: Path, service: str) -> None:
    db_path = str(tmp_path / f"{service}.db")
    # 手工建一个"落后"库：只有版本表且记录 0 之前的状态不可行，
    # 直接校验空库走 initialize 而非 verify 的行为差异
    runner = _runner(service)
    runner.upgrade(db_path)
    runner.verify(db_path)  # head：通过

    # 模拟更老的库：版本回退
    with sqlite3.connect(db_path) as db:
        db.execute("DELETE FROM schema_migrations")
        db.commit()
    with pytest.raises(MigrationError) as excinfo:
        runner.verify(db_path)
    assert (
        excinfo.value.code == "MIGRATION_FAILED" or excinfo.value.code == "DATABASE_SCHEMA_BEHIND"
    )


def test_checksum_mismatch_rejected(tmp_path: Path) -> None:
    db_path = str(tmp_path / "diagnosis.db")
    runner = _runner("diagnosis")
    runner.upgrade(db_path)
    # 篡改 checksum 模拟脚本被修改
    with sqlite3.connect(db_path) as db:
        db.execute("UPDATE schema_migrations SET checksum = 'deadbeef'")
        db.commit()
    with pytest.raises(MigrationError) as excinfo:
        runner.status(db_path)
    assert excinfo.value.code == "MIGRATION_CHECKSUM_MISMATCH"


def test_legacy_db_missing_column_upgraded(tmp_path: Path) -> None:
    """旧库（表存在但缺 claimed_at/document_id/chunk_index 列）由迁移补齐。"""
    db_path = str(tmp_path / "legacy.db")
    with sqlite3.connect(db_path) as db:
        db.executescript(
            """
            CREATE TABLE device (device_id TEXT PRIMARY KEY, device_type TEXT NOT NULL,
                name TEXT NOT NULL, firmware_version TEXT, created_at TEXT NOT NULL);
            CREATE TABLE diagnosis_record (
                diagnosis_id TEXT PRIMARY KEY, request_id TEXT NOT NULL, device_id TEXT NOT NULL,
                query TEXT NOT NULL, fault_type TEXT NOT NULL, fault_name TEXT NOT NULL,
                cause TEXT NOT NULL, solutions_json TEXT NOT NULL, confidence REAL NOT NULL,
                router_type TEXT NOT NULL, selected_sources_json TEXT NOT NULL,
                retrieved_documents_json TEXT NOT NULL, retrieval_count INTEGER NOT NULL,
                rerank_count INTEGER NOT NULL, total_latency_ms REAL NOT NULL,
                created_at TEXT NOT NULL
            );
            INSERT INTO diagnosis_record VALUES
                ('DIA_1', 'req-1', 'ESP32_05', 'q', 't', 'n', 'c', '[]', 0.9, 'rule',
                 '[]', '[]', 0, 0, 1.0, '2026-01-01T00:00:00+00:00');
            """
        )
    runner = _runner("diagnosis")
    runner.upgrade(db_path)
    with sqlite3.connect(db_path) as db:
        columns = {row[1] for row in db.execute("PRAGMA table_info(diagnosis_record)").fetchall()}
        row = db.execute(
            "SELECT error, input_tokens FROM diagnosis_record WHERE diagnosis_id = 'DIA_1'"
        ).fetchone()
    assert {"result_json", "error", "input_tokens"} <= columns
    assert row[0] is None  # 兼容列使用默认值


def test_failed_migration_does_not_record_version(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = str(tmp_path / "failing.db")

    def boom(_db) -> None:
        raise RuntimeError("boom")

    broken = Migration(version=1, name="broken", upgrade=boom, checksum="x")
    runner = SQLiteMigrationRunner([broken], service="test")
    with pytest.raises(MigrationError) as excinfo:
        runner.upgrade(db_path)
    assert excinfo.value.code == "MIGRATION_FAILED"
    with sqlite3.connect(db_path) as db:
        count = db.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0]
    assert count == 0


def test_sequence_must_be_contiguous() -> None:
    migrations = [Migration(version=2, name="skip", upgrade=lambda db: None, checksum="x")]
    with pytest.raises(MigrationError) as excinfo:
        SQLiteMigrationRunner(migrations, service="test")
    assert excinfo.value.code == "MIGRATION_SEQUENCE_INVALID"


def test_mysql_runner_reads_rows_from_cursor() -> None:
    """PyMySQL execute 返回行数，结果必须从 cursor.fetchall 读取。"""
    cursor = MagicMock()
    cursor.execute.return_value = 0
    cursor.fetchall.return_value = []
    connection = MagicMock()
    connection.__enter__.return_value = connection
    connection.cursor.return_value = cursor

    MySQLMigrationRunner([], service="test").ensure(lambda: connection)

    cursor.fetchall.assert_called_once_with()


def test_repository_construction_uses_runner(tmp_path: Path) -> None:
    """Repository 构造（auto_migrate 默认）等价于迁移到 head。"""
    repository = DiagnosisRepository(str(tmp_path / "diag.db"))
    status = get_runner("diagnosis").status(str(tmp_path / "diag.db"))
    assert status["pending"] == []
    assert repository.get_device_status("ESP32_05") is not None  # seed 数据生效

    ControlRepository(str(tmp_path / "control.db"))
    status = get_runner("control").status(str(tmp_path / "control.db"))
    assert status["pending"] == []


def test_repository_verify_only_mode(tmp_path: Path) -> None:
    """auto_migrate=False 且库落后时拒绝构造。"""
    db_path = str(tmp_path / "behind.db")
    with sqlite3.connect(db_path) as db:
        db.execute("CREATE TABLE legacy (id INTEGER PRIMARY KEY)")
        db.commit()
    with pytest.raises(MigrationError):
        DiagnosisRepository(db_path, auto_migrate=False)


def test_sqlite_backup(tmp_path: Path) -> None:
    db_path = str(tmp_path / "diag.db")
    _runner("diagnosis").upgrade(db_path)
    target = str(tmp_path / "backup.db")
    _runner("diagnosis").backup(db_path, target)
    with sqlite3.connect(target) as db:
        tables = {
            row[0]
            for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
    assert "schema_migrations" in tables


def test_migrate_cli(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    from scripts import migrate as migrate_cli

    db_path = tmp_path / "cli.db"
    import os

    os.environ["DIAGNOSIS_DATABASE_PATH"] = str(db_path)
    try:
        assert migrate_cli.main(["--service", "diagnosis", "status"]) == 0
        first = capsys.readouterr().out
        assert '"pending": [1, 2, 3, 4, 5]' in first

        assert migrate_cli.main(["--service", "diagnosis", "upgrade", "--dry-run"]) == 0
        capsys.readouterr()

        assert migrate_cli.main(["--service", "diagnosis", "upgrade"]) == 0
        capsys.readouterr()

        assert migrate_cli.main(["--service", "diagnosis", "status"]) == 0
        final = capsys.readouterr().out
        assert '"pending": []' in final or '"pending":[]' in final.replace(" ", "")

        assert migrate_cli.main(["upgrade", "--service", "diagnosis"]) == 0
        command_first = capsys.readouterr().out
        assert '"applied": []' in command_first
    finally:
        del os.environ["DIAGNOSIS_DATABASE_PATH"]
