import asyncio
import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from prometheus_client import make_asgi_app
from sqlalchemy import select

from app.api.router import router
from app.config import get_settings
from app.db import SessionFactory
from app.errors import AppError
from app.migrations import RevisionStatus, check_revision, upgrade_to_head
from app.models import User, UserRole
from app.observability.logging import configure_logging
from app.observability.metrics import (
    HTTP_LATENCY,
    HTTP_REQUESTS,
)
from app.security import hash_password
from app.services.retention import retention_loop
from app.services.run_dispatcher import RunDispatcher
from app.services.run_recovery import recover_interrupted_runs
from app.services.runs import execute_claimed_run

configure_logging("xiaoyi-backend")
logger = logging.getLogger("xiaoyi.main")


async def seed_users() -> None:
    settings = get_settings()
    if not settings.seed_demo_users:
        return
    async with SessionFactory() as db:
        if await db.scalar(select(User.id).limit(1)):
            return
        db.add_all(
            [
                User(
                    username="admin", password_hash=hash_password("admin123"), role=UserRole.ADMIN
                ),
                User(
                    username="operator",
                    password_hash=hash_password("operator123"),
                    role=UserRole.OPERATOR,
                ),
            ]
        )
        await db.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    settings.ensure_local_paths()
    if settings.db_auto_upgrade:
        # 开发/测试：启动即升级到 head。生产部署必须先行执行
        # `python -m app.cli deploy`，并设置 DB_AUTO_UPGRADE=false。
        upgrade_to_head()
    else:
        status = check_revision()
        if status == RevisionStatus.AHEAD:
            raise RuntimeError(
                "DATABASE_SCHEMA_AHEAD: 数据库版本高于当前代码支持版本，请部署匹配的应用版本"
            )
        if status == RevisionStatus.BEHIND:
            raise RuntimeError(
                "DATABASE_SCHEMA_BEHIND: 数据库版本落后，请先执行 python -m app.cli deploy"
            )
        if status == RevisionStatus.EMPTY:
            raise RuntimeError(
                "DATABASE_NOT_INITIALIZED: 空数据库，请先执行 python -m app.cli deploy"
            )
        logger.info("database revision check passed: %s", status.value)

    # 恢复扫描：RUNNING → FAILED/RUN_INTERRUPTED；QUEUED 保留待执行
    report = await recover_interrupted_runs()
    logger.info(
        "startup recovery: %s",
        report.to_dict(),
        extra={"event": "run_recovery_report", **report.to_dict()},
    )

    dispatcher: RunDispatcher | None = None
    if settings.run_dispatcher_mode == "dispatcher":
        dispatcher = RunDispatcher(
            execute_claimed_run,
            poll_interval_seconds=settings.run_dispatcher_poll_seconds,
            shutdown_grace_seconds=settings.run_shutdown_grace_seconds,
        )
        dispatcher.start()
        app.state.run_dispatcher = dispatcher
        # 恢复扫描留下的 QUEUED 任务由周期扫描接管，无需额外通知

    # 数据保留：删除开关关闭时持续输出 dry-run 统计（WP-11）
    retention_task = asyncio.create_task(
        retention_loop(
            delete_enabled=settings.retention_delete_enabled,
            interval_hours=settings.retention_interval_hours,
        ),
        name="retention-loop",
    )

    await seed_users()
    yield
    retention_task.cancel()
    try:
        await retention_task
    except asyncio.CancelledError:
        pass
    if dispatcher is not None:
        await dispatcher.stop()


settings = get_settings()
app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.frontend_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "X-CSRF-Token", "Last-Event-ID"],
)


@app.middleware("http")
async def request_context(request: Request, call_next):
    request.state.request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        _record_http_metrics(request, 500, time.perf_counter() - started)
        raise
    _record_http_metrics(request, response.status_code, time.perf_counter() - started)
    response.headers["X-Request-ID"] = request.state.request_id
    return response


def _record_http_metrics(request: Request, status_code: int, duration: float) -> None:
    if request.url.path.startswith(("/metrics", "/live", "/ready", "/health")):
        return
    # 用路由模板做标签，避免高基数；静态路径退回实际 path
    route = request.scope.get("route")
    path = getattr(route, "path", request.url.path)
    method = request.method
    HTTP_REQUESTS.labels(method=method, path=path, status=str(status_code)).inc()
    HTTP_LATENCY.labels(method=method, path=path).observe(duration)


@app.exception_handler(HTTPException)
async def http_error(request: Request, exc: HTTPException) -> JSONResponse:
    code = str(exc.detail)
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {"code": code, "message": code.replace("_", " ").title(), "retryable": False},
            "request_id": getattr(request.state, "request_id", None),
        },
        headers=exc.headers,
    )


@app.exception_handler(AppError)
async def app_error(request: Request, exc: AppError) -> JSONResponse:
    error_class = exc.error_class
    return JSONResponse(
        status_code=error_class.http_status,
        content={
            "error": {
                "code": error_class.code,
                "message": error_class.public_message,
                "retryable": error_class.retryable,
            },
            "request_id": getattr(request.state, "request_id", None),
        },
    )


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "请求参数无效",
                "retryable": False,
                "details": exc.errors(),
            },
            "request_id": getattr(request.state, "request_id", None),
        },
    )


@app.get("/live")
async def live(request: Request) -> dict[str, object]:
    """进程存活探针：事件循环可响应即 200，不检查任何依赖。"""
    return {
        "data": {"status": "alive", "service": "xiaoyi-backend"},
        "request_id": request.state.request_id,
    }


@app.get("/ready")
async def ready(request: Request) -> JSONResponse:
    """业务就绪探针：数据库、schema 版本、Dispatcher；必需 MCP 故障时 503。"""
    from app.services.readiness import probe_readiness

    report = await probe_readiness(
        dispatcher=getattr(app.state, "run_dispatcher", None),
    )
    return JSONResponse(
        status_code=report.http_status(),
        content={
            "data": {
                "status": report.status,
                "service": "xiaoyi-backend",
                "checks": report.checks,
            },
            "request_id": request.state.request_id,
        },
    )


@app.get("/health")
async def health(request: Request) -> dict[str, object]:
    """兼容旧探针：进程存活语义（等价 /live）。容器健康检查应使用 /ready。"""
    return {
        "data": {"status": "ok", "service": "xiaoyi-backend"},
        "request_id": request.state.request_id,
    }


app.mount("/metrics", make_asgi_app())

app.include_router(router)
