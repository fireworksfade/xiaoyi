"""Control 服务基线 schema（v1.1 当前形态）。

- 从空库创建设备命令与修复提案表，列集合为历史动态补丁的最终形态
  （案例归档相关：diagnosis_id/case_id/case_status/case_attempts/case_error）。
- 对旧库幂等补列，由部署期迁移执行；Repository 构造只做版本验证。
"""

version = 1
name = "current"

_DDL = """
CREATE TABLE IF NOT EXISTS device_command (
    command_id TEXT PRIMARY KEY,
    device_id TEXT NOT NULL,
    action TEXT NOT NULL,
    parameters_json TEXT NOT NULL DEFAULT '{}',
    reason TEXT NOT NULL DEFAULT '',
    issued_by TEXT NOT NULL DEFAULT '',
    risk_level TEXT NOT NULL,
    proposal_id TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    verify_status TEXT,
    ack_json TEXT,
    diagnosis_id TEXT,
    case_id TEXT,
    case_status TEXT,
    case_attempts INTEGER NOT NULL DEFAULT 0,
    case_error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    acked_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_command_device
    ON device_command(device_id, created_at);
CREATE TABLE IF NOT EXISTS remediation_proposal (
    proposal_id TEXT PRIMARY KEY,
    device_id TEXT NOT NULL,
    action TEXT NOT NULL,
    parameters_json TEXT NOT NULL DEFAULT '{}',
    reason TEXT NOT NULL DEFAULT '',
    impact TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'pending',
    version INTEGER NOT NULL DEFAULT 1,
    expires_at TEXT NOT NULL,
    task_status TEXT,
    command_id TEXT,
    diagnosis_id TEXT,
    decided_by TEXT,
    decided_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_proposal_status
    ON remediation_proposal(status, created_at);
"""

_COMPAT_COLUMNS = {
    "device_command": {
        "diagnosis_id": "TEXT",
        "case_status": "TEXT",
        "case_id": "TEXT",
        "case_attempts": "INTEGER NOT NULL DEFAULT 0",
        "case_error": "TEXT",
    },
    "remediation_proposal": {
        "diagnosis_id": "TEXT",
    },
}


def upgrade(db) -> None:  # noqa: ANN001 - sqlite3.Connection
    db.executescript(_DDL)
    for table, columns in _COMPAT_COLUMNS.items():
        existing = {row[1] for row in db.execute(f"PRAGMA table_info({table})").fetchall()}
        for column, definition in columns.items():
            if column not in existing:
                db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
    db.commit()
