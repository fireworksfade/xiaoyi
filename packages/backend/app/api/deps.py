from datetime import datetime, timezone
from typing import Annotated

from fastapi import Cookie, Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.db import get_db
from app.models import Session, User, UserRole
from app.security import token_hash

Db = Annotated[AsyncSession, Depends(get_db)]
AppSettings = Annotated[Settings, Depends(get_settings)]


async def current_session(
    db: Db,
    settings: AppSettings,
    session_token: Annotated[str | None, Cookie(alias="xiaoyi_session")] = None,
) -> Session:
    if not session_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="NOT_AUTHENTICATED")
    record = await db.scalar(select(Session).where(Session.token_hash == token_hash(session_token)))
    if not record or record.expires_at.replace(tzinfo=timezone.utc) <= datetime.now(timezone.utc):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="SESSION_EXPIRED")
    return record


async def current_user(db: Db, session: Annotated[Session, Depends(current_session)]) -> User:
    user = await db.get(User, session.user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="USER_DISABLED")
    return user


async def require_csrf(
    session: Annotated[Session, Depends(current_session)],
    csrf_header: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
) -> None:
    if not csrf_header or not hmac_compare(session.csrf_hash, token_hash(csrf_header)):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="CSRF_FAILED")


def hmac_compare(left: str, right: str) -> bool:
    import hmac

    return hmac.compare_digest(left, right)


CurrentUser = Annotated[User, Depends(current_user)]
CsrfProtected = Annotated[None, Depends(require_csrf)]


async def require_admin(user: CurrentUser) -> User:
    if user.role != UserRole.ADMIN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="ADMIN_REQUIRED")
    return user


AdminUser = Annotated[User, Depends(require_admin)]
