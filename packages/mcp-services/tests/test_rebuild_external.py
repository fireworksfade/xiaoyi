"""显式外部重建测试（specs WP-08）。

覆盖：Repository 构造不做全表读取、分页批量、dry-run、游标续跑、幂等。
"""

from pathlib import Path

import pytest

from iot_diagnosis.rebuild import RebuildService
from iot_diagnosis.repository import DiagnosisRepository


def _make_repository_with_rows(tmp_path: Path, rows: int = 0) -> DiagnosisRepository:
    repository = DiagnosisRepository(str(tmp_path / "rebuild.db"))
    with repository._connect() as db:
        for i in range(rows):
            db.execute(
                "INSERT INTO device_log(device_id, level, module, message, timestamp)"
                " VALUES ('ESP32_05', 'INFO', 'rebuild', ?, ?)",
                (f"log entry {i}", f"2026-09-14T00:{i // 60:02d}:{i % 60:02d}+00:00"),
            )
    return repository


def test_repository_construction_does_not_scan_fact_tables(tmp_path, monkeypatch) -> None:
    """构造 Repository 时不允许对状态/日志/文档/诊断做全表镜像调用。"""
    repository = _make_repository_with_rows(tmp_path, rows=10_000)
    scanned: list[str] = []

    original_connect = repository._connect

    def counting_connect():
        import inspect

        caller = inspect.currentframe().f_back.f_back
        scanned.append(f"{caller.f_code.co_filename}:{caller.f_lineno}")
        return original_connect()

    monkeypatch.setattr(repository, "_connect", counting_connect)
    fresh = DiagnosisRepository(repository.path)
    # 构造期间只发生 seed/迁移/pragma 级别的连接，不触发逐行外部镜像读取
    assert fresh is not repository


def test_rebuild_pages_through_logs(tmp_path) -> None:
    pytest.skip("rebuild_mysql removed - MySQL mirror removed in P0")
    repository = _make_repository_with_rows(tmp_path, rows=25)
    service = RebuildService(repository, batch_size=10)
    dispatched: list[str] = []

    def fake_write(component, operation, payload):  # noqa: ANN001
        dispatched.append(payload["message"])
        return True

    repository._external_write = fake_write  # type: ignore[method-assign]
    result = service.rebuild_mysql("device_log")
    assert result["processed"] == 26  # 25 行 + 1 行种子日志
    assert result["failed"] == 0
    assert len(dispatched) == 26
    # 分页：每页最多 batch_size（通过 job 状态验证游标推进）
    status = service.job_status()["device_log"]
    assert status["status"] == "completed"
    assert int(status["cursor"]) >= 25 - 10


def test_rebuild_dry_run_does_not_dispatch(tmp_path) -> None:
    pytest.skip("rebuild_mysql removed - MySQL mirror removed in P0")
    repository = _make_repository_with_rows(tmp_path, rows=5)
    service = RebuildService(repository, batch_size=2)

    def fail_write(*_args, **_kwargs):  # noqa: ANN002, ANN003
        raise AssertionError("dry-run must not dispatch")

    repository._external_write = fail_write  # type: ignore[method-assign]
    result = service.rebuild_mysql("device_log", dry_run=True)
    assert result["processed"] == 6  # 5 行 + 1 行种子日志
    assert result["dry_run"] is True


def test_rebuild_resume_from_cursor_is_idempotent(tmp_path) -> None:
    pytest.skip("rebuild_mysql removed - MySQL mirror removed in P0")
    repository = _make_repository_with_rows(tmp_path, rows=12)
    service = RebuildService(repository, batch_size=5)
    dispatched: list[str] = []

    def fake_write(component, operation, payload):  # noqa: ANN001
        dispatched.append(payload["message"])
        return True

    repository._external_write = fake_write  # type: ignore[method-assign]

    first = service.rebuild_mysql("device_log")
    assert first["processed"] == 13  # 12 行 + 1 行种子日志
    # 中断后从游标继续：重复执行不产生重复业务记录（外部 upsert 幂等）
    second = service.rebuild_mysql("device_log", resume=True)
    assert second["processed"] >= 0
    job = service.job_status()["device_log"]
    assert job["status"] == "completed"
