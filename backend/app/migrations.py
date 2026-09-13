"""数据库迁移运行时辅助。

生产部署必须先执行迁移（`python -m app.cli deploy`）再启动应用；
应用启动只校验版本，不边接收请求边修改 schema。
"""

from __future__ import annotations

import enum
import logging
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text

from app.config import get_settings
from app.db import engine

logger = logging.getLogger("xiaoyi.migrations")

BASELINE_REVISION = "0001_current_schema"

# 已有库 stamp 0001 前必须验证的关键表（旧 create_schema 时代的库）
_BASELINE_KEY_TABLES = {
    "users",
    "sessions",
    "conversations",
    "messages",
    "agent_runs",
    "run_events",
    "mcp_servers",
    "mcp_tools",
}
_BASELINE_KEY_COLUMNS = {
    "conversations": "deleted_at",
    "messages": "client_message_id",
}


class RevisionStatus(str, enum.Enum):
    OK = "ok"
    EMPTY = "empty"
    BEHIND = "behind"
    AHEAD = "ahead"


def get_alembic_config() -> Config:
    root = Path(__file__).resolve().parent.parent
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "migrations"))
    # 与应用共享同一个数据库（测试中可整体替换 engine）
    config.set_main_option("sqlalchemy.url", engine.url.render_as_string(hide_password=False))
    return config


def upgrade_to_head() -> None:
    get_settings().ensure_local_paths()
    command.upgrade(get_alembic_config(), "head")


def stamp(revision: str) -> None:
    command.stamp(get_alembic_config(), revision, purge=True)


def _revision_table_exists(connection) -> bool:  # noqa: ANN001
    return "alembic_version" in inspect(connection).get_table_names()


def current_revision() -> str | None:
    with engine.connect() as connection:
        if not _revision_table_exists(connection):
            return None
        return connection.execute(text("SELECT version_num FROM alembic_version")).scalar()


def head_revision() -> str:
    from alembic.script import ScriptDirectory

    script = ScriptDirectory.from_config(get_alembic_config())
    heads = script.get_heads()
    if not heads:
        raise RuntimeError("NO_MIGRATION_SCRIPTS")
    return heads[0]


def check_revision() -> RevisionStatus:
    """比较数据库版本与代码支持的版本。"""
    current = current_revision()
    if current is None:
        return RevisionStatus.EMPTY
    head = head_revision()
    if current == head:
        return RevisionStatus.OK
    return RevisionStatus.AHEAD if _is_ahead(current, head) else RevisionStatus.BEHIND


def _is_ahead(current: str, head: str) -> bool:
    """判断 current 是否在 head 之后；未知版本（不在脚本目录中）视为 ahead。"""
    from alembic.script import ScriptDirectory

    script = ScriptDirectory.from_config(get_alembic_config())
    revisions = [rev.revision for rev in script.walk_revisions()]
    if current not in revisions:
        return True
    return revisions.index(current) > revisions.index(head)


def verify_baseline_schema() -> list[str]:
    """已有库 stamp 0001 前的关键表/列检查，返回缺失项。"""
    missing: list[str] = []
    with engine.connect() as connection:
        inspector = inspect(connection)
        tables = set(inspector.get_table_names())
        for table in _BASELINE_KEY_TABLES:
            if table not in tables:
                missing.append(f"table:{table}")
        for table, column in _BASELINE_KEY_COLUMNS.items():
            if table in tables and column not in {
                item["name"] for item in inspector.get_columns(table)
            }:
                missing.append(f"column:{table}.{column}")
    return missing


def deploy() -> str:
    """部署入口迁移：空库 upgrade；旧库先 stamp 0001 再 upgrade；已有版本直接 upgrade。"""
    get_settings().ensure_local_paths()
    status = check_revision()
    if status == RevisionStatus.EMPTY:
        with engine.connect() as connection:
            has_tables = bool(inspect(connection).get_table_names())
        if has_tables:
            missing = verify_baseline_schema()
            if missing:
                raise RuntimeError("DATABASE_BASELINE_VERIFY_FAILED: missing " + ", ".join(missing))
            logger.info("existing pre-migration database; stamping %s", BASELINE_REVISION)
            stamp(BASELINE_REVISION)
        upgrade_to_head()
        return "upgraded"
    if status == RevisionStatus.OK:
        return "up-to-date"
    if status == RevisionStatus.AHEAD:
        raise RuntimeError(
            f"DATABASE_SCHEMA_AHEAD: database revision {current_revision()} is newer than code head {head_revision()}"
        )
    upgrade_to_head()
    return "upgraded"
