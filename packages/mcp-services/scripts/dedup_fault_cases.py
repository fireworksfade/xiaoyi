"""按故障名称去重案例库：每组保留沉淀时间最新的一条，其余删除。

同步清理 MySQL 镜像与 Qdrant 向量（复用 repository.delete_fault_case）。
在 iot-diagnosis-mcp 容器内运行：
    python scripts/dedup_fault_cases.py
"""

from __future__ import annotations

import argparse
import json
import os

from iot_diagnosis.repository import DiagnosisRepository


def main() -> None:
    parser = argparse.ArgumentParser(description="Deduplicate fault cases by fault_name")
    parser.add_argument(
        "--database",
        default=os.getenv("DIAGNOSIS_DATABASE_PATH", "data/iot_diagnosis.db"),
    )
    args = parser.parse_args()

    repository = DiagnosisRepository(args.database)
    items: list[dict] = []
    offset = 0
    while True:
        page = repository.list_fault_cases(limit=200, offset=offset)
        items.extend(page["items"])
        offset += len(page["items"])
        if offset >= page["total"] or not page["items"]:
            break

    newest_by_name: dict[str, dict] = {}
    for item in items:
        keeper = newest_by_name.get(item["fault_name"])
        if keeper is None or item["created_at"] > keeper["created_at"]:
            newest_by_name[item["fault_name"]] = item

    removed: list[str] = []
    results = []
    for item in items:
        keeper = newest_by_name[item["fault_name"]]
        if item["fault_id"] == keeper["fault_id"]:
            continue
        outcome = repository.delete_fault_case(item["fault_id"])
        if outcome["deleted"]:
            removed.append(f"{item['fault_id']}({item['fault_name']})")
        results.append(outcome)

    print(
        json.dumps(
            {
                "total_before": len(items),
                "distinct_names": len(newest_by_name),
                "removed": len(removed),
                "removed_ids": removed,
                "remaining": repository.list_fault_cases(limit=1)["total"],
                "outbox_pending": repository.external_sync_status()["pending"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
