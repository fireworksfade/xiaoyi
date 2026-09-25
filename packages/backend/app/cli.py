"""小yi 后端管理 CLI。

用法（在 backend 目录下）：

    python -m app.cli upgrade      # 升级到最新迁移版本
    python -m app.cli deploy       # 部署迁移：空库升级 / 旧库 stamp 后升级
    python -m app.cli current      # 显示当前数据库版本
    python -m app.cli status       # 比较数据库版本与代码 head
    python -m app.cli retention    # 数据保留统计（默认 dry-run）
    python -m app.cli retention --execute   # 实际执行清理（需 RETENTION_DELETE_ENABLED）
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

from app.config import get_settings
from app.migrations import (
    RevisionStatus,
    check_revision,
    current_revision,
    deploy,
    head_revision,
    upgrade_to_head,
)


def _print(message: object) -> None:
    print(json.dumps(message, ensure_ascii=False, default=str))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("upgrade", help="升级数据库到最新迁移版本")
    subparsers.add_parser("deploy", help="部署迁移（空库升级，旧库先 stamp 基线）")
    subparsers.add_parser("current", help="显示当前数据库迁移版本")
    subparsers.add_parser("status", help="比较数据库版本与代码 head")
    retention_parser = subparsers.add_parser(
        "retention", help="数据保留：附件/Session/事件压缩统计或清理"
    )
    retention_parser.add_argument(
        "--execute",
        action="store_true",
        help="实际删除（默认 dry-run；仍需 RETENTION_DELETE_ENABLED=true）",
    )
    args = parser.parse_args(argv)

    if args.command == "upgrade":
        upgrade_to_head()
        _print({"action": "upgrade", "revision": current_revision()})
        return 0
    if args.command == "deploy":
        outcome = deploy()
        _print({"action": "deploy", "outcome": outcome, "revision": current_revision()})
        return 0
    if args.command == "current":
        _print({"revision": current_revision(), "head": head_revision()})
        return 0
    if args.command == "status":
        status = check_revision()
        _print(
            {
                "status": status.value,
                "revision": current_revision(),
                "head": head_revision(),
            }
        )
        return 0 if status in (RevisionStatus.OK, RevisionStatus.EMPTY) else 1
    if args.command == "retention":
        from app.services.retention import run_retention

        settings = get_settings()
        delete_enabled = args.execute and settings.retention_delete_enabled
        report = asyncio.run(run_retention(delete_enabled=delete_enabled, settings=settings))
        _print({"action": "retention", "executed": delete_enabled, "report": report})
        if args.execute and not settings.retention_delete_enabled:
            _print(
                {
                    "warning": "RETENTION_DELETE_ENABLED=false，本次仍为 dry-run；"
                    "开启后再次执行才会删除"
                }
            )
        return 0
    parser.error(f"unknown command {args.command}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
