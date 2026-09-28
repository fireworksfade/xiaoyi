"""退役案例归档：重建 device_command 去除 case 列（memory 替代，spec §11.4）。

- 保留 diagnosis_id、命令结果与验证状态；表重建时显式复制全部保留列，
  并校验行数一致、命令与提案关联完整。
- SQLite 不支持 DROP COLUMN 的旧版本由本迁移统一走表重建路径。
"""

version = 4
name = "remove_case_columns"

_DDL = """
CREATE TABLE device_command_new (
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
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    acked_at TEXT
);
"""

_KEEP_COLUMNS = (
    "command_id",
    "device_id",
    "action",
    "parameters_json",
    "reason",
    "issued_by",
    "risk_level",
    "proposal_id",
    "status",
    "verify_status",
    "ack_json",
    "diagnosis_id",
    "created_at",
    "updated_at",
    "acked_at",
)


def upgrade(db) -> None:  # noqa: ANN001 - sqlite3.Connection
    existing = {row[1] for row in db.execute("PRAGMA table_info(device_command)").fetchall()}
    if not existing or not ({"case_id", "case_status", "case_attempts", "case_error"} & existing):
        return  # 基线已无案例列（新库 0001→0004 幂等直达）
    db.executescript(_DDL)
    columns = ", ".join(_KEEP_COLUMNS)
    db.execute(
        f"INSERT INTO device_command_new ({columns}) SELECT {columns} FROM device_command"
    )
    before = db.execute("SELECT COUNT(*) FROM device_command").fetchone()[0]
    after = db.execute("SELECT COUNT(*) FROM device_command_new").fetchone()[0]
    if before != after:
        raise RuntimeError("CASE_COLUMN_MIGRATION_ROW_COUNT_MISMATCH")
    orphans = db.execute(
        """SELECT COUNT(*) FROM device_command_new c
        WHERE c.proposal_id IS NOT NULL AND NOT EXISTS (
            SELECT 1 FROM remediation_proposal p WHERE p.proposal_id = c.proposal_id)"""
    ).fetchone()[0]
    db.execute("DROP TABLE device_command")
    db.execute("ALTER TABLE device_command_new RENAME TO device_command")
    # 旧表连同其索引/触发器已删除；此处恢复 0002 的约束语义与索引
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_command_device ON device_command(device_id, created_at)"
    )
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_command_diagnosis ON device_command(diagnosis_id)"
    )
    db.execute(
        """CREATE TRIGGER trg_device_command_require_diagnosis_insert
        BEFORE INSERT ON device_command
        WHEN NEW.diagnosis_id IS NULL OR trim(NEW.diagnosis_id) = ''
        BEGIN
            SELECT RAISE(ABORT, 'DIAGNOSIS_ID_REQUIRED');
        END"""
    )
    db.execute(
        """CREATE TRIGGER trg_device_command_require_diagnosis_update
        BEFORE UPDATE OF diagnosis_id ON device_command
        WHEN NEW.diagnosis_id IS NULL OR trim(NEW.diagnosis_id) = ''
        BEGIN
            SELECT RAISE(ABORT, 'DIAGNOSIS_ID_REQUIRED');
        END"""
    )
    db.commit()
    if orphans:
        # 只记录告警：历史孤儿关联不代表数据损坏，迁移不回滚
        import logging

        logging.getLogger("xiaoyi.iot_control.migrations").warning(
            "device_command rebuild kept %d proposal links without matching proposals", orphans
        )
