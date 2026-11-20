from __future__ import annotations

import time
from collections import defaultdict
from datetime import datetime, timezone

from fastapi import Cookie, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .database import get_db
from .models.admin import AdminSession, AdminUser

SESSION_COOKIE = "admin_session"
SESSION_DAYS = 30

# In-memory sliding-window rate limiter for the login endpoint.
# Single-instance deployment, so no Redis needed.
_RATE_LIMIT_MAX = 5
_RATE_LIMIT_WINDOW_SECS = 15 * 60
_login_attempts: dict[str, list[float]] = defaultdict(list)


def _prune(ip: str, now: float) -> list[float]:
    recent = [t for t in _login_attempts[ip] if now - t < _RATE_LIMIT_WINDOW_SECS]
    _login_attempts[ip] = recent
    return recent


def check_rate_limit(ip: str) -> None:
    """Raise 429 if this IP has hit the limit, then record the attempt."""
    now = time.monotonic()
    if len(_prune(ip, now)) >= _RATE_LIMIT_MAX:
        raise HTTPException(status_code=429, detail="Too many login attempts. Try again later.")
    _login_attempts[ip].append(now)


async def require_admin(
    db: AsyncSession = Depends(get_db),
    token: str | None = Cookie(default=None, alias=SESSION_COOKIE),
) -> AdminUser:
    """FastAPI dependency. Validates the session cookie and returns the AdminUser."""
    if token is None:
        raise HTTPException(status_code=401, detail="Not authenticated")

    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(AdminSession).where(
            AdminSession.token == token,
            AdminSession.expires_at > now,
        )
    )
    session = result.scalar_one_or_none()
    if session is None:
        raise HTTPException(status_code=401, detail="Not authenticated")

    result = await db.execute(
        select(AdminUser).where(AdminUser.id == session.admin_user_id)
    )
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=401, detail="Not authenticated")

    return user
