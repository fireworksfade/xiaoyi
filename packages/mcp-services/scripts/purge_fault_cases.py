"""清空案例库：逐条删除已验证案例并同步清理 MySQL 镜像与 Qdrant 向量。

在 iot-diagnosis-mcp 容器内运行：
    python scripts/purge_fault_cases.py
"""

from __future__ import annotations

import argparse
import json
import os

from iot_diagnosis.repository import DiagnosisRepository


def main() -> None:
    parser = argparse.ArgumentParser(description="Purge all verified fault cases")
    parser.add_argument(
        "--database",
        default=os.getenv("DIAGNOSIS_DATABASE_PATH", "data/iot_diagnosis.db"),
    )
    args = parser.parse_args()

    repository = DiagnosisRepository(args.database)
    fault_ids: list[str] = []
    offset = 0
    while True:
        page = repository.list_fault_cases(limit=200, offset=offset)
        fault_ids.extend(item["fault_id"] for item in page["items"])
        offset += len(page["items"])
        if offset >= page["total"] or not page["items"]:
            break

    results = [repository.delete_fault_case(fault_id) for fault_id in fault_ids]
    deleted = sum(1 for item in results if item["deleted"])
    pending = repository.external_sync_status()["pending"]
    print(
        json.dumps(
            {
                "purged": deleted,
                "total_before": len(fault_ids),
                "remaining": repository.list_fault_cases(limit=1)["total"],
                "outbox_pending": pending,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
