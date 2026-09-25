"""知识文档摄取：结构感知 + Token 分块（Spec《RAG 检索链路升级》G1/G2）。

Document → Structure-aware Parsing → Structural Blocks → Token-aware
Chunking → Chunks。chunk 长度统一按 token 计数，默认 512 / overlap 64，
可通过 RAG_CHUNK_SIZE / RAG_CHUNK_OVERLAP 覆盖（Spec §17）。
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from pypdf import PdfReader

from iot_diagnosis.chunking import (
    Chunk,
    ChunkerConfig,
    chunk_blocks,
    parse_blocks,
    token_counter_from_env,
)
from iot_diagnosis.repository import DiagnosisRepository

DOCUMENT_SOURCES = {"mqtt_docs", "wifi_docs", "sensor_docs", "device_docs"}
DOCUMENT_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,119}$")

MIN_CHUNK_SIZE = 64
MAX_CHUNK_SIZE = 4000
MAX_CHUNK_OVERLAP = 1000


def chunker_config_from_env() -> ChunkerConfig:
    size = int(os.getenv("RAG_CHUNK_SIZE", str(ChunkerConfig.chunk_size)))
    overlap = int(os.getenv("RAG_CHUNK_OVERLAP", str(ChunkerConfig.chunk_overlap)))
    return validate_chunk_config(ChunkerConfig(chunk_size=size, chunk_overlap=overlap))


def validate_chunk_config(config: ChunkerConfig) -> ChunkerConfig:
    if not MIN_CHUNK_SIZE <= config.chunk_size <= MAX_CHUNK_SIZE:
        raise ValueError("CHUNK_SIZE_INVALID")
    if not 0 <= config.chunk_overlap <= min(MAX_CHUNK_OVERLAP, config.chunk_size - 1):
        raise ValueError("CHUNK_OVERLAP_INVALID")
    return config


def chunk_document(
    text: str,
    *,
    document_id: str,
    source: str = "",
    title: str = "",
    chunk_size: int | None = None,
    overlap: int | None = None,
) -> list[Chunk]:
    """把文档文本解析为结构块并按 token budget 分块。

    参数缺省时取 RAG_CHUNK_SIZE / RAG_CHUNK_OVERLAP 环境变量（默认 512 / 64）。
    """
    env_config = chunker_config_from_env()
    config = ChunkerConfig(
        chunk_size=chunk_size if chunk_size is not None else env_config.chunk_size,
        chunk_overlap=overlap if overlap is not None else env_config.chunk_overlap,
    )
    validate_chunk_config(config)
    if not text.strip():
        raise ValueError("DOCUMENT_EMPTY")
    blocks = parse_blocks(text)
    return chunk_blocks(
        blocks,
        document_id=document_id,
        source=source,
        title=title,
        counter=token_counter_from_env(),
        config=config,
    )


def chunk_text(
    text: str,
    chunk_size: int | None = None,
    overlap: int | None = None,
) -> list[str]:
    """兼容入口：只返回 chunk 正文列表。"""
    chunks = chunk_document(
        text,
        document_id="doc",
        chunk_size=chunk_size,
        overlap=overlap,
    )
    return [chunk.content for chunk in chunks]


def ingest_text(
    repository: DiagnosisRepository,
    *,
    source: str,
    document_id: str,
    title: str,
    content: str,
    device_type: str | None = "ESP32",
    chunk_size: int | None = None,
    overlap: int | None = None,
) -> dict[str, Any]:
    if source not in DOCUMENT_SOURCES:
        raise ValueError("INVALID_DOCUMENT_SOURCE")
    if not DOCUMENT_ID_PATTERN.fullmatch(document_id):
        raise ValueError("DOCUMENT_ID_INVALID")
    if not title.strip():
        raise ValueError("DOCUMENT_TITLE_INVALID")
    chunks = chunk_document(
        content,
        document_id=document_id,
        source=source,
        title=title.strip(),
        chunk_size=chunk_size,
        overlap=overlap,
    )
    return repository.replace_knowledge_document(
        source=source,
        document_id=document_id,
        title=title.strip(),
        chunks=[
            {
                "content": chunk.content,
                "heading": " > ".join(chunk.heading_path or []),
                "metadata_json": chunk.to_metadata_json(),
                "token_count": chunk.token_count or 0,
            }
            for chunk in chunks
        ],
        device_type=device_type,
    )


def extract_file(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".txt", ".md", ".markdown"}:
        return path.read_text(encoding="utf-8")
    if suffix == ".pdf":
        reader = PdfReader(str(path))
        return "\n\n".join(page.extract_text() or "" for page in reader.pages)
    raise ValueError("DOCUMENT_FORMAT_UNSUPPORTED")
