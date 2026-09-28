"""Durable idempotency mapping, committed with the command/proposal."""
version = 3
name = "action_correlation"


def upgrade(db):
    db.execute("""CREATE TABLE IF NOT EXISTS action_correlation (
        correlation_key TEXT PRIMARY KEY,
        parameters_hash TEXT NOT NULL,
        command_id TEXT,
        proposal_id TEXT,
        delivery_status TEXT NOT NULL DEFAULT 'unknown'
    )""")
    db.commit()
