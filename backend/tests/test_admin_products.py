from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models.collection import Collection, CollectionStatus
from app.models.order import OrderItem
from app.models.product import Product, ProductStatus

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _make_collection(db_engine, **kwargs) -> Collection:
    defaults = dict(name="Fall 2026", slug="fall-2026", status=CollectionStatus.live)
    defaults.update(kwargs)
    SessionLocal = async_sessionmaker(db_engine, expire_on_commit=False)
    async with SessionLocal() as db:
        c = Collection(**defaults)
        db.add(c)
        await db.commit()
        await db.refresh(c)
        return c


async def _make_product(db_engine, collection_id: uuid.UUID, **kwargs) -> Product:
    defaults = dict(
        collection_id=collection_id,
        name="Green Bag",
        slug="green-bag",
        description="A lovely bag",
        price_cents=2500,
        materials="Cotton",
        status=ProductStatus.draft,
    )
    defaults.update(kwargs)
    SessionLocal = async_sessionmaker(db_engine, expire_on_commit=False)
    async with SessionLocal() as db:
        p = Product(**defaults)
        db.add(p)
        await db.commit()
        await db.refresh(p)
        return p


PRODUCT_BODY = {
    "name": "Cozy Scarf",
    "description": "Very warm",
    "price_cents": 3500,
    "materials": "Wool",
}


# ---------------------------------------------------------------------------
# POST /admin/products
# ---------------------------------------------------------------------------


