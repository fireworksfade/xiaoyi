"""新建修复提案与设备命令必须携带非空 diagnosis_id。

保留历史 NULL 行以避免不可逆猜测或错误回填；触发器只阻止新的无关联写入，
并为精确追踪诊断闭环增加索引。
"""

version = 2
name = "require_diagnosis_id"

_DDL = """
CREATE INDEX IF NOT EXISTS idx_command_diagnosis
    ON device_command(diagnosis_id);
CREATE INDEX IF NOT EXISTS idx_proposal_diagnosis
    ON remediation_proposal(diagnosis_id);

CREATE TRIGGER IF NOT EXISTS trg_device_command_require_diagnosis_insert
BEFORE INSERT ON device_command
WHEN NEW.diagnosis_id IS NULL OR trim(NEW.diagnosis_id) = ''
BEGIN
    SELECT RAISE(ABORT, 'DIAGNOSIS_ID_REQUIRED');
END;

CREATE TRIGGER IF NOT EXISTS trg_device_command_require_diagnosis_update
BEFORE UPDATE OF diagnosis_id ON device_command
WHEN NEW.diagnosis_id IS NULL OR trim(NEW.diagnosis_id) = ''
BEGIN
    SELECT RAISE(ABORT, 'DIAGNOSIS_ID_REQUIRED');
END;

CREATE TRIGGER IF NOT EXISTS trg_remediation_proposal_require_diagnosis_insert
BEFORE INSERT ON remediation_proposal
WHEN NEW.diagnosis_id IS NULL OR trim(NEW.diagnosis_id) = ''
BEGIN
    SELECT RAISE(ABORT, 'DIAGNOSIS_ID_REQUIRED');
END;

CREATE TRIGGER IF NOT EXISTS trg_remediation_proposal_require_diagnosis_update
BEFORE UPDATE OF diagnosis_id ON remediation_proposal
WHEN NEW.diagnosis_id IS NULL OR trim(NEW.diagnosis_id) = ''
BEGIN
    SELECT RAISE(ABORT, 'DIAGNOSIS_ID_REQUIRED');
END;
"""


def upgrade(db) -> None:  # noqa: ANN001 - sqlite3.Connection
    db.executescript(_DDL)
    db.commit()
