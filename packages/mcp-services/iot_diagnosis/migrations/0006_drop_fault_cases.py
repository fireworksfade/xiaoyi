"""退役旧故障案例库（memory 替代，spec §11.4）。

- 删除 fault_case / fault_case_feedback 表与专属索引；官方文档、设备数据、
  诊断记录不受影响。
- 旧向量集合中案例 document 已在删除链路清理；此处取消 outbox 中仍待重试的
  案例操作，防止迁移后重新写回。
- 历史案例和反馈按产品决策直接删除，不迁入 memory。
"""

version = 6
name = "drop_fault_cases"


def upgrade(db) -> None:  # noqa: ANN001 - sqlite3.Connection
    db.execute("DROP TABLE IF EXISTS fault_case_feedback")
    db.execute("DROP INDEX IF EXISTS ix_fault_case_lifecycle")
    db.execute("DROP INDEX IF EXISTS ix_fault_case_signature")
    db.execute("DROP INDEX IF EXISTS ix_fault_case_cluster")
    db.execute("DROP INDEX IF EXISTS uq_fault_case_source_command")
    db.execute("DROP TABLE IF EXISTS fault_case")
    # 取消所有仍待重试的案例向量操作，避免清理后被重试队列复活
    from iot_diagnosis.repository_common import iso

    db.execute(
        """UPDATE external_sync_outbox
        SET completed_at = COALESCE(completed_at, ?),
            last_error = CASE WHEN completed_at IS NULL
                THEN 'CANCELLED_LEGACY_FAULT_CASE' ELSE last_error END,
            claimed_at = NULL
        WHERE payload_json LIKE '%"source": "fault_cases"%'
           OR payload_json LIKE '%"source":"fault_cases"%'""",
        (iso(),),
    )
