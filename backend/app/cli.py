"""小yi 后端管理 CLI。

用法（在 backend 目录下）：

    python -m app.cli upgrade      # 升级到最新迁移版本
    python -m app.cli deploy       # 部署迁移：空库升级 / 旧库 stamp 后升级
    python -m app.cli current      # 显示当前数据库版本
    python -m app.cli status       # 比较数据库版本与代码 head
"""

from __future__ import annotations

import argparse
import json
import sys

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
    parser.error(f"unknown command {args.command}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
