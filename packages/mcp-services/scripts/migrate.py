"""MCP 服务数据库迁移 CLI。

用法（mcp-services 目录下，或容器内 PYTHONPATH=/app）：

    python -m scripts.migrate status --service diagnosis
    python -m scripts.migrate upgrade --service diagnosis [--dry-run]
    python -m scripts.migrate upgrade --service control
    python -m scripts.migrate backup --service diagnosis --target /tmp/backup.db
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from common.migrations import (
    MigrationError,
    SQLiteMigrationRunner,
    load_migrations_from_dir,
)

_ROOT = Path(__file__).resolve().parent.parent

_MIGRATION_DIRS = {
    "diagnosis": _ROOT / "iot_diagnosis" / "migrations",
    "control": _ROOT / "iot_control" / "migrations",
}

_DATABASE_PATHS = {
    "diagnosis": ("DIAGNOSIS_DATABASE_PATH", "data/iot_diagnosis.db"),
    "control": ("CONTROL_DATABASE_PATH", "data/iot_control.db"),
}


def get_runner(service: str) -> SQLiteMigrationRunner:
    migrations = load_migrations_from_dir(_MIGRATION_DIRS[service])
    return SQLiteMigrationRunner(migrations, service=service)


def database_path(service: str) -> str:
    env_name, default = _DATABASE_PATHS[service]
    return os.getenv(env_name, default)


def _normalize_argv(argv: list[str]) -> list[str]:
    """Allow ``--service`` before or after the migration subcommand."""
    try:
        service_index = argv.index("--service")
    except ValueError:
        return argv
    if service_index == 0 or service_index + 1 >= len(argv):
        return argv
    service_args = argv[service_index : service_index + 2]
    return service_args + argv[:service_index] + argv[service_index + 2 :]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m scripts.migrate")
    parser.add_argument("--service", required=True, choices=["diagnosis", "control"])
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("status", help="查看已应用/待应用迁移版本")
    upgrade_parser = subparsers.add_parser("upgrade", help="应用全部待应用迁移")
    upgrade_parser.add_argument("--dry-run", action="store_true", help="只显示将应用的迁移")
    backup_parser = subparsers.add_parser("backup", help="SQLite 官方 backup API 备份")
    backup_parser.add_argument("--target", required=True)
    raw_argv = list(sys.argv[1:] if argv is None else argv)
    args = parser.parse_args(_normalize_argv(raw_argv))

    runner = get_runner(args.service)
    try:
        if args.command == "status":
            result = runner.status(database_path(args.service))
        elif args.command == "upgrade":
            if args.dry_run:
                result = {"dry_run": True, **runner.status(database_path(args.service))}
            else:
                result = runner.upgrade(database_path(args.service))
        elif args.command == "backup":
            runner.backup(database_path(args.service), args.target)
            result = {"service": args.service, "backup": args.target}
        else:  # pragma: no cover - argparse 保证
            parser.error(f"unknown command {args.command}")
            return 2
    except MigrationError as exc:
        print(
            json.dumps({"error": exc.code, "message": str(exc)}, ensure_ascii=False),
            file=sys.stderr,
        )
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
