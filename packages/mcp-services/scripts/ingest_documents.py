from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from iot_diagnosis.ingestion import DOCUMENT_SOURCES, extract_file, ingest_text
from iot_diagnosis.repository import DiagnosisRepository


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest TXT, Markdown, or PDF into diagnosis RAG")
    parser.add_argument("path", type=Path)
    parser.add_argument("--source", required=True, choices=sorted(DOCUMENT_SOURCES))
    parser.add_argument("--document-id")
    parser.add_argument("--title")
    parser.add_argument("--device-type", default="ESP32")
    # 缺省走 RAG_CHUNK_SIZE / RAG_CHUNK_OVERLAP（structure_token 分块，默认 512 / 64）
    parser.add_argument("--chunk-size", type=int, default=None)
    parser.add_argument("--overlap", type=int, default=None)
    parser.add_argument(
        "--database",
        default=os.getenv("DIAGNOSIS_DATABASE_PATH", "data/iot_diagnosis.db"),
    )
    args = parser.parse_args()

    path = args.path.resolve(strict=True)
    result = ingest_text(
        DiagnosisRepository(args.database),
        source=args.source,
        document_id=args.document_id or path.stem,
        title=args.title or path.stem,
        content=extract_file(path),
        device_type=args.device_type,
        chunk_size=args.chunk_size,
        overlap=args.overlap,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
