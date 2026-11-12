"""Ingest the official documents listed in knowledge/manifest.json.

Fetch them first with scripts/fetch_official_docs.py. Re-running replaces each document
by its document_id, so the knowledge base always matches the manifest.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from iot_diagnosis.ingestion import ingest_text
from iot_diagnosis.repository import DiagnosisRepository

KNOWLEDGE_DIR = Path(__file__).resolve().parents[1] / "knowledge"


def load_manifest() -> list[dict]:
    return json.loads((KNOWLEDGE_DIR / "manifest.json").read_text(encoding="utf-8"))["documents"]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database",
        default=os.getenv("DIAGNOSIS_DATABASE_PATH", "data/iot_diagnosis.db"),
    )
    # 缺省走 RAG_CHUNK_SIZE / RAG_CHUNK_OVERLAP（structure_token 分块，默认 512 / 64）
    parser.add_argument("--chunk-size", type=int, default=None)
    parser.add_argument("--overlap", type=int, default=None)
    parser.add_argument("documents", nargs="*", help="只导入这些 document_id")
    args = parser.parse_args()

    repository = DiagnosisRepository(args.database)
    results = []
    for entry in load_manifest():
        if args.documents and entry["document_id"] not in args.documents:
            continue
        path = KNOWLEDGE_DIR / f"{entry['document_id']}.md"
        if not path.exists():
            raise SystemExit(f"{path.name} 不存在，先运行 scripts/fetch_official_docs.py")
        result = ingest_text(
            repository,
            source=entry["source"],
            document_id=entry["document_id"],
            title=entry["title"],
            content=path.read_text(encoding="utf-8"),
            device_type="ESP32",
            chunk_size=args.chunk_size,
            overlap=args.overlap,
            category=entry["category"],
            document_type=entry["document_type"],
        )
        results.append(result)
        print(f"{entry['document_id']:22s} {result.get('chunks', result.get('chunk_count', '?'))} chunks",
              flush=True)
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
