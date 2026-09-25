"""数据库迁移快照测试。

覆盖：空库升级、重复升级幂等、旧库 stamp 基线后升级且数据不变、
downgrade、schema ahead 检测、关键表缺失拒绝 stamp。
"""

from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, text

from app import migrations
from app.migrations import (
    BASELINE_REVISION,
    RevisionStatus,
    get_alembic_config,
)


def _make_engine(db_path: Path):
    url = f"sqlite:///{db_path.as_posix()}"
    return url, create_engine(url)


def _alembic_upgrade(url: str, revision: str) -> None:
    from alembic import command

    config = get_alembic_config()
    config.set_main_option("sqlalchemy.url", url)
    command.upgrade(config, revision)


def _alembic_stamp(url: str, revision: str) -> None:
    from alembic import command

    config = get_alembic_config()
    config.set_main_option("sqlalchemy.url", url)
    command.stamp(config, revision, purge=True)


def _alembic_downgrade(url: str, revision: str) -> None:
    from alembic import command

    config = get_alembic_config()
    config.set_main_option("sqlalchemy.url", url)
    command.downgrade(config, revision)


def _table_names(engine) -> set[str]:  # noqa: ANN001
    return set(inspect(engine).get_table_names())


@pytest.fixture
def isolated_migrations(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """把 app.migrations 的 engine 指向测试专用数据库。"""
    url, engine = _make_engine(tmp_path / "migration-test.db")
    monkeypatch.setattr(migrations, "engine", engine)
    return url, engine


def test_empty_db_upgrades_to_head(isolated_migrations) -> None:
    url, engine = isolated_migrations
    _alembic_upgrade(url, "head")
    tables = _table_names(engine)
    assert {
        "users",
        "sessions",
        "conversations",
        "messages",
        "attachments",
        "agent_runs",
        "run_events",
        "mcp_servers",
        "mcp_tools",
        "audit_logs",
        "model_configurations",
        "operation_workflows",
        "operation_workflow_steps",
        "operation_workflow_events",
        "run_artifacts",
        "conversation_context_snapshots",
        "alembic_version",
    } <= tables
    columns = {item["name"] for item in inspect(engine).get_columns("agent_runs")}
    assert {
        "queued_at",
        "started_at",
        "finished_at",
        "last_progress_at",
        "attempt_count",
    } <= columns
    assert migrations.current_revision() == migrations.head_revision()


def test_repeated_upgrade_is_idempotent(isolated_migrations) -> None:
    url, engine = isolated_migrations
    _alembic_upgrade(url, "head")
    first_tables = _table_names(engine)
    first_revision = migrations.current_revision()
    _alembic_upgrade(url, "head")
    assert _table_names(engine) == first_tables
    assert migrations.current_revision() == first_revision


def _seed_run(engine) -> None:  # noqa: ANN001
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO users (id, username, password_hash, role, is_active, created_at) "
                "VALUES ('u1', 'admin', 'x', 'admin', 1, CURRENT_TIMESTAMP)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO conversations (id, user_id, title, created_at, updated_at) "
                "VALUES ('c1', 'u1', '测试对话', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO messages (id, conversation_id, role, content, metadata_json, created_at) "
                "VALUES ('m1', 'c1', 'user', '你好', '{}', CURRENT_TIMESTAMP)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO agent_runs (id, user_id, conversation_id, user_message_id, status, "
                "runtime_state, created_at, updated_at) "
                "VALUES ('r1', 'u1', 'c1', 'm1', 'COMPLETED', '{}', "
                "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO run_events (run_id, event_type, data, created_at) "
                "VALUES ('r1', 'run.completed', '{}', CURRENT_TIMESTAMP)"
            )
        )


def _drop_version_table(engine) -> None:  # noqa: ANN001
    with engine.begin() as connection:
        connection.execute(text("DROP TABLE alembic_version"))


def test_legacy_db_stamps_baseline_and_upgrades_preserving_runs(
    isolated_migrations,
) -> None:
    """旧 create_schema 时代的库：有完整表结构、无版本记录；stamp 后升级不丢数据。"""
    url, engine = isolated_migrations
    _alembic_upgrade(url, BASELINE_REVISION)
    _seed_run(engine)
    _drop_version_table(engine)
    assert migrations.current_revision() is None

    outcome = migrations.deploy()
    assert outcome == "upgraded"
    assert migrations.check_revision() == RevisionStatus.OK

    with engine.connect() as connection:
        row = connection.execute(
            text(
                "SELECT status, attempt_count, queued_at IS NOT NULL FROM agent_runs WHERE id = 'r1'"
            )
        ).one()
    assert row[0] == "COMPLETED"
    # 终态记录回填 attempt_count=1、queued_at=created_at
    assert row[1] == 1
    assert row[2] == 1


def test_deploy_rejects_legacy_db_missing_key_tables(isolated_migrations) -> None:
    url, engine = isolated_migrations
    _alembic_upgrade(url, BASELINE_REVISION)
    with engine.begin() as connection:
        connection.execute(text("DROP TABLE run_events"))
    _drop_version_table(engine)
    with pytest.raises(RuntimeError, match="DATABASE_BASELINE_VERIFY_FAILED"):
        migrations.deploy()


def test_downgrade_0002_to_0001_and_reupgrade(isolated_migrations) -> None:
    url, engine = isolated_migrations
    _alembic_upgrade(url, "head")
    _alembic_downgrade(url, BASELINE_REVISION)
    columns = {item["name"] for item in inspect(engine).get_columns("agent_runs")}
    assert "queued_at" not in columns
    assert "attempt_count" not in columns
    assert migrations.current_revision() == BASELINE_REVISION
    _alembic_upgrade(url, "head")
    columns = {item["name"] for item in inspect(engine).get_columns("agent_runs")}
    assert "queued_at" in columns


def test_schema_ahead_detected(isolated_migrations) -> None:
    url, engine = isolated_migrations
    _alembic_upgrade(url, "head")
    with engine.begin() as connection:
        connection.execute(text("UPDATE alembic_version SET version_num = '9999_future'"))
    assert migrations.check_revision() == RevisionStatus.AHEAD


def test_check_revision_empty_and_ok(isolated_migrations) -> None:
    url, _engine = isolated_migrations
    assert migrations.check_revision() == RevisionStatus.EMPTY
    _alembic_upgrade(url, "head")
    assert migrations.check_revision() == RevisionStatus.OK


def test_known_older_revision_is_behind_not_ahead(isolated_migrations) -> None:
    url, _engine = isolated_migrations
    _alembic_upgrade(url, "0003_mcp_service_kinds")
    assert migrations.check_revision() == RevisionStatus.BEHIND
    assert migrations.deploy() == "upgraded"
    assert migrations.check_revision() == RevisionStatus.OK
