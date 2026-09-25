"""保留策略测试（specs WP-07）。

覆盖：dry-run 不修改行、分批删除收敛、日志分级截止日期、
outbox 未完成不删、legacy 表显式清理。
"""

from datetime import datetime, timedelta, timezone

from iot_diagnosis.repository import DiagnosisRepository
from iot_diagnosis.retention import RetentionConfig, RetentionService, purge_legacy_status


def _iso(days_ago: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()


def _service(path: str, *, delete_enabled: bool) -> RetentionService:
    config = RetentionConfig(
        telemetry_days=14,
        info_log_days=14,
        error_log_days=90,
        record_days=180,
        outbox_completed_days=7,
        batch_size=3,
        delete_enabled=delete_enabled,
    )
    return RetentionService(path, config)


def _seed_repository(tmp_path) -> DiagnosisRepository:
    repo = DiagnosisRepository(str(tmp_path / "retention.db"))
    return repo


def _insert(repo: DiagnosisRepository) -> None:
    received_old = _iso(30)
    received_recent = _iso(1)
    with repo._connect() as db:
        for i in range(10):
            db.execute(
                """INSERT OR IGNORE INTO device_telemetry
                (device_id, temperature, rssi, uptime, wifi_status, mqtt_status,
                 device_timestamp, received_at, payload_hash)
                VALUES ('ESP32_05', ?, NULL, NULL, NULL, NULL, ?, ?, ?)""",
                (20.0 + i, f"2026-09-{10 + i:02d}T00:00:00+00:00", received_old, f"old-{i}"),
            )
        for _i in range(4):
            db.execute(
                "INSERT INTO device_log(device_id, level, module, message, timestamp)"
                " VALUES ('ESP32_05', 'INFO', 'test', 'old info', ?)",
                (received_old,),
            )
        db.execute(
            "INSERT INTO device_log(device_id, level, module, message, timestamp)"
            " VALUES ('ESP32_05', 'ERROR', 'test', 'old error', ?)",
            (received_old,),
        )
        db.execute(
            "INSERT INTO device_log(device_id, level, module, message, timestamp)"
            " VALUES ('ESP32_05', 'INFO', 'test', 'fresh info', ?)",
            (received_recent,),
        )
        db.execute(
            """INSERT INTO external_sync_outbox
            (id, dedupe_key, component, operation, payload_json, attempts, created_at, updated_at, completed_at)
            VALUES ('out-done', 'k1', 'mysql', 'add_log', '{}', 0, ?, ?, ?)""",
            (_iso(10), _iso(10), _iso(8)),
        )
        db.execute(
            """INSERT INTO external_sync_outbox
            (id, dedupe_key, component, operation, payload_json, attempts, created_at, updated_at)
            VALUES ('out-pending', 'k2', 'mysql', 'add_log', '{}', 5, ?, ?)""",
            (_iso(30), _iso(30)),
        )


def test_dry_run_does_not_modify_rows(tmp_path) -> None:
    repo = _seed_repository(tmp_path)
    _insert(repo)
    service = _service(repo.path, delete_enabled=False)
    report = service.run()
    assert report.dry_run
    assert report.deleted == {}
    assert report.candidates["telemetry"]["rows"] == 10
    assert report.candidates["logs_info"]["rows"] == 4
    assert report.candidates["outbox_completed"]["rows"] == 1

    with repo._connect() as db:
        assert db.execute("SELECT COUNT(*) FROM device_telemetry").fetchone()[0] == 10
        # 6 行测试日志 + 1 行种子日志
        assert db.execute("SELECT COUNT(*) FROM device_log").fetchone()[0] == 7
        assert db.execute("SELECT COUNT(*) FROM external_sync_outbox").fetchone()[0] == 2


def test_execute_deletes_in_batches_and_spares_pending_outbox(tmp_path) -> None:
    repo = _seed_repository(tmp_path)
    _insert(repo)
    service = _service(repo.path, delete_enabled=True)
    report = service.run()
    assert not report.dry_run
    assert report.deleted["telemetry"] == 10
    assert report.deleted["logs_info"] == 4
    # ERROR 日志保留 90 天，30 天的不删
    assert "logs_error" not in report.deleted
    assert report.deleted["outbox_completed"] == 1

    with repo._connect() as db:
        assert db.execute("SELECT COUNT(*) FROM device_telemetry").fetchone()[0] == 0
        # 保留：新鲜 INFO、旧 ERROR（90 天内）、种子 ERROR
        assert db.execute("SELECT COUNT(*) FROM device_log").fetchone()[0] == 3
        remaining = {
            row["id"] for row in db.execute("SELECT id FROM external_sync_outbox").fetchall()
        }
    assert remaining == {"out-pending"}  # 未完成 outbox 永不删除


def test_info_and_error_logs_use_separate_cutoffs(tmp_path) -> None:
    repo = _seed_repository(tmp_path)
    with repo._connect() as db:
        # 60 天前：INFO 应删（14 天），ERROR 应保留（90 天）
        old = _iso(60)
        db.execute(
            "INSERT INTO device_log(device_id, level, module, message, timestamp)"
            " VALUES ('ESP32_05', 'INFO', 't', 'i-old', ?)",
            (old,),
        )
        db.execute(
            "INSERT INTO device_log(device_id, level, module, message, timestamp)"
            " VALUES ('ESP32_05', 'ERROR', 't', 'e-old', ?)",
            (old,),
        )
    service = _service(repo.path, delete_enabled=True)
    report = service.run()
    assert report.deleted.get("logs_info") == 1
    assert "logs_error" not in report.deleted
    with repo._connect() as db:
        levels = {row["level"] for row in db.execute("SELECT level FROM device_log").fetchall()}
    assert levels == {"ERROR"}


def test_purge_legacy_status(tmp_path) -> None:
    repo = _seed_repository(tmp_path)
    # legacy 表在迁移后已存在（由 0002 重命名产生），只清理内容
    with repo._connect() as db:
        db.execute("DELETE FROM device_status_legacy")
        for i in range(7):
            db.execute(
                "INSERT INTO device (device_id, device_type, name, firmware_version, created_at, updated_at)"
                " VALUES (?, 'ESP32', ?, '1.0.0', ?, ?)",
                (f"ESP32_L{i}", f"legacy-{i}", _iso(1), _iso(1)),
            )
            db.execute(
                """INSERT INTO device_status_legacy
                (device_id, online, wifi_status, rssi, mqtt_status, temperature, uptime, timestamp)
                VALUES (?, 1, 'connected', -50, 'connected', 25.0, 3600, ?)""",
                (f"ESP32_L{i}", _iso(1)),
            )
    dry = purge_legacy_status(repo.path, dry_run=True)
    assert dry["legacy_rows"] == 7
    applied = purge_legacy_status(repo.path, dry_run=False)
    assert applied["deleted"] == 7
    with repo._connect() as db:
        count = db.execute("SELECT COUNT(*) FROM device_status_legacy").fetchone()[0]
    assert count == 0
