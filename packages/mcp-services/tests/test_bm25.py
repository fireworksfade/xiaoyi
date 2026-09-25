"""BM25 Tests（Spec《RAG 检索链路升级》§20-§22、§40 BM25 Tests、AC10/AC11）。

重点验证精确技术词（错误码、命令、型号、配置键）相对 Dense 的补充价值，
以及 bm25() 负分数语义的封装。
"""

import sqlite3

from iot_diagnosis.repository import DiagnosisRepository
from iot_diagnosis.retrieval.bm25 import build_match_query, expand_index_text, search_bm25

TECH_DOC = """# ESP32 MQTT 故障排查手册

## 认证错误

Broker 返回 unauthorized 时检查 mosquitto.conf 的 password_file 配置，
使用 mosquitto_passwd 重新生成凭据。

## 网络错误

```
ERR_CONNECTION_RESET
AT+CGATT=1
```

## Keep Alive

MQTT_KEEPALIVE 超时通常是心跳间隔配置过大或网络 RTT 过高。
"""

COMMAND_DOC = """# AT 指令参考

型号 MODEL-X200 固件使用 AT+CGATT 激活 PDP 上下文，
错误码 0x1F 表示 SIM 未就绪。
"""


def _make_repository(tmp_path) -> DiagnosisRepository:
    return DiagnosisRepository(str(tmp_path / "diagnosis.db"))


def test_expand_index_text_splits_technical_tokens_and_cjk_bigrams() -> None:
    expanded = expand_index_text("ERR_CONNECTION_RESET 与 mosquitto.conf 超时")
    tokens = expanded.split(" ")
    assert "ERR" in tokens and "CONNECTION" in tokens and "RESET" in tokens
    assert "mosquitto" in tokens and "conf" in tokens
    assert "超时" in tokens


def test_build_match_query_keeps_phrase_adjacency_and_cjk_or() -> None:
    query = build_match_query("ERR_CONNECTION_RESET 超时")
    assert '"ERR CONNECTION RESET"' in query
    assert '"超时"' in query
    assert " OR " in query


def test_bm25_wraps_negative_fts5_scores_as_positive(tmp_path) -> None:
    repository = _make_repository(tmp_path)
    with repository._connect() as db:
        repository._sync_fts(
            db,
            delete=None,
            rows=[
                {
                    "chunk_id": "doc#0000",
                    "document_id": "doc",
                    "source": "mqtt_docs",
                    "title": "技术手册",
                    "heading": "",
                    "content": TECH_DOC,
                }
            ],
        )
        hits = search_bm25(db, "ERR_CONNECTION_RESET", ["mqtt_docs"], 5)
    assert hits
    assert hits[0]["id"] == "doc#0000"
    # Spec §20：封装为正分数，越大越相关
    assert hits[0]["score"] > 0


def test_bm25_finds_precise_technical_words(tmp_path) -> None:
    repository = _make_repository(tmp_path)
    with repository._connect() as db:
        repository._sync_fts(
            db,
            delete=None,
            rows=[
                {
                    "chunk_id": "mqtt#0000",
                    "document_id": "mqtt",
                    "source": "mqtt_docs",
                    "title": "MQTT 手册",
                    "heading": "认证错误",
                    "content": TECH_DOC,
                },
                {
                    "chunk_id": "at#0000",
                    "document_id": "at",
                    "source": "device_docs",
                    "title": "AT 指令",
                    "heading": "",
                    "content": COMMAND_DOC,
                },
            ],
        )
        cases = {
            "ERR_CONNECTION_RESET": "mqtt#0000",
            "MQTT_KEEPALIVE": "mqtt#0000",
            "mosquitto.conf": "mqtt#0000",
            "AT+CGATT": "at#0000",
            "MODEL-X200": "at#0000",
            "0x1F": "at#0000",
            "password_file": "mqtt#0000",
            "mosquitto_passwd": "mqtt#0000",
        }
        for query, expected in cases.items():
            hits = search_bm25(db, query, ["mqtt_docs", "device_docs"], 5)
            assert hits, f"BM25 未命中: {query}"
            assert hits[0]["id"] == expected, f"{query} -> {[h['id'] for h in hits]}"

        # 中文短语：二元组展开后可命中（Spec §40 中英文覆盖）
        hits = search_bm25(db, "心跳间隔配置过大", ["mqtt_docs"], 5)
        assert hits and hits[0]["id"] == "mqtt#0000"

        # 来源过滤生效：MODEL-X200 仅存在于 device_docs
        hits = search_bm25(db, "MODEL-X200", ["mqtt_docs"], 5)
        assert hits == []


def test_bm25_ranking_prefers_more_matching_terms(tmp_path) -> None:
    repository = _make_repository(tmp_path)
    with repository._connect() as db:
        repository._sync_fts(
            db,
            delete=None,
            rows=[
                {
                    "chunk_id": "weak#0000",
                    "document_id": "weak",
                    "source": "mqtt_docs",
                    "title": "t",
                    "heading": "",
                    "content": "keep alive 相关背景介绍",
                },
                {
                    "chunk_id": "strong#0000",
                    "document_id": "strong",
                    "source": "mqtt_docs",
                    "title": "t2",
                    "heading": "",
                    "content": "keep alive timeout 心跳超时排查",
                },
            ],
        )
        hits = search_bm25(db, "keep alive timeout", ["mqtt_docs"], 5)
    assert hits[0]["id"] == "strong#0000"


def test_bm25_search_via_repository_rehydrates_content(tmp_path) -> None:
    repository = _make_repository(tmp_path)
    repository.replace_knowledge_document(
        source="mqtt_docs",
        document_id="tech",
        title="技术手册",
        chunks=[
            {"content": TECH_DOC, "heading": "认证错误", "metadata_json": "{}", "token_count": 50}
        ],
        device_type="ESP32",
    )
    hits = repository.bm25_search("mosquitto.conf password_file", ["mqtt_docs"], 5)
    assert hits
    assert hits[0]["content"].startswith("# ESP32 MQTT 故障排查手册")
    assert hits[0]["title"].startswith("技术手册")
    assert repository.bm25_available() is True


def test_search_bm25_degrades_gracefully_without_fts_table(tmp_path) -> None:
    db = sqlite3.connect(str(tmp_path / "bare.db"))
    db.row_factory = sqlite3.Row
    assert search_bm25(db, "anything", ["mqtt_docs"], 5) == []
    db.close()
