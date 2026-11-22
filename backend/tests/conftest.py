from __future__ import annotations

import asyncio
import itertools
import os

import bcrypt
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.pool import NullPool
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

# Importing from app triggers app/config.py which loads .env
from app import auth
from app.auth import SESSION_COOKIE
from app.database import get_db
from app.main import app
from app.models.admin import AdminUser
from app.models.base import Base

# ---------------------------------------------------------------------------
# Safety guard — checked at collection time, before any fixture runs.
# ---------------------------------------------------------------------------

_TEST_DB_URL: str = os.environ.get("TEST_DATABASE_URL", "").strip()
_PROD_DB_URL: str = os.environ.get("DATABASE_URL", "").strip()

if not _TEST_DB_URL:
    raise RuntimeError(
        "TEST_DATABASE_URL is not set. "
        "Add TEST_DATABASE_URL=<url> to .env pointing at a dedicated test "
        "database, then re-run pytest."
    )

if _TEST_DB_URL == _PROD_DB_URL:
    raise RuntimeError(
        "TEST_DATABASE_URL and DATABASE_URL are the same. "
        "The test suite must not run against the production database."
    )


# ---------------------------------------------------------------------------
# Session-scoped schema management
# ---------------------------------------------------------------------------
# Schema creation and teardown run once per pytest session in their own
# temporary event loop so they don't interfere with pytest-asyncio's
# per-test loops.


def _run_sync(coro) -> None:
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(coro)
    finally:
        loop.close()


@pytest.fixture(scope="session", autouse=True)
def _init_test_schema() -> None:
    """Drop and recreate all tables exactly once per test session."""

    async def _setup() -> None:
        engine = create_async_engine(_TEST_DB_URL, poolclass=NullPool)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)
        await engine.dispose()

    async def _teardown() -> None:
        engine = create_async_engine(_TEST_DB_URL, poolclass=NullPool)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await engine.dispose()

    _run_sync(_setup())
    yield
    _run_sync(_teardown())


# ---------------------------------------------------------------------------
# Per-test fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def db_engine(_init_test_schema):
    """
    Per-test database connection with an open transaction that is always
    rolled back when the test finishes — no truncation queries needed.

    Yields an AsyncConnection, not an AsyncEngine.  async_sessionmaker accepts
    both, so test helpers that call async_sessionmaker(db_engine, ...) work
    unchanged.  Because the connection already has an active transaction,
    SQLAlchemy's default "conditional_savepoint" join_transaction_mode kicks
    in: every session.commit() inside a helper or route handler emits a
    SAVEPOINT / RELEASE SAVEPOINT rather than a real COMMIT.  The final
    transaction.rollback() wipes all test data with a single round-trip.
    """
    engine = create_async_engine(_TEST_DB_URL, poolclass=NullPool)
    async with engine.connect() as conn:
        transaction = await conn.begin()
        try:
            yield conn
        finally:
            await transaction.rollback()
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


@pytest.fixture(autouse=True)
def mock_order_number(monkeypatch):
    """Replace the Postgres-sequence call with a simple per-test counter."""
    counter = itertools.count(1001)

    async def _fake(db):
        return f"CBC-{next(counter)}"

    monkeypatch.setattr("app.utils.order_number.next_order_number", _fake)


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
