"""Rebuild local fallback indexes without sending documents to the primary API."""

from __future__ import annotations

import argparse
import json
import os

from iot_diagnosis.repository import DiagnosisRepository


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", choices=("local", "hash", "all"), default="all")
    parser.add_argument("--batch-size", type=int, default=16)
    args = parser.parse_args()
    if not 1 <= args.batch_size <= 100:
        parser.error("batch-size must be between 1 and 100")
    try:
        repository = DiagnosisRepository(
            os.getenv("DIAGNOSIS_DATABASE_PATH", "data/iot_diagnosis.db"), auto_migrate=False
        )
        stores = {
            "local": repository.external.qdrant_local_fallback,
            "hash": repository.external.qdrant_fallback,
        }
        selected = [args.target] if args.target != "all" else ["local", "hash"]
        documents = repository.knowledge_documents(
            ["mqtt_docs", "wifi_docs", "sensor_docs", "device_docs"]
        )
        items = [repository._knowledge_vector_document(document) for document in documents]
        for target in selected:
            store = stores[target]
            if store is None:
                raise RuntimeError("FALLBACK_STORE_NOT_CONFIGURED")
            indexed = 0
            for offset in range(0, len(items), args.batch_size):
                batch = items[offset : offset + args.batch_size]
                if not store.upsert_many(batch):
                    raise RuntimeError("FALLBACK_INDEX_WRITE_FAILED")
                indexed += len(batch)
                if indexed % 80 == 0 or indexed == len(items):
                    print(
                        json.dumps({"target": target, "indexed": indexed, "total": len(items)}),
                        flush=True,
                    )
            print(
                json.dumps(
                    {
                        "target": target,
                        "collection": store.collection,
                        "dimensions": store.dimensions,
                        "indexed": indexed,
                        "status": "complete",
                    }
                ),
                flush=True,
            )
        return 0
    except Exception as exc:
        print(json.dumps({"status": "failed", "error": type(exc).__name__}), flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
