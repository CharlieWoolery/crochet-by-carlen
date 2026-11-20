from __future__ import annotations

from datetime import datetime, timedelta, timezone

import bcrypt
from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import SESSION_COOKIE, SESSION_DAYS, check_rate_limit, require_admin
from ..database import get_db
from ..models.admin import AdminSession, AdminUser

router = APIRouter(prefix="/admin", tags=["admin"])

# Computed once at startup; used to run bcrypt for unknown emails so response
# time doesn't reveal whether the email exists.
_DUMMY_HASH = bcrypt.hashpw(b"dummy", bcrypt.gensalt())


class LoginRequest(BaseModel):
    email: str
    password: str


class AdminOut(BaseModel):
    email: str


@router.post("/login")
async def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    ip = request.client.host if request.client else "unknown"
    check_rate_limit(ip)

    result = await db.execute(select(AdminUser).where(AdminUser.email == body.email))
    user = result.scalar_one_or_none()

    # Always run bcrypt so response time doesn't reveal whether the email exists
    hash_to_check = user.password_hash.encode() if user else _DUMMY_HASH
    password_ok = bcrypt.checkpw(body.password.encode(), hash_to_check)

    if not user or not password_ok:
        from fastapi import HTTPException
        raise HTTPException(status_code=401, detail="Invalid credentials")

    expires_at = datetime.now(timezone.utc) + timedelta(days=SESSION_DAYS)
    session = AdminSession(admin_user_id=user.id, expires_at=expires_at)
    db.add(session)
    await db.commit()
    await db.refresh(session)

    response.set_cookie(
        key=SESSION_COOKIE,
        value=session.token,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=SESSION_DAYS * 24 * 60 * 60,
    )
    return {"message": "Logged in"}


@router.post("/logout")
async def logout(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
    _admin: AdminUser = Depends(require_admin),
) -> dict[str, str]:
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        result = await db.execute(
            select(AdminSession).where(AdminSession.token == token)
        )
        session = result.scalar_one_or_none()
        if session:
            await db.delete(session)
            await db.commit()

    response.delete_cookie(key=SESSION_COOKIE, httponly=True, secure=True, samesite="lax")
    return {"message": "Logged out"}


@router.get("/me", response_model=AdminOut)
async def me(admin: AdminUser = Depends(require_admin)) -> AdminOut:
    return AdminOut(email=admin.email)