class TestCreateProduct:
    async def test_creates_with_generated_slug(self, client, auth_headers, db_engine):
        c = await _make_collection(db_engine)
        resp = await client.post(
            "/admin/products",
            json={**PRODUCT_BODY, "collection_id": str(c.id)},
            headers=auth_headers,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Cozy Scarf"
        assert data["slug"] == "cozy-scarf"
        assert data["status"] == "draft"

    async def test_slug_collision_appends_counter(self, client, auth_headers, db_engine):
        c = await _make_collection(db_engine)
        body = {**PRODUCT_BODY, "collection_id": str(c.id)}
        await client.post("/admin/products", json=body, headers=auth_headers)
        resp = await client.post("/admin/products", json=body, headers=auth_headers)
        assert resp.status_code == 201
        assert resp.json()["slug"] == "cozy-scarf-2"

    async def test_price_must_be_positive(self, client, auth_headers, db_engine):
        c = await _make_collection(db_engine)
        resp = await client.post(
            "/admin/products",
            json={**PRODUCT_BODY, "collection_id": str(c.id), "price_cents": 0},
            headers=auth_headers,
        )
        assert resp.status_code == 422

    async def test_requires_auth(self, client, db_engine):
        c = await _make_collection(db_engine)
        resp = await client.post(
            "/admin/products",
            json={**PRODUCT_BODY, "collection_id": str(c.id)},
        )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /admin/products
# ---------------------------------------------------------------------------


class TestListProducts:
    async def test_returns_all_products(self, client, auth_headers, db_engine):
        c = await _make_collection(db_engine)
        await _make_product(db_engine, c.id, name="A", slug="a")
        await _make_product(db_engine, c.id, name="B", slug="b")
        resp = await client.get("/admin/products", headers=auth_headers)
        assert resp.status_code == 200
        assert len(resp.json()) == 2

    async def test_filter_by_status(self, client, auth_headers, db_engine):
        c = await _make_collection(db_engine)
        await _make_product(db_engine, c.id, name="D", slug="d", status=ProductStatus.draft)
        await _make_product(db_engine, c.id, name="L", slug="l", status=ProductStatus.live)
        resp = await client.get("/admin/products?status=live", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["status"] == "live"

    async def test_filter_by_collection(self, client, auth_headers, db_engine):
        c1 = await _make_collection(db_engine, name="C1", slug="c1")
        c2 = await _make_collection(db_engine, name="C2", slug="c2")
        await _make_product(db_engine, c1.id, name="X", slug="x")
        await _make_product(db_engine, c2.id, name="Y", slug="y")
        resp = await client.get(f"/admin/products?collection={c1.id}", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["collection_id"] == str(c1.id)

    async def test_requires_auth(self, client):
        resp = await client.get("/admin/products")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /admin/products/{id}
# ---------------------------------------------------------------------------


class TestGetProduct:
    async def test_returns_product(self, client, auth_headers, db_engine):
        c = await _make_collection(db_engine)
        p = await _make_product(db_engine, c.id)
        resp = await client.get(f"/admin/products/{p.id}", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["id"] == str(p.id)

    async def test_404_on_missing(self, client, auth_headers):
        resp = await client.get(f"/admin/products/{uuid.uuid4()}", headers=auth_headers)
        assert resp.status_code == 404

    async def test_requires_auth(self, client, db_engine):
        c = await _make_collection(db_engine)
        p = await _make_product(db_engine, c.id)
        resp = await client.get(f"/admin/products/{p.id}")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# PATCH /admin/products/{id}
# ---------------------------------------------------------------------------


class TestUpdateProduct:
    async def test_updates_price(self, client, auth_headers, db_engine):
        c = await _make_collection(db_engine)
        p = await _make_product(db_engine, c.id)
        resp = await client.patch(
            f"/admin/products/{p.id}",
            json={"price_cents": 9900},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["price_cents"] == 9900

    async def test_name_change_regenerates_slug(self, client, auth_headers, db_engine):
        c = await _make_collection(db_engine)
        p = await _make_product(db_engine, c.id, name="Old", slug="old")
        resp = await client.patch(
            f"/admin/products/{p.id}",
            json={"name": "New Thing"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "New Thing"
        assert data["slug"] == "new-thing"

    async def test_same_name_keeps_same_slug(self, client, auth_headers, db_engine):
        c = await _make_collection(db_engine)
        p = await _make_product(db_engine, c.id, name="Green Bag", slug="green-bag")
        resp = await client.patch(
            f"/admin/products/{p.id}",
            json={"name": "Green Bag"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["slug"] == "green-bag"

    async def test_renamed_slug_avoids_other_collision(self, client, auth_headers, db_engine):
        c = await _make_collection(db_engine)
        await _make_product(db_engine, c.id, name="Blue Hat", slug="blue-hat")
        p = await _make_product(db_engine, c.id, name="Old", slug="old")
        resp = await client.patch(
            f"/admin/products/{p.id}",
            json={"name": "Blue Hat"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["slug"] == "blue-hat-2"

    async def test_unset_fields_are_not_touched(self, client, auth_headers, db_engine):
        c = await _make_collection(db_engine)
        p = await _make_product(db_engine, c.id, name="Green Bag", slug="green-bag")
        original_materials = p.materials
        resp = await client.patch(
            f"/admin/products/{p.id}",
            json={"price_cents": 1000},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["materials"] == original_materials

    async def test_404_on_missing(self, client, auth_headers):
        resp = await client.patch(
            f"/admin/products/{uuid.uuid4()}",
            json={"price_cents": 100},
            headers=auth_headers,
        )
        assert resp.status_code == 404

    async def test_requires_auth(self, client, db_engine):
        c = await _make_collection(db_engine)
        p = await _make_product(db_engine, c.id)
        resp = await client.patch(f"/admin/products/{p.id}", json={"price_cents": 100})
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# POST /admin/products/{id}/archive
# ---------------------------------------------------------------------------


class TestArchiveProduct:
    async def test_sets_status_archived(self, client, auth_headers, db_engine):
        c = await _make_collection(db_engine)
        p = await _make_product(db_engine, c.id, status=ProductStatus.live)
        resp = await client.post(
            f"/admin/products/{p.id}/archive",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "archived"

    async def test_already_archived_is_idempotent(self, client, auth_headers, db_engine):
        c = await _make_collection(db_engine)
        p = await _make_product(db_engine, c.id, status=ProductStatus.archived)
        resp = await client.post(
            f"/admin/products/{p.id}/archive",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "archived"

    async def test_404_on_missing(self, client, auth_headers):
        resp = await client.post(
            f"/admin/products/{uuid.uuid4()}/archive",
            headers=auth_headers,
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# DELETE /admin/products/{id}
# ---------------------------------------------------------------------------


class TestDeleteProduct:
    async def test_deletes_product_with_no_orders(self, client, auth_headers, db_engine):
        c = await _make_collection(db_engine)
        p = await _make_product(db_engine, c.id)
        resp = await client.delete(f"/admin/products/{p.id}", headers=auth_headers)
        assert resp.status_code == 204
        # Confirm gone
        resp2 = await client.get(f"/admin/products/{p.id}", headers=auth_headers)
        assert resp2.status_code == 404

    async def test_409_when_product_has_orders(self, client, auth_headers, db_engine):
        c = await _make_collection(db_engine)
        p = await _make_product(db_engine, c.id)
        # Attach a stub order item directly
        SessionLocal = async_sessionmaker(db_engine, expire_on_commit=False)
        async with SessionLocal() as db:
            db.add(OrderItem(order_id=uuid.uuid4(), product_id=p.id))
            await db.commit()

        resp = await client.delete(f"/admin/products/{p.id}", headers=auth_headers)
        assert resp.status_code == 409

    async def test_404_on_missing(self, client, auth_headers):
        resp = await client.delete(f"/admin/products/{uuid.uuid4()}", headers=auth_headers)
        assert resp.status_code == 404

    async def test_requires_auth(self, client, db_engine):
        c = await _make_collection(db_engine)
        p = await _make_product(db_engine, c.id)
        resp = await client.delete(f"/admin/products/{p.id}")
        assert resp.status_code == 401
