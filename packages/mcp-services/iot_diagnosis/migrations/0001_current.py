"""Diagnosis 服务基线 schema（v1.4 当前形态）。

- 从空库创建全部表与索引，列集合为历史动态补丁的最终形态
  （diagnosis_record 观测列、knowledge_document 摄取列、outbox claimed_at）。
- 对旧版本建库（缺列）的存量库：幂等补列 + knowledge_document.document_id 回填，
  由 scripts/migrate.py upgrade 在部署期执行；Repository 构造只做版本验证。
"""

version = 1
name = "current"

_DDL = """
CREATE TABLE IF NOT EXISTS device (
    device_id TEXT PRIMARY KEY,
    device_type TEXT NOT NULL,
    name TEXT NOT NULL,
    firmware_version TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS device_status (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id TEXT NOT NULL REFERENCES device(device_id),
    online INTEGER NOT NULL,
    wifi_status TEXT NOT NULL,
    rssi INTEGER,
    mqtt_status TEXT NOT NULL,
    temperature REAL,
    uptime INTEGER,
    timestamp TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_device_status_latest
    ON device_status(device_id, timestamp DESC);
CREATE TABLE IF NOT EXISTS device_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id TEXT NOT NULL REFERENCES device(device_id),
    level TEXT NOT NULL,
    module TEXT NOT NULL,
    message TEXT NOT NULL,
    timestamp TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_device_log_latest
    ON device_log(device_id, timestamp DESC);
CREATE TABLE IF NOT EXISTS knowledge_document (
    source TEXT NOT NULL,
    source_id TEXT NOT NULL,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    device_type TEXT,
    document_id TEXT,
    chunk_index INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    PRIMARY KEY(source, source_id)
);
CREATE TABLE IF NOT EXISTS fault_case (
    fault_id TEXT PRIMARY KEY,
    device_id TEXT,
    device_type TEXT NOT NULL,
    fault_type TEXT NOT NULL,
    fault_name TEXT NOT NULL,
    symptoms_json TEXT NOT NULL,
    logs_json TEXT NOT NULL,
    cause TEXT NOT NULL,
    solution TEXT NOT NULL,
    verified INTEGER NOT NULL,
    verified_by TEXT NOT NULL,
    source TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS diagnosis_record (
    diagnosis_id TEXT PRIMARY KEY,
    request_id TEXT NOT NULL,
    device_id TEXT NOT NULL,
    query TEXT NOT NULL,
    fault_type TEXT NOT NULL,
    fault_name TEXT NOT NULL,
    cause TEXT NOT NULL,
    solutions_json TEXT NOT NULL,
    confidence REAL NOT NULL,
    router_type TEXT NOT NULL,
    selected_sources_json TEXT NOT NULL,
    retrieved_documents_json TEXT NOT NULL,
    result_json TEXT,
    retrieval_count INTEGER NOT NULL,
    rerank_count INTEGER NOT NULL,
    retrieval_latency_ms REAL NOT NULL DEFAULT 0,
    llm_latency_ms REAL NOT NULL DEFAULT 0,
    total_latency_ms REAL NOT NULL,
    input_tokens INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    error TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS external_sync_outbox (
    id TEXT PRIMARY KEY,
    dedupe_key TEXT NOT NULL UNIQUE,
    component TEXT NOT NULL,
    operation TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    completed_at TEXT,
    claimed_at TEXT
);
CREATE INDEX IF NOT EXISTS ix_external_sync_pending
    ON external_sync_outbox(completed_at, created_at);
"""

# 旧库补列（列已存在时跳过；与历史 _initialize 动态补丁一致）
_COMPAT_COLUMNS = {
    "diagnosis_record": {
        "retrieval_latency_ms": "REAL NOT NULL DEFAULT 0",
        "llm_latency_ms": "REAL NOT NULL DEFAULT 0",
        "input_tokens": "INTEGER NOT NULL DEFAULT 0",
        "output_tokens": "INTEGER NOT NULL DEFAULT 0",
        "error": "TEXT",
        "result_json": "TEXT",
    },
    "knowledge_document": {
        "document_id": "TEXT",
        "chunk_index": "INTEGER NOT NULL DEFAULT 0",
    },
    "external_sync_outbox": {
        "claimed_at": "TEXT",
    },
}


def upgrade(db) -> None:  # noqa: ANN001 - sqlite3.Connection
    db.executescript(_DDL)
    for table, columns in _COMPAT_COLUMNS.items():
        existing = {row[1] for row in db.execute(f"PRAGMA table_info({table})").fetchall()}
        for column, definition in columns.items():
            if column not in existing:
                db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
    db.execute(
        """UPDATE knowledge_document
        SET document_id = CASE
            WHEN instr(source_id, '#') > 0
            THEN substr(source_id, 1, instr(source_id, '#') - 1)
            ELSE source_id
        END
        WHERE document_id IS NULL OR document_id = ''"""
    )
    db.commit()
