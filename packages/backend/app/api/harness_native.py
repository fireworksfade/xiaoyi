from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.agent.remediation_correlation import RemediationCorrelationError
from app.api.common import envelope
from app.api.deps import CsrfProtected, CurrentUser, Db
from app.services.harness import HEADER, instance_id
from app.services.harness_native import (
    create_native_run,
    execute_native_tool,
    native_catalog,
    owned_native_run,
    run_lock,
    settle_native_run,
)

router = APIRouter(prefix="/harness/native", tags=["Harness native tools"])


def native_instance(request):
    instance = instance_id(request.headers.get(HEADER))
    if not instance:
        raise HTTPException(400, "HARNESS_INSTANCE_REQUIRED")
    return instance


class NativeRunCreate(BaseModel):
    context_key: str = Field(min_length=1, max_length=160)


class NativeToolCall(BaseModel):
    tool_id: str = Field(min_length=1, max_length=120)
    arguments: dict = Field(default_factory=dict)
    call_id: str = Field(min_length=1, max_length=160)


class NativeRunClose(BaseModel):
    cancelled: bool = False


@router.get("/tools")
async def tools(request: Request, db: Db, _: CurrentUser):
    native_instance(request)
    return envelope(request, {"items": await native_catalog(db), "executor": "deepseek-harness"})


@router.post("/runs")
async def create(
    payload: NativeRunCreate, request: Request, db: Db, user: CurrentUser, _: CsrfProtected
):
    instance = native_instance(request)
    async with run_lock(f"create:{user.id}:{instance}:{payload.context_key}"):
        run = await create_native_run(db, user.id, instance, payload.context_key)
    return envelope(request, {"run_id": run.id, "executor": "deepseek-harness"})


@router.post("/runs/{run_id}/call")
async def call(
    run_id: str, payload: NativeToolCall, request: Request, user: CurrentUser, _: CsrfProtected
):
    try:
        result = await execute_native_tool(
            request.app,
            user,
            native_instance(request),
            run_id,
            payload.tool_id,
            payload.arguments,
            payload.call_id,
        )
    except RemediationCorrelationError as exc:
        raise HTTPException(409, exc.code) from exc
    return envelope(request, result)


@router.post("/runs/{run_id}/close")
async def close(
    run_id: str,
    payload: NativeRunClose,
    request: Request,
    db: Db,
    user: CurrentUser,
    _: CsrfProtected,
):
    async with run_lock(run_id):
        await owned_native_run(db, user.id, native_instance(request), run_id)
        await db.commit()
        await settle_native_run(run_id, failed=payload.cancelled)
    return envelope(request, {"closed": True})
