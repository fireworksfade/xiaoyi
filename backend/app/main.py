import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import select

from app.api.router import router
from app.config import get_settings
from app.db import SessionFactory, create_schema
from app.models import User, UserRole
from app.security import hash_password


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
async def lifespan(_: FastAPI):
    await create_schema()
    await seed_users()
    yield


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
    response = await call_next(request)
    response.headers["X-Request-ID"] = request.state.request_id
    return response


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


@app.get("/health")
async def health(request: Request) -> dict[str, object]:
    return {
        "data": {"status": "ok", "service": "xiaoyi-backend"},
        "request_id": request.state.request_id,
    }


app.include_router(router)
