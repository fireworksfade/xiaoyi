"""Chunking Tests（Spec《RAG 检索链路升级》§40 Chunking Tests、AC1-AC6）。"""

from iot_diagnosis.chunking import (
    ChunkerConfig,
    chunk_blocks,
    parse_blocks,
)
from iot_diagnosis.chunking.token_counter import HeuristicTokenCounter
from iot_diagnosis.ingestion import chunk_document

COUNTER = HeuristicTokenCounter()


def _chunk(text: str, **overrides) -> list:
    config = ChunkerConfig(**{"chunk_size": 512, "chunk_overlap": 64, **overrides})
    return chunk_blocks(
        parse_blocks(text),
        document_id="doc",
        title="Doc",
        counter=COUNTER,
        config=config,
    )


def test_heading_inheritance_records_hierarchy() -> None:
    text = "# MQTT\n## Connection\n### Timeout\n设备频繁断开连接。\n"
    blocks = parse_blocks(text)
    paragraph = blocks[-1]
    assert paragraph.block_type == "paragraph"
    assert paragraph.heading_path == ["MQTT", "Connection", "Timeout"]

    chunks = _chunk(text)
    assert chunks[0].heading_path == ["MQTT", "Connection", "Timeout"]
    assert chunks[0].title == "MQTT"
    assert chunks[0].metadata["heading_injected"] is True


def test_heading_context_is_injected_into_embedding_content() -> None:
    text = "# MQTT\n\n## Keep Alive\n\n设备频繁断开连接。\n"
    chunks = _chunk(text)
    assert len(chunks) == 1
    assert chunks[0].content.startswith("# MQTT\n## Keep Alive")
    assert "设备频繁断开连接" in chunks[0].content
    assert chunks[0].heading_path == ["MQTT", "Keep Alive"]


def test_code_block_preserved_atomically() -> None:
    code_lines = [f"line_{index} = {index}" for index in range(20)]
    text = "```python\n" + "\n".join(code_lines) + "\n```\n"
    chunks = _chunk(text)
    assert len(chunks) == 1
    assert chunks[0].block_type == "code"
    assert chunks[0].metadata["language"] == "python"
    assert chunks[0].content.count("```") == 2
    for line in code_lines:
        assert line in chunks[0].content


def test_log_lines_keep_line_boundaries() -> None:
    text = (
        "### 日志\n\n"
        "2026-09-01 12:00:00 ERROR connection timeout\n"
        "2026-09-01 12:00:01 INFO reconnecting\n"
        "2026-09-01 12:00:02 ERROR reconnect failed\n"
    )
    chunks = _chunk(text)
    assert len(chunks) == 1
    content = chunks[0].content
    assert chunks[0].block_type == "log"
    # 每条日志必须保持独立行，不得被压平成单行
    assert "2026-09-01 12:00:00 ERROR connection timeout\n" in content
    assert "2026-09-01 12:00:02 ERROR reconnect failed" in content
    assert "timeout 2026" not in content


def test_numbered_steps_split_at_step_boundary() -> None:
    steps = "\n".join(f"{index}. 排查步骤说明内容步骤 {index}" * 4 for index in range(1, 13))
    text = f"### 排查步骤\n\n{steps}\n"
    chunks = _chunk(text, chunk_size=128)
    assert len(chunks) > 1
    for chunk in chunks:
        for line in chunk.content.split("\n"):
            if not line.strip():
                continue
            # 每个步骤必须完整：不允许在步骤句中截断
            assert line.startswith("#") or "步骤" in line
    # 步骤不丢失（overlap 造成的重复允许存在）
    unique_steps = {
        line
        for chunk in chunks
        for line in chunk.content.split("\n")
        if line[:2].rstrip(".").isdigit()
    }
    assert len(unique_steps) == 12


def test_table_preserved_and_split_by_rows_with_header() -> None:
    header = "| 参数 | 默认值 | 说明 |"
    separator = "| ---- | ------ | ---- |"
    rows = [f"| key_{index} | {index} | 参数说明内容 {index} |" for index in range(30)]
    text = "\n".join([header, separator, *rows]) + "\n"
    chunks = _chunk(text, chunk_size=160)
    assert len(chunks) > 1
    for chunk in chunks:
        assert chunk.block_type == "table"
        # 每个分片必须重复表头（Spec §12），overlap 行插在表头之后
        lines = chunk.content.split("\n")
        assert lines[0] == header and lines[1] == separator
    # 行不丢失（overlap 造成的重复行允许存在）
    seen = set()
    for chunk in chunks:
        for line in chunk.content.split("\n"):
            if line.startswith("| key_"):
                seen.add(line)
    assert len(seen) == 30


