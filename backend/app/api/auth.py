from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select

from app.api.common import SettingsDep, envelope, user_view
from app.api.deps import CsrfProtected, CurrentUser, Db, current_session
from app.models import Session, User
from app.schemas import LoginRequest
from app.security import opaque_token, token_hash, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login")
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: Db,
    settings: SettingsDep,
) -> dict[str, object]:
    user = await db.scalar(select(User).where(User.username == payload.username))
    if not user or not user.is_active or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="INVALID_CREDENTIALS")
    session_token = opaque_token()
    csrf_token = opaque_token()
    record = Session(
        user_id=user.id,
        token_hash=token_hash(session_token),
        csrf_hash=token_hash(csrf_token),
        expires_at=datetime.now(timezone.utc) + timedelta(hours=settings.session_ttl_hours),
    )
    db.add(record)
    await db.commit()
    response.set_cookie(
        settings.session_cookie_name,
        session_token,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite=settings.session_cookie_samesite,
        max_age=settings.session_ttl_hours * 3600,
    )
    return envelope(request, {"user": user_view(user), "csrf_token": csrf_token})


@router.get("/me")
async def me(request: Request, user: CurrentUser) -> dict[str, object]:
    return envelope(request, user_view(user))


@router.post("/logout")
async def logout(
    request: Request,
    response: Response,
    db: Db,
    settings: SettingsDep,
    session: Annotated[Session, Depends(current_session)],
    _: CsrfProtected,
) -> dict[str, object]:
    await db.delete(session)
    await db.commit()
    response.delete_cookie(
        settings.session_cookie_name,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite=settings.session_cookie_samesite,
    )
    return envelope(request, {"logged_out": True})
