"""外部 MySQL 镜像库基线 schema（v1.4 当前形态）。

- DDL 与原 external.py ensure_schema() 完全一致（幂等 CREATE IF NOT EXISTS）。
- 对旧库幂等补列（knowledge_document 摄取列、diagnosis_record.result_json）。
- 由 MySQLMigrationRunner 在外部存储可用时执行并记录版本。
"""

version = 1
name = "initial"

STATEMENTS = [
    """CREATE TABLE IF NOT EXISTS device (
        device_id VARCHAR(120) PRIMARY KEY, device_type VARCHAR(120) NOT NULL,
        name VARCHAR(200) NOT NULL, firmware_version VARCHAR(120), created_at VARCHAR(64) NOT NULL
    ) CHARACTER SET utf8mb4""",
    """CREATE TABLE IF NOT EXISTS device_status (
        id BIGINT AUTO_INCREMENT PRIMARY KEY, device_id VARCHAR(120) NOT NULL,
        online BOOLEAN NOT NULL, wifi_status VARCHAR(80) NOT NULL, rssi INT,
        mqtt_status VARCHAR(80) NOT NULL, temperature DOUBLE, uptime BIGINT,
        timestamp VARCHAR(64) NOT NULL, UNIQUE KEY uq_device_status_time(device_id, timestamp),
        INDEX idx_device_status_latest(device_id, timestamp)
    ) CHARACTER SET utf8mb4""",
    """CREATE TABLE IF NOT EXISTS device_log (
        id BIGINT AUTO_INCREMENT PRIMARY KEY, device_id VARCHAR(120) NOT NULL,
        level VARCHAR(32) NOT NULL, module VARCHAR(120) NOT NULL, message TEXT NOT NULL,
        timestamp VARCHAR(64) NOT NULL,
        UNIQUE KEY uq_device_log_entry(device_id, timestamp, module, message(191)),
        INDEX idx_device_log_latest(device_id, timestamp)
    ) CHARACTER SET utf8mb4""",
    """CREATE TABLE IF NOT EXISTS knowledge_document (
        source VARCHAR(120) NOT NULL, source_id VARCHAR(160) NOT NULL,
        title VARCHAR(300) NOT NULL, content TEXT NOT NULL, device_type VARCHAR(120),
        created_at VARCHAR(64) NOT NULL, document_id VARCHAR(120), chunk_index INT NOT NULL DEFAULT 0,
        PRIMARY KEY(source, source_id)
    ) CHARACTER SET utf8mb4""",
    """CREATE TABLE IF NOT EXISTS fault_case (
        fault_id VARCHAR(120) PRIMARY KEY, device_id VARCHAR(120), device_type VARCHAR(120) NOT NULL,
        fault_type VARCHAR(120) NOT NULL, fault_name VARCHAR(300) NOT NULL,
        symptoms_json JSON NOT NULL, logs_json JSON NOT NULL, cause TEXT NOT NULL,
        solution TEXT NOT NULL, verified BOOLEAN NOT NULL, verified_by VARCHAR(160) NOT NULL,
        source VARCHAR(120) NOT NULL, created_at VARCHAR(64) NOT NULL, updated_at VARCHAR(64) NOT NULL
    ) CHARACTER SET utf8mb4""",
    """CREATE TABLE IF NOT EXISTS diagnosis_record (
        diagnosis_id VARCHAR(120) PRIMARY KEY, request_id VARCHAR(120) NOT NULL,
        device_id VARCHAR(120) NOT NULL, query TEXT NOT NULL, fault_type VARCHAR(120) NOT NULL,
        fault_name VARCHAR(300) NOT NULL, cause TEXT NOT NULL, solutions_json JSON NOT NULL,
        confidence DOUBLE NOT NULL, router_type VARCHAR(80) NOT NULL,
        selected_sources_json JSON NOT NULL, retrieved_documents_json JSON NOT NULL,
        observability_json JSON NOT NULL, result_json JSON, created_at VARCHAR(64) NOT NULL
    ) CHARACTER SET utf8mb4""",
]

# 旧库补列（列已存在时跳过）
_COMPAT_COLUMNS = {
    "knowledge_document": [
        ("document_id", "VARCHAR(120) NULL"),
        ("chunk_index", "INT NOT NULL DEFAULT 0"),
    ],
    "diagnosis_record": [
        ("result_json", "JSON NULL"),
    ],
}


def upgrade(cursor) -> None:  # noqa: ANN001 - DB cursor
    for statement in STATEMENTS:
        cursor.execute(statement)
    # 旧库补列（列已存在时跳过）
    for table, columns in _COMPAT_COLUMNS.items():
        cursor.execute(f"SHOW COLUMNS FROM {table}")
        existing = {row[0] for row in cursor.fetchall()}
        for column, ddl in columns:
            if column not in existing:
                cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")
