from datetime import timedelta

from fastapi import APIRouter, HTTPException, Request

from app.api.common import envelope
from app.api.deps import CsrfProtected, CurrentUser, Db
from app.models import HarnessConnection, utc_now
from app.services.harness import instance_id, is_enabled, require_enabled, stop_connection_runs

router = APIRouter(prefix="/harness", tags=["Harness Desktop plugin"])


@router.get("/capabilities")
async def capabilities(request: Request, _: CurrentUser):
    return envelope(
        request,
        {
            "protocol": 1,
            "harness_version": "0.2.0-rc.2",
            "features": ["native_tools", "task_delegation", "memory", "knowledge", "approval", "leases"],
        },
    )


@router.post("/connections/{instance}/activate")
async def activate(instance: str, request: Request, db: Db, user: CurrentUser, _: CsrfProtected):
    instance_id(instance)
    if getattr(request.app.state, "run_dispatcher", None) is None:
        raise HTTPException(409, "HARNESS_DISPATCHER_REQUIRED")
    connection = await db.get(HarnessConnection, (user.id, instance))
    if connection is not None and not is_enabled(connection):
        await stop_connection_runs(request.app, user.id, instance)
    if connection is None:
        connection = HarnessConnection(user_id=user.id, instance_id=instance)
        db.add(connection)
    connection.enabled = True
    connection.lease_until = utc_now() + timedelta(seconds=90)
    await db.commit()
    return envelope(request, {"enabled": True, "lease_seconds": 90})


@router.post("/connections/{instance}/heartbeat")
async def heartbeat(instance: str, request: Request, db: Db, user: CurrentUser, _: CsrfProtected):
    instance_id(instance)
    await require_enabled(db, user.id, instance)
    connection = await db.get(HarnessConnection, (user.id, instance))
    connection.lease_until = utc_now() + timedelta(seconds=90)
    await db.commit()
    return envelope(request, {"enabled": True, "lease_seconds": 90})


@router.post("/connections/{instance}/deactivate")
async def deactivate(instance: str, request: Request, db: Db, user: CurrentUser, _: CsrfProtected):
    instance_id(instance)
    connection = await db.get(HarnessConnection, (user.id, instance))
    if connection:
        connection.enabled = False
        await db.commit()
    result = await stop_connection_runs(request.app, user.id, instance)
    return envelope(request, {"enabled": False, **result})
