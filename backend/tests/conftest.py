from __future__ import annotations

import bcrypt
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app import auth
from app.auth import SESSION_COOKIE
from app.database import get_db
from app.main import app
from app.models.admin import AdminUser
from app.models.base import Base


@pytest_asyncio.fixture
async def db_engine():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def client(db_engine):
    SessionLocal = async_sessionmaker(db_engine, expire_on_commit=False)

    async def override_get_db():
        async with SessionLocal() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def reset_rate_limiter():
    """Clear in-memory rate-limit state between tests."""
    auth._login_attempts.clear()
    yield
    auth._login_attempts.clear()


@pytest_asyncio.fixture
async def auth_headers(client, db_engine):
    """
    Create an AdminUser, log in, and return a Cookie header dict.
    Use this in tests that need an authenticated request.
    """
    email = "admin@test.com"
    password = "testpass"
    SessionLocal = async_sessionmaker(db_engine, expire_on_commit=False)
    async with SessionLocal() as db:
        hash_ = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
        db.add(AdminUser(email=email, password_hash=hash_))
        await db.commit()

    resp = await client.post("/admin/login", json={"email": email, "password": password})
    token = resp.cookies[SESSION_COOKIE]
    return {"Cookie": f"{SESSION_COOKIE}={token}"}
