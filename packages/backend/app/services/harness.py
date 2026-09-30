"""Plugin lifecycle boundary shared by HTTP admission and the Agent runtime."""

import asyncio
import logging
import re
from datetime import timezone

from fastapi import HTTPException
from sqlalchemy import select, update

from app.db import SessionFactory
from app.models import AgentRun, HarnessConnection, RunStatus, utc_now

logger = logging.getLogger(__name__)
HEADER = "X-Xiaoyi-Harness-Instance"


def instance_id(value: str | None) -> str | None:
    if value is not None and not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", value):
        raise HTTPException(422, "HARNESS_INSTANCE_INVALID")
    return value


def is_enabled(connection) -> bool:
    return bool(
        connection
        and connection.enabled
        and connection.lease_until.replace(tzinfo=timezone.utc) > utc_now()
    )


async def require_enabled(db, user_id, instance):
    if instance:
        connection = await db.get(HarnessConnection, (user_id, instance))
        if not is_enabled(connection):
            raise HTTPException(409, "HARNESS_PLUGIN_DISABLED")


async def assert_run_enabled(run_id):
    if not run_id:
        return
    async with SessionFactory() as db:
        run = await db.get(AgentRun, run_id)
        if run and (instance := (run.runtime_state or {}).get("harness_instance")):
            connection = await db.get(HarnessConnection, (run.user_id, instance))
            if not is_enabled(connection):
                raise asyncio.CancelledError("RUN_STOPPED")


async def stop_connection_runs(app, user_id, instance):
    async with SessionFactory() as db:
        runs = list(
            (
                await db.scalars(
                    select(AgentRun).where(
                        AgentRun.user_id == user_id,
                        AgentRun.status.in_([RunStatus.QUEUED, RunStatus.RUNNING]),
                    )
                )
            ).all()
        )
    dispatcher = getattr(app.state, "run_dispatcher", None)
    stopped, pending = [], []
    for run in runs:
        if (run.runtime_state or {}).get("harness_instance") != instance:
            continue
        if (run.runtime_state or {}).get("harness_native"):
            from app.services.harness_native import settle_native_run
            task = getattr(app.state, "harness_native_tasks", {}).get(run.id)
            if task and not task.done():
                task.cancel("PLUGIN_DISABLED")
                await asyncio.gather(task, return_exceptions=True)
            await settle_native_run(run.id, failed=True)
            stopped.append(run.id)
            continue
        if dispatcher is not None and await dispatcher.cancel(run.id):
            stopped.append(run.id)
        else:
            pending.append(run.id)
    return {"stopped_run_ids": stopped, "pending_run_ids": pending}


async def lease_watchdog(app):
    while True:
        await asyncio.sleep(5)
        try:
            async with SessionFactory() as db:
                expired = list(
                    (
                        await db.scalars(
                            select(HarnessConnection).where(
                                HarnessConnection.enabled.is_(True),
                                HarnessConnection.lease_until <= utc_now(),
                            )
                        )
                    ).all()
                )
                expired_ids = []
                for connection in expired:
                    result = await db.execute(
                        update(HarnessConnection)
                        .where(
                            HarnessConnection.user_id == connection.user_id,
                            HarnessConnection.instance_id == connection.instance_id,
                            HarnessConnection.enabled.is_(True),
                            HarnessConnection.lease_until <= utc_now(),
                        )
                        .values(enabled=False)
                    )
                    if result.rowcount:
                        expired_ids.append((connection.user_id, connection.instance_id))
                await db.commit()
            for user_id, instance in expired_ids:
                await stop_connection_runs(app, user_id, instance)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("harness lease cleanup failed")
