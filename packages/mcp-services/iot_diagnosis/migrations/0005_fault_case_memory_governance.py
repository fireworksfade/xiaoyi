"""Fault-case lifecycle, applicability, clustering and idempotent reuse feedback."""

import hashlib

version = 5
name = "fault_case_memory_governance"

_COLUMNS = {
    "lifecycle_status": "TEXT NOT NULL DEFAULT 'verified'",
    "fault_signature": "TEXT NOT NULL DEFAULT ''",
    "cluster_id": "TEXT",
    "applicability_json": "TEXT NOT NULL DEFAULT '{}'",
    "source_diagnosis_id": "TEXT",
    "source_command_id": "TEXT",
    "reuse_count": "INTEGER NOT NULL DEFAULT 0",
    "success_count": "INTEGER NOT NULL DEFAULT 0",
    "failure_count": "INTEGER NOT NULL DEFAULT 0",
    "reliability_score": "REAL NOT NULL DEFAULT 0.5",
    "last_used_at": "TEXT",
    "last_success_at": "TEXT",
    "last_failure_at": "TEXT",
    "deprecated_reason": "TEXT",
}


def upgrade(db) -> None:  # noqa: ANN001
    existing = {row[1] for row in db.execute("PRAGMA table_info(fault_case)").fetchall()}
    for column, definition in _COLUMNS.items():
        if column not in existing:
            db.execute(f"ALTER TABLE fault_case ADD COLUMN {column} {definition}")
    db.execute(
        "UPDATE fault_case SET lifecycle_status = 'verified' WHERE verified = 1 "
        "AND (lifecycle_status IS NULL OR lifecycle_status = '')"
    )
    rows = db.execute(
        "SELECT fault_id, device_type, fault_type, fault_name FROM fault_case "
        "WHERE fault_signature = ''"
    ).fetchall()
    for fault_id, device_type, fault_type, fault_name in rows:
        canonical = "|".join(
            [str(device_type).lower(), str(fault_type).lower(), str(fault_name).lower()]
        )
        digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        db.execute(
            "UPDATE fault_case SET fault_signature=?, cluster_id=? WHERE fault_id=?",
            (f"v1:{digest}", f"FCG_{digest[:16].upper()}", fault_id),
        )
    db.execute("CREATE INDEX IF NOT EXISTS ix_fault_case_lifecycle ON fault_case(lifecycle_status)")
    db.execute("CREATE INDEX IF NOT EXISTS ix_fault_case_signature ON fault_case(fault_signature)")
    db.execute("CREATE INDEX IF NOT EXISTS ix_fault_case_cluster ON fault_case(cluster_id)")
    db.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_fault_case_source_command "
        "ON fault_case(source_command_id) WHERE source_command_id IS NOT NULL"
    )
    db.execute(
        """CREATE TABLE IF NOT EXISTS fault_case_feedback (
            feedback_id TEXT PRIMARY KEY,
            fault_id TEXT NOT NULL REFERENCES fault_case(fault_id) ON DELETE CASCADE,
            diagnosis_id TEXT NOT NULL,
            command_id TEXT NOT NULL,
            device_id TEXT NOT NULL,
            outcome TEXT NOT NULL CHECK(outcome IN ('succeeded','failed','inconclusive')),
            evidence_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(fault_id, command_id)
        )"""
    )
    db.execute(
        "CREATE INDEX IF NOT EXISTS ix_fault_case_feedback_fault ON fault_case_feedback(fault_id)"
    )
    db.commit()
