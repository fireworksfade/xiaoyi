"""设备状态扩展字段。

真实固件的 status 还带有复位原因、启动次数、空闲堆、重连次数、Keep Alive、
可回退版本等运维字段。它们只保存最新值（不进历史序列），供诊断查看，
并作为修复动作执行前的验证快照。
"""

version = 7
name = "device_state_details"


def upgrade(db) -> None:  # noqa: ANN001 - sqlite3.Connection
    columns = {row[1] for row in db.execute("PRAGMA table_info(device_current_state)")}
    if "details_json" not in columns:
        db.execute("ALTER TABLE device_current_state ADD COLUMN details_json TEXT")
    db.commit()