def test_token_limit_and_metadata() -> None:
    paragraph = "这是一段用于测试 token 预算的中文段落内容，" * 60
    chunks = _chunk(paragraph, chunk_size=256, chunk_overlap=32)
    assert len(chunks) > 1
    for chunk in chunks:
        assert chunk.token_count <= 256
        assert chunk.token_count == COUNTER.count(chunk.content)
        assert chunk.block_type == "paragraph"
    # chunk_index 连续
    assert [chunk.chunk_index for chunk in chunks] == list(range(len(chunks)))


def test_overlap_prefers_complete_structures() -> None:
    lines = [f"2026-09-01 12:00:{index:02d} ERROR 日志行内容 {index}" for index in range(40)]
    text = "\n".join(lines) + "\n"
    chunks = _chunk(text, chunk_size=120, chunk_overlap=40)
    assert len(chunks) > 1
    for previous, current in zip(chunks, chunks[1:], strict=False):
        previous_lines = [line for line in previous.content.split("\n") if line.strip()]
        current_lines = [line for line in current.content.split("\n") if line.strip()]
        # 相邻分片之间应存在完整的重叠日志行（Spec §16）
        overlap = set(previous_lines) & set(current_lines)
        assert overlap


def test_very_long_code_block_split_keeps_fences_and_metadata() -> None:
    code_lines = [f"value_{index:03d} = compute({index})" for index in range(200)]
    text = "```python\n" + "\n".join(code_lines) + "\n```\n"
    chunks = _chunk(text, chunk_size=200)
    assert len(chunks) > 1
    for index, chunk in enumerate(chunks):
        assert chunk.metadata["language"] == "python"
        assert chunk.metadata["block_sequence"] == index + 1
        assert chunk.metadata["block_total"] == len(chunks)
        assert chunk.content.startswith("```python\n")
        assert chunk.content.rstrip().endswith("```")
    covered = "".join(chunk.content for chunk in chunks)
    for line in code_lines:
        assert line in covered


def test_chinese_english_mixed_document() -> None:
    text = (
        "# 设备诊断 Device Diagnosis\n\n"
        "MQTT_KEEPALIVE 超时会导致设备离线。The keep alive timeout causes offline devices.\n\n"
        "## 排查 Troubleshooting\n\n"
        "1. 检查 check broker 配置\n"
        "2. 验证 verify 网络 network 延迟\n"
    )
    chunks = _chunk(text)
    assert chunks
    joined = "\n".join(chunk.content for chunk in chunks)
    assert "MQTT_KEEPALIVE" in joined
    assert "The keep alive timeout causes offline devices." in joined
    assert "2. 验证 verify 网络 network 延迟" in joined


def test_ingest_chunk_document_defaults_and_validation() -> None:
    chunks = chunk_document("段落一。\n\n段落二。", document_id="d")
    assert len(chunks) == 1
    assert chunks[0].token_count == COUNTER.count(chunks[0].content)

    try:
        chunk_document("x", document_id="d", chunk_size=10)
    except ValueError as exc:
        assert str(exc) == "CHUNK_SIZE_INVALID"
    else:
        raise AssertionError("expected CHUNK_SIZE_INVALID")

    try:
        chunk_document("x", document_id="d", chunk_size=128, overlap=200)
    except ValueError as exc:
        assert str(exc) == "CHUNK_OVERLAP_INVALID"
    else:
        raise AssertionError("expected CHUNK_OVERLAP_INVALID")

    try:
        chunk_document("   \n", document_id="d")
    except ValueError as exc:
        assert str(exc) == "DOCUMENT_EMPTY"
    else:
        raise AssertionError("expected DOCUMENT_EMPTY")


def test_chunk_document_reads_env_config(monkeypatch) -> None:
    # Spec §17：缺省参数必须走 RAG_CHUNK_SIZE / RAG_CHUNK_OVERLAP
    monkeypatch.setenv("RAG_CHUNK_SIZE", "96")
    monkeypatch.setenv("RAG_CHUNK_OVERLAP", "8")
    paragraph = "这是一段用于验证环境变量分块配置的中文内容，" * 20
    chunks = chunk_document(paragraph, document_id="d")
    assert len(chunks) > 1
    assert all(chunk.token_count <= 96 for chunk in chunks)

    # 显式参数优先于环境变量
    explicit = chunk_document(paragraph, document_id="d", chunk_size=512, overlap=64)
    assert len(explicit) < len(chunks)
