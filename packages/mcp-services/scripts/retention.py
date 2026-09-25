"""数据保留 CLI。

用法：

    python -m scripts.retention --dry-run                 # 候选统计，不删除
    python -m scripts.retention --execute                 # 按配置执行（需 DELETE_ENABLED=true）
    python -m scripts.retention --purge-legacy-status     # 显式清理 legacy 状态表
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from iot_diagnosis.retention import (
    RetentionService,
    purge_legacy_status,
    report_to_json,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m scripts.retention")
    parser.add_argument(
        "--database",
        default=os.getenv("DIAGNOSIS_DATABASE_PATH", "data/iot_diagnosis.db"),
    )
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--dry-run", action="store_true", help="只统计候选，不删除")
    modes.add_argument("--execute", action="store_true", help="执行清理（受配置开关限制）")
    modes.add_argument(
        "--purge-legacy-status",
        action="store_true",
        help="显式清理 device_status_legacy（先去重观察，再执行）",
    )
    parser.add_argument(
        "--legacy-apply",
        action="store_true",
        help="与 --purge-legacy-status 连用：真正删除（默认 dry-run）",
    )
    args = parser.parse_args(argv)

    if args.purge_legacy_status:
        report = purge_legacy_status(args.database, dry_run=not args.legacy_apply)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    service = RetentionService(args.database)
    report = service.run(force_dry_run=args.dry_run)
    print(report_to_json(report))
    if args.execute and report.dry_run:
        print(
            json.dumps(
                {"warning": "DIAGNOSIS_RETENTION_DELETE_ENABLED=false，本次未删除任何数据"},
                ensure_ascii=False,
            )
        )
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
