"""轻量级有序迁移框架（SQLite 与 MySQL）。

约束（specs WP-05）：
- 普通 Repository 构造只验证版本（空库除外）；迁移通过 scripts/migrate.py 或
  服务启动 CMD 显式执行。
- 已应用版本的 checksum 变化时拒绝启动（迁移脚本不可变）。
- 版本号在迁移内容全部执行成功后最后写入；迁移必须可安全重试（幂等 DDL）。
- SQLite backup 使用官方 backup API 写入显式目标文件。
"""

from __future__ import annotations

import hashlib
import importlib.util
import inspect
import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Sequence, cast

logger = logging.getLogger("xiaoyi.migrations")


def load_migration_module(path: Path):
    """按文件路径加载迁移模块（迁移文件名以数字开头，不能常规 import）。"""
    spec = importlib.util.spec_from_file_location(f"migration_{path.stem}", path)
    if spec is None or spec.loader is None:
        raise MigrationError("MIGRATION_LOAD_FAILED", f"无法加载迁移模块 {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_migrations_from_dir(directory: Path) -> list[Migration]:
    """按文件名排序加载目录下全部迁移模块。"""
    migrations = [
        Migration.of(load_migration_module(path))
        for path in sorted(directory.glob("0*.py"))
        if not path.name.startswith("__")
    ]
    return migrations


MIGRATIONS_TABLE_DDL = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    checksum TEXT NOT NULL,
    applied_at TEXT NOT NULL
)
"""


class MigrationError(RuntimeError):
    """迁移框架错误；code 为稳定错误码。"""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    upgrade: Callable[[sqlite3.Connection], None]
    checksum: str

    @classmethod
    def of(cls, module: object) -> "Migration":
        typed_module = cast(Any, module)
        source = inspect.getsource(typed_module)
        return cls(
            version=int(typed_module.version),
            name=str(typed_module.name),
            upgrade=typed_module.upgrade,
            checksum=hashlib.sha256(source.encode("utf-8")).hexdigest(),
        )


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class SQLiteMigrationRunner:
    def __init__(self, migrations: Sequence[Migration], *, service: str):
        ordered = sorted(migrations, key=lambda item: item.version)
        versions = [item.version for item in ordered]
        if versions != list(range(1, len(ordered) + 1)):
            raise MigrationError(
                "MIGRATION_SEQUENCE_INVALID",
                f"{service}: 迁移版本必须从 1 连续递增，当前 {versions}",
            )
        self.migrations = ordered
        self.service = service
        self.head = ordered[-1].version if ordered else 0

    def _connect(self, path: str) -> sqlite3.Connection:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(path, timeout=30)
        connection.row_factory = sqlite3.Row
        return connection

    def _applied(self, db: sqlite3.Connection) -> dict[int, str]:
        self._ensure_table(db)
        rows = db.execute("SELECT version, checksum FROM schema_migrations").fetchall()
        return {int(row["version"]): row["checksum"] for row in rows}

    @staticmethod
    def _ensure_table(db: sqlite3.Connection) -> None:
        db.execute(MIGRATIONS_TABLE_DDL)
        db.commit()

    def _verify_checksums(self, applied: dict[int, str]) -> None:
        for migration in self.migrations:
            expected = applied.get(migration.version)
            if expected and expected != migration.checksum:
                raise MigrationError(
                    "MIGRATION_CHECKSUM_MISMATCH",
                    f"{self.service}: migration {migration.version}_{migration.name} "
                    "已应用但脚本内容发生变化",
                )

    def status(self, path: str) -> dict:
        with self._connect(path) as db:
            applied = self._applied(db)
            self._verify_checksums(applied)
            pending = [item.version for item in self.migrations if item.version not in applied]
            return {
                "service": self.service,
                "applied": sorted(applied),
                "pending": pending,
                "head": self.head,
            }

    def verify(self, path: str) -> None:
        """已有库只验证：behind/ahead/checksum 不符时抛错，不修改 schema。"""
        with self._connect(path) as db:
            applied = self._applied(db)
            self._verify_checksums(applied)
            current = max(applied, default=0)
        if current < self.head:
            raise MigrationError(
                "DATABASE_SCHEMA_BEHIND",
                f"{self.service}: 数据库版本 {current} 落后于代码 head {self.head}，"
                "请先执行 python -m scripts.migrate upgrade",
            )
        if current > self.head:
            raise MigrationError(
                "DATABASE_SCHEMA_AHEAD",
                f"{self.service}: 数据库版本 {current} 高于代码 head {self.head}",
            )

    def upgrade(self, path: str) -> dict:
        """应用全部 pending 迁移；空库与新迁移按版本顺序执行。"""
        applied_summary: list[int] = []
        with self._connect(path) as db:
            applied = self._applied(db)
            self._verify_checksums(applied)
            for migration in self.migrations:
                if migration.version in applied:
                    continue
                try:
                    migration.upgrade(db)
                    db.execute(
                        "INSERT INTO schema_migrations (version, name, checksum, applied_at) "
                        "VALUES (?, ?, ?, ?)",
                        (migration.version, migration.name, migration.checksum, utc_now_iso()),
                    )
                    db.commit()
                except Exception as exc:
                    db.rollback()
                    raise MigrationError(
                        "MIGRATION_FAILED",
                        f"{self.service}: migration {migration.version}_{migration.name} 失败: {exc}",
                    ) from exc
                applied_summary.append(migration.version)
        return {"service": self.service, "applied": applied_summary, "head": self.head}

    def initialize(self, path: str) -> None:
        """Repository 构造入口：空库（无版本记录）执行迁移，否则仅验证。"""
        with self._connect(path) as db:
            applied = self._applied(db)
        if not applied:
            self.upgrade(path)
        else:
            self.verify(path)

    def backup(self, path: str, target: str) -> None:
        """SQLite 官方 backup API，写入显式目标文件。"""
        source = sqlite3.connect(path)
        destination = sqlite3.connect(target)
        try:
            with destination:
                source.backup(destination)
        finally:
            destination.close()
            source.close()
        logger.info(
            "sqlite backup written",
            extra={"event": "sqlite_backup", "service": self.service, "target": target},
        )


@dataclass(frozen=True)
class MySqlMigration:
    version: int
    name: str
    upgrade: Callable[[object], None]  # 接收 DB cursor，可执行语句并检查列
    checksum: str

    @classmethod
    def of(cls, module: object) -> "MySqlMigration":
        typed_module = cast(Any, module)
        source = inspect.getsource(typed_module)
        return cls(
            version=int(typed_module.version),
            name=str(typed_module.name),
            upgrade=typed_module.upgrade,
            checksum=hashlib.sha256(source.encode("utf-8")).hexdigest(),
        )


class MySQLMigrationRunner:
    """外部 MySQL schema 的有序迁移（DDL 幂等，版本记录在库内）。

    migration.upgrade(execute) 通过注入的 execute 逐条执行语句，
    版本行在迁移内容完成后写入；失败不记录版本，DDL 幂等可安全重试。
    """

    def __init__(self, migrations: Sequence[MySqlMigration], *, service: str):
        ordered = sorted(migrations, key=lambda item: item.version)
        versions = [item.version for item in ordered]
        if versions != list(range(1, len(ordered) + 1)):
            raise MigrationError(
                "MIGRATION_SEQUENCE_INVALID",
                f"{service}: MySQL 迁移版本必须从 1 连续递增，当前 {versions}",
            )
        self.migrations = ordered
        self.service = service

    def ensure(self, connect: Callable[[], object]) -> None:
        with cast(Any, connect()) as connection:
            cursor = connection.cursor()
            cursor.execute(MIGRATIONS_TABLE_DDL)
            connection.commit()

            cursor.execute("SELECT version, checksum FROM schema_migrations")
            rows = cursor.fetchall()
            applied = {int(row[0]): row[1] for row in rows}
            for migration in self.migrations:
                expected = applied.get(migration.version)
                if expected and expected != migration.checksum:
                    raise MigrationError(
                        "MIGRATION_CHECKSUM_MISMATCH",
                        f"{self.service}: MySQL migration "
                        f"{migration.version}_{migration.name} 已应用但内容变化",
                    )
                if expected:
                    continue
                migration.upgrade(cursor)
                cursor.execute(
                    "INSERT INTO schema_migrations (version, name, checksum, applied_at) "
                    "VALUES (%s, %s, %s, %s)",
                    (migration.version, migration.name, migration.checksum, utc_now_iso()),
                )
                connection.commit()
