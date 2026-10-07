"""Persist command delivery and per-command verification; never resend legacy commands."""

version = 5
name = "delivery_and_verification"


def upgrade(db) -> None:
    db.execute("""CREATE TABLE IF NOT EXISTS command_outbox (
        command_id TEXT PRIMARY KEY REFERENCES device_command(command_id),
        delivery_status TEXT NOT NULL DEFAULT 'pending',
        attempts INTEGER NOT NULL DEFAULT 0,
        attempted_at TEXT,
        confirmed_at TEXT,
        next_attempt_at TEXT NOT NULL,
        expires_at TEXT NOT NULL,
        baseline_json TEXT NOT NULL DEFAULT '{}'
    )""")
    # Existing commands may already have executed. They must never enter the send queue.
    db.execute("""INSERT OR IGNORE INTO command_outbox
        (command_id, delivery_status, next_attempt_at, expires_at)
        SELECT command_id, 'unknown', created_at,
            COALESCE(strftime('%Y-%m-%dT%H:%M:%f+00:00', created_at, '+30 minutes'), created_at)
        FROM device_command""")
    db.execute("""CREATE TRIGGER IF NOT EXISTS enqueue_device_command
        AFTER INSERT ON device_command BEGIN
            INSERT INTO command_outbox(command_id, next_attempt_at, expires_at)
            VALUES (NEW.command_id, NEW.created_at,
                strftime('%Y-%m-%dT%H:%M:%f+00:00', NEW.created_at, '+30 minutes'));
        END""")
    db.execute("""CREATE TABLE IF NOT EXISTS command_verification (
        command_id TEXT PRIMARY KEY REFERENCES device_command(command_id),
        device_id TEXT NOT NULL,
        started_at TEXT NOT NULL,
        deadline TEXT NOT NULL,
        status_json TEXT NOT NULL DEFAULT '{}',
        error_seen INTEGER NOT NULL DEFAULT 0
    )""")
    db.execute("""INSERT OR IGNORE INTO command_verification
        (command_id, device_id, started_at, deadline)
        SELECT command_id, device_id, COALESCE(acked_at, updated_at),
            strftime('%Y-%m-%dT%H:%M:%f+00:00', COALESCE(acked_at, updated_at), '+60 seconds')
        FROM device_command WHERE status = 'applied' AND verify_status IS NULL""")
    db.execute("""CREATE INDEX IF NOT EXISTS idx_outbox_pending
        ON command_outbox(delivery_status, next_attempt_at)""")
    db.execute("""CREATE INDEX IF NOT EXISTS idx_verification_device
        ON command_verification(device_id, deadline)""")
