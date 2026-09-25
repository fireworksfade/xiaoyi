"""显式重建服务的进度表（specs WP-08）。

rebuild_job 记录每种实体的游标、已处理/失败计数与状态，
支持中断后从游标继续；由 scripts/rebuild_external.py 驱动。
"""

version = 3
name = "rebuild_jobs"

_DDL = """
CREATE TABLE IF NOT EXISTS rebuild_job (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity TEXT NOT NULL UNIQUE,
    cursor TEXT,
    processed INTEGER NOT NULL DEFAULT 0,
    failed INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'pending',
    last_error TEXT,
    updated_at TEXT NOT NULL
);
"""


def upgrade(db) -> None:  # noqa: ANN001 - sqlite3.Connection
    db.executescript(_DDL)
    db.commit()
