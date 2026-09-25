"""外部存储显式重建 CLI。

用法：

    python -m scripts.rebuild_external --entity device_log --batch-size 500
    python -m scripts.rebuild_external --entity device_log --resume-from 12345
    python -m scripts.rebuild_external --entity knowledge_document --dry-run
    python -m scripts.rebuild_external --list
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from iot_diagnosis.rebuild import ENTITIES, RebuildService
from iot_diagnosis.repository import DiagnosisRepository


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m scripts.rebuild_external")
    parser.add_argument(
        "--entity",
        choices=ENTITIES,
        help="要重建的实体类型（device_status/device_log/knowledge_document/fault_case/diagnosis_record）",
    )
    parser.add_argument("--batch-size", type=int, default=500)
    parser.add_argument(
        "--resume-from",
        dest="resume_from",
        help="从此游标继续（或使用 job 表中的上次游标）",
    )
    parser.add_argument("--dry-run", action="store_true", help="只统计，不写外部存储")
    parser.add_argument("--source", choices=["mysql", "qdrant"], default="mysql")
    parser.add_argument(
        "--database", default=os.getenv("DIAGNOSIS_DATABASE_PATH", "data/iot_diagnosis.db")
    )
    parser.add_argument("--list", action="store_true", help="列出各实体任务状态")
    args = parser.parse_args(argv)

    if args.list:
        repository = DiagnosisRepository(args.database)
        service = RebuildService(repository)
        print(json.dumps(service.job_status(), ensure_ascii=False, indent=2))
        return 0
    if not args.entity:
        parser.error("--entity 或 --list 必填")
        return 2

    repository = DiagnosisRepository(args.database)
    service = RebuildService(repository, batch_size=args.batch_size)
    result = service.rebuild_mysql(
        args.entity,
        resume=bool(args.resume_from),
        dry_run=args.dry_run,
    )
    print(json.dumps(result, ensure_ascii=False))
    return 1 if result.get("failed") else 0


if __name__ == "__main__":
    sys.exit(main())
