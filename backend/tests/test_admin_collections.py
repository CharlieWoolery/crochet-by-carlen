from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models.collection import Collection, CollectionStatus

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _make_collection(db_engine, **kwargs) -> Collection:
    """Insert a Collection row directly for test setup."""
    defaults = dict(
        name="Fall 2026",
        slug="fall-2026",
        status=CollectionStatus.draft,
    )
    defaults.update(kwargs)
    SessionLocal = async_sessionmaker(db_engine, expire_on_commit=False)
    async with SessionLocal() as db:
        c = Collection(**defaults)
        db.add(c)
        await db.commit()
        await db.refresh(c)
        return c


# ---------------------------------------------------------------------------
# GET /admin/collections
# ---------------------------------------------------------------------------


class TestListCollections:
    async def test_returns_empty_list(self, client, auth_headers):
        resp = await client.get("/admin/collections", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_returns_all_collections(self, client, auth_headers, db_engine):
        await _make_collection(db_engine, name="Fall 2026", slug="fall-2026")
        await _make_collection(db_engine, name="Summer 2027", slug="summer-2027")
        resp = await client.get("/admin/collections", headers=auth_headers)
        assert resp.status_code == 200
        assert len(resp.json()) == 2

    async def test_requires_auth(self, client):
        resp = await client.get("/admin/collections")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# POST /admin/collections
# ---------------------------------------------------------------------------


class TestCreateCollection:
    async def test_creates_with_generated_slug(self, client, auth_headers):
        resp = await client.post(
            "/admin/collections",
            json={"name": "Fall 2026"},
            headers=auth_headers,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Fall 2026"
        assert data["slug"] == "fall-2026"
        assert data["status"] == "draft"

    async def test_slug_collision_appends_counter(self, client, auth_headers):
        await client.post("/admin/collections", json={"name": "Fall 2026"}, headers=auth_headers)
        resp = await client.post("/admin/collections", json={"name": "Fall 2026"}, headers=auth_headers)
        assert resp.status_code == 201
        assert resp.json()["slug"] == "fall-2026-2"

    async def test_third_collision_appends_3(self, client, auth_headers):
        for _ in range(2):
            await client.post("/admin/collections", json={"name": "Yarn"}, headers=auth_headers)
        resp = await client.post("/admin/collections", json={"name": "Yarn"}, headers=auth_headers)
        assert resp.json()["slug"] == "yarn-3"

    async def test_special_chars_in_name_produce_valid_slug(self, client, auth_headers):
        resp = await client.post(
            "/admin/collections",
            json={"name": "Fall/Winter 2026!"},
            headers=auth_headers,
        )
        assert resp.status_code == 201
        assert resp.json()["slug"] == "fall-winter-2026"

    async def test_accepts_optional_fields(self, client, auth_headers):
        resp = await client.post(
            "/admin/collections",
            json={
                "name": "Spring Drop",
                "description": "Bright colours",
                "status": "live",
            },
            headers=auth_headers,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["description"] == "Bright colours"
        assert data["status"] == "live"

    async def test_requires_auth(self, client):
        resp = await client.post("/admin/collections", json={"name": "x"})
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# PATCH /admin/collections/{id}
# ---------------------------------------------------------------------------


class TestUpdateCollection:
    async def test_updates_name_and_regenerates_slug(self, client, auth_headers, db_engine):
        c = await _make_collection(db_engine, name="Old Name", slug="old-name")
        resp = await client.patch(
            f"/admin/collections/{c.id}",
            json={"name": "New Name"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "New Name"
        assert data["slug"] == "new-name"

    async def test_same_name_keeps_same_slug(self, client, auth_headers, db_engine):
        """Patching with the same name must not collide against itself."""
        c = await _make_collection(db_engine, name="Fall 2026", slug="fall-2026")
        resp = await client.patch(
            f"/admin/collections/{c.id}",
            json={"name": "Fall 2026"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["slug"] == "fall-2026"

    async def test_renamed_slug_avoids_other_collision(self, client, auth_headers, db_engine):
        await _make_collection(db_engine, name="Spring Drop", slug="spring-drop")
        c = await _make_collection(db_engine, name="Old", slug="old")
        resp = await client.patch(
            f"/admin/collections/{c.id}",
            json={"name": "Spring Drop"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["slug"] == "spring-drop-2"

    async def test_updates_description(self, client, auth_headers, db_engine):
        c = await _make_collection(db_engine)
        resp = await client.patch(
            f"/admin/collections/{c.id}",
            json={"description": "New desc"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["description"] == "New desc"

    async def test_updates_status(self, client, auth_headers, db_engine):
        c = await _make_collection(db_engine)
        resp = await client.patch(
            f"/admin/collections/{c.id}",
            json={"status": "live"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "live"

    async def test_404_on_missing(self, client, auth_headers):
        resp = await client.patch(
            f"/admin/collections/{uuid.uuid4()}",
            json={"name": "x"},
            headers=auth_headers,
        )
        assert resp.status_code == 404

    async def test_requires_auth(self, client, db_engine):
        c = await _make_collection(db_engine)
        resp = await client.patch(f"/admin/collections/{c.id}", json={"name": "x"})
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# POST /admin/collections/{id}/archive
# ---------------------------------------------------------------------------


class TestArchiveCollection:
    async def test_sets_status_archived(self, client, auth_headers, db_engine):
        c = await _make_collection(db_engine, status=CollectionStatus.live)
        resp = await client.post(
            f"/admin/collections/{c.id}/archive",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "archived"

    async def test_already_archived_is_idempotent(self, client, auth_headers, db_engine):
        c = await _make_collection(db_engine, status=CollectionStatus.archived)
        resp = await client.post(
            f"/admin/collections/{c.id}/archive",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "archived"

    async def test_404_on_missing(self, client, auth_headers):
        resp = await client.post(
            f"/admin/collections/{uuid.uuid4()}/archive",
            headers=auth_headers,
        )
        assert resp.status_code == 404

    async def test_requires_auth(self, client, db_engine):
        c = await _make_collection(db_engine)
        resp = await client.post(f"/admin/collections/{c.id}/archive")
        assert resp.status_code == 401
