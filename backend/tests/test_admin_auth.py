from __future__ import annotations

from datetime import datetime, timedelta, timezone

import bcrypt
import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker

from app import auth
from app.auth import SESSION_COOKIE, _RATE_LIMIT_MAX
from app.models.admin import AdminSession, AdminUser


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

EMAIL = "owner@crochetbycarlen.com"
PASSWORD = "supersecret"


@pytest_asyncio.fixture
async def admin_user(db_engine):
    """Insert an AdminUser row and return (email, password)."""
    SessionLocal = async_sessionmaker(db_engine, expire_on_commit=False)
    async with SessionLocal() as db:
        hash_ = bcrypt.hashpw(PASSWORD.encode(), bcrypt.gensalt()).decode()
        user = AdminUser(email=EMAIL, password_hash=hash_)
        db.add(user)
        await db.commit()
        await db.refresh(user)
    return user


@pytest_asyncio.fixture
async def logged_in(client, admin_user):
    """Log in and return the raw session token string."""
    resp = await client.post(
        "/admin/login", json={"email": EMAIL, "password": PASSWORD}
    )
    assert resp.status_code == 200
    return resp.cookies[SESSION_COOKIE]


def _auth(token: str) -> dict[str, str]:
    """Return a Cookie header dict carrying the session token."""
    return {"Cookie": f"{SESSION_COOKIE}={token}"}


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------


class TestLogin:
    async def test_success_returns_200(self, client, admin_user):
        resp = await client.post(
            "/admin/login", json={"email": EMAIL, "password": PASSWORD}
        )
        assert resp.status_code == 200
        assert resp.json() == {"message": "Logged in"}

    async def test_success_sets_httponly_cookie(self, client, admin_user):
        resp = await client.post(
            "/admin/login", json={"email": EMAIL, "password": PASSWORD}
        )
        assert resp.status_code == 200
        set_cookie = resp.headers.get("set-cookie", "")
        assert SESSION_COOKIE in set_cookie
        assert "HttpOnly" in set_cookie
        assert "Secure" in set_cookie
        # FastAPI normalises SameSite casing
        assert "samesite=lax" in set_cookie.lower()

    async def test_wrong_password_returns_401(self, client, admin_user):
        resp = await client.post(
            "/admin/login", json={"email": EMAIL, "password": "wrongpassword"}
        )
        assert resp.status_code == 401

    async def test_unknown_email_returns_401(self, client):
        resp = await client.post(
            "/admin/login", json={"email": "nobody@example.com", "password": PASSWORD}
        )
        assert resp.status_code == 401

    async def test_rate_limit_blocks_after_max_attempts(self, client, admin_user):
        # Exhaust the limit with wrong passwords
        for _ in range(_RATE_LIMIT_MAX):
            await client.post(
                "/admin/login", json={"email": EMAIL, "password": "wrong"}
            )
        # The next attempt must be blocked regardless of credentials
        resp = await client.post(
            "/admin/login", json={"email": EMAIL, "password": PASSWORD}
        )
        assert resp.status_code == 429

    async def test_rate_limit_counts_successful_attempts(self, client, admin_user):
        # Successful logins also count toward the window so the counter
        # can't be "reset" by logging in first.
        for _ in range(_RATE_LIMIT_MAX):
            await client.post(
                "/admin/login", json={"email": EMAIL, "password": PASSWORD}
            )
        resp = await client.post(
            "/admin/login", json={"email": EMAIL, "password": PASSWORD}
        )
        assert resp.status_code == 429


# ---------------------------------------------------------------------------
# GET /admin/me
# ---------------------------------------------------------------------------


class TestMe:
    async def test_authenticated_returns_email(self, client, logged_in):
        resp = await client.get("/admin/me", headers=_auth(logged_in))
        assert resp.status_code == 200
        assert resp.json() == {"email": EMAIL}

    async def test_no_cookie_returns_401(self, client):
        resp = await client.get("/admin/me")
        assert resp.status_code == 401

    async def test_invalid_token_returns_401(self, client):
        resp = await client.get("/admin/me", headers=_auth("not-a-real-token"))
        assert resp.status_code == 401

    async def test_expired_session_returns_401(self, client, admin_user, db_engine):
        # Insert an already-expired session directly
        SessionLocal = async_sessionmaker(db_engine, expire_on_commit=False)
        async with SessionLocal() as db:
            session = AdminSession(
                admin_user_id=admin_user.id,
                expires_at=datetime.now(timezone.utc) - timedelta(seconds=1),
            )
            db.add(session)
            await db.commit()
            await db.refresh(session)
            token = session.token

        resp = await client.get("/admin/me", headers=_auth(token))
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# POST /admin/logout
# ---------------------------------------------------------------------------


class TestLogout:
    async def test_logout_returns_200(self, client, logged_in):
        resp = await client.post("/admin/logout", headers=_auth(logged_in))
        assert resp.status_code == 200
        assert resp.json() == {"message": "Logged out"}

    async def test_logout_deletes_session_from_db(self, client, logged_in, db_engine):
        await client.post("/admin/logout", headers=_auth(logged_in))

        from sqlalchemy import select

        SessionLocal = async_sessionmaker(db_engine, expire_on_commit=False)
        async with SessionLocal() as db:
            result = await db.execute(
                select(AdminSession).where(AdminSession.token == logged_in)
            )
            assert result.scalar_one_or_none() is None

    async def test_logout_clears_cookie(self, client, logged_in):
        resp = await client.post("/admin/logout", headers=_auth(logged_in))
        set_cookie = resp.headers.get("set-cookie", "")
        # Starlette's delete_cookie sets max-age=0
        assert "max-age=0" in set_cookie.lower()

    async def test_logout_requires_auth(self, client):
        resp = await client.post("/admin/logout")
        assert resp.status_code == 401

    async def test_me_returns_401_after_logout(self, client, logged_in):
        await client.post("/admin/logout", headers=_auth(logged_in))
        resp = await client.get("/admin/me", headers=_auth(logged_in))
        assert resp.status_code == 401
