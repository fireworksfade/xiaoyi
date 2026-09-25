"""Mirror fault-case memory governance fields and feedback."""

version = 2
name = "fault_case_memory_governance"

_COLUMNS = {
    "lifecycle_status": "VARCHAR(32) NOT NULL DEFAULT 'verified'",
    "fault_signature": "VARCHAR(80) NOT NULL DEFAULT ''",
    "cluster_id": "VARCHAR(80) NULL",
    "applicability_json": "JSON NULL",
    "source_diagnosis_id": "VARCHAR(120) NULL",
    "source_command_id": "VARCHAR(120) NULL",
    "reuse_count": "INT NOT NULL DEFAULT 0",
    "success_count": "INT NOT NULL DEFAULT 0",
    "failure_count": "INT NOT NULL DEFAULT 0",
    "reliability_score": "DOUBLE NOT NULL DEFAULT 0.5",
    "last_used_at": "VARCHAR(64) NULL",
    "last_success_at": "VARCHAR(64) NULL",
    "last_failure_at": "VARCHAR(64) NULL",
    "deprecated_reason": "TEXT NULL",
}


def upgrade(cursor) -> None:  # noqa: ANN001
    cursor.execute("SHOW COLUMNS FROM fault_case")
    existing = {row[0] for row in cursor.fetchall()}
    for column, ddl in _COLUMNS.items():
        if column not in existing:
            cursor.execute(f"ALTER TABLE fault_case ADD COLUMN {column} {ddl}")
    cursor.execute("SHOW INDEX FROM fault_case")
    indexes = {row[2] for row in cursor.fetchall()}
    if "uq_fault_case_source_command" not in indexes:
        cursor.execute(
            "ALTER TABLE fault_case ADD UNIQUE KEY uq_fault_case_source_command(source_command_id)"
        )
    cursor.execute(
        """CREATE TABLE IF NOT EXISTS fault_case_feedback (
            feedback_id VARCHAR(36) PRIMARY KEY,
            fault_id VARCHAR(120) NOT NULL,
            diagnosis_id VARCHAR(120) NOT NULL,
            command_id VARCHAR(120) NOT NULL,
            device_id VARCHAR(120) NOT NULL,
            outcome VARCHAR(32) NOT NULL,
            evidence_json JSON NOT NULL,
            created_at VARCHAR(64) NOT NULL,
            UNIQUE KEY uq_fault_case_feedback(fault_id, command_id),
            INDEX ix_fault_case_feedback_fault(fault_id)
        ) CHARACTER SET utf8mb4"""
    )
