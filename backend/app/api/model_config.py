import ipaddress
from urllib.parse import urlsplit

from fastapi import APIRouter, HTTPException, Request
from openai import AsyncOpenAI
from sqlalchemy import select

from app.api.deps import CsrfProtected, CurrentUser, Db
from app.config import get_settings
from app.models import ModelConfiguration
from app.schemas import ModelConfigurationUpdate
from app.security import decrypt_secret, encrypt_secret
from app.services.operations import add_audit_log

router = APIRouter(prefix="/model-config", tags=["Model configuration"])


def envelope(request: Request, data: object) -> dict[str, object]:
    return {"data": data, "request_id": request.state.request_id}


def validate_base_url(value: str) -> str:
    parsed = urlsplit(value)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("MODEL_BASE_URL_INVALID")
    if parsed.scheme == "http" and parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise ValueError("MODEL_BASE_URL_REQUIRES_HTTPS")
    try:
        address = ipaddress.ip_address(parsed.hostname)
    except ValueError:
        address = None
    if address and not address.is_global and not address.is_loopback:
        raise ValueError("MODEL_BASE_URL_PRIVATE_ADDRESS_BLOCKED")
    return value.rstrip("/")


def config_view(item: ModelConfiguration | None) -> dict[str, object]:
    settings = get_settings()
    if not item:
        return {
            "provider_name": "OpenAI",
            "base_url": settings.openai_base_url,
            "model_name": settings.openai_model,
            "api_mode": settings.openai_api_mode,
            "api_key_configured": False,
            "api_key_hint": None,
            "enabled": False,
        }
    key = decrypt_secret(item.api_key_ciphertext, settings.app_secret_key)
    return {
        "provider_name": item.provider_name,
        "base_url": item.base_url,
        "model_name": item.model_name,
        "api_mode": item.api_mode,
        "api_key_configured": bool(key),
        "api_key_hint": f"••••{key[-4:]}" if key else None,
        "enabled": item.enabled,
    }


async def user_config(db: Db, user_id: str) -> ModelConfiguration | None:
    return await db.scalar(select(ModelConfiguration).where(ModelConfiguration.user_id == user_id))


@router.get("")
async def get_model_config(
    request: Request,
    db: Db,
    user: CurrentUser,
) -> dict[str, object]:
    return envelope(request, config_view(await user_config(db, user.id)))


@router.put("")
async def update_model_config(
    payload: ModelConfigurationUpdate,
    request: Request,
    db: Db,
    user: CurrentUser,
    _: CsrfProtected,
) -> dict[str, object]:
    try:
        base_url = validate_base_url(payload.base_url)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    item = await user_config(db, user.id)
    if not item:
        item = ModelConfiguration(user_id=user.id)
        db.add(item)
    item.provider_name = payload.provider_name
    item.base_url = base_url
    item.model_name = payload.model_name
    item.api_mode = payload.api_mode
    if payload.clear_api_key:
        item.api_key_ciphertext = None
    elif payload.api_key:
        item.api_key_ciphertext = encrypt_secret(payload.api_key, get_settings().app_secret_key)
    if payload.enabled and not item.api_key_ciphertext:
        raise HTTPException(status_code=422, detail="MODEL_API_KEY_REQUIRED")
    item.enabled = payload.enabled
    await db.flush()
    add_audit_log(
        db,
        actor_type="user",
        actor_id=user.id,
        action="model_configuration.updated",
        resource_type="model_configuration",
        resource_id=item.id,
        request_id=request.state.request_id,
        details={
            "provider_name": item.provider_name,
            "base_url": item.base_url,
            "model_name": item.model_name,
            "api_mode": item.api_mode,
            "api_key_configured": bool(item.api_key_ciphertext),
            "enabled": item.enabled,
        },
    )
    await db.commit()
    return envelope(request, config_view(item))


@router.post("/test")
async def test_model_config(
    request: Request,
    db: Db,
    user: CurrentUser,
    _: CsrfProtected,
) -> dict[str, object]:
    item = await user_config(db, user.id)
    if not item or not item.api_key_ciphertext:
        raise HTTPException(status_code=422, detail="MODEL_API_KEY_REQUIRED")
    key = decrypt_secret(item.api_key_ciphertext, get_settings().app_secret_key)
    try:
        async with AsyncOpenAI(api_key=key, base_url=item.base_url) as client:
            models = await client.models.list()
            available = any(model.id == item.model_name for model in models.data)
    except Exception as exc:
        raise HTTPException(status_code=502, detail="MODEL_CONNECTION_FAILED") from exc
    return envelope(
        request,
        {"connected": True, "model_available": available, "model_name": item.model_name},
    )
