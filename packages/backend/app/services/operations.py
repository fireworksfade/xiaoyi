from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog


def add_audit_log(
    db: AsyncSession,
    *,
    actor_type: str,
    actor_id: str | None,
    action: str,
    resource_type: str,
    resource_id: str | None,
    request_id: str | None,
    details: dict[str, object] | None = None,
) -> AuditLog:
    entry = AuditLog(
        actor_type=actor_type,
        actor_id=actor_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        request_id=request_id,
        details=details or {},
    )
    db.add(entry)
    return entry
