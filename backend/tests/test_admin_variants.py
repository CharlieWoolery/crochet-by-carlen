from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models.collection import Collection, CollectionStatus
from app.models.product import Product, ProductStatus
from app.models.product_image import ProductImage
from app.models.variant import OptionType, Variant

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
        description="A bag",
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


async def _make_image(db_engine, product_id: uuid.UUID, **kwargs) -> ProductImage:
    img_id = uuid.uuid4()
    defaults = dict(
        id=img_id,
        product_id=product_id,
        storage_key=f"products/{product_id}/{img_id}",
        url_small="https://test/small.webp",
        url_medium="https://test/medium.webp",
        url_large="https://test/large.webp",
        width=800,
        height=600,
        sort_order=0,
    )
    defaults.update(kwargs)
    SessionLocal = async_sessionmaker(db_engine, expire_on_commit=False)
    async with SessionLocal() as db:
        img = ProductImage(**defaults)
        db.add(img)
        await db.commit()
        await db.refresh(img)
        return img


async def _make_variant(db_engine, product_id: uuid.UUID, **kwargs) -> Variant:
    defaults = dict(
        product_id=product_id,
        name="Blue",
        option_type=OptionType.color,
    )
    defaults.update(kwargs)
    SessionLocal = async_sessionmaker(db_engine, expire_on_commit=False)
    async with SessionLocal() as db:
        v = Variant(**defaults)
        db.add(v)
        await db.commit()
        await db.refresh(v)
        return v


# ---------------------------------------------------------------------------
# POST /admin/products/{id}/variants
# ---------------------------------------------------------------------------


class TestCreateVariant:
    async def test_creates_basic_variant(self, client, auth_headers, db_engine):
        c = await _make_collection(db_engine)
        p = await _make_product(db_engine, c.id)
        resp = await client.post(
            f"/admin/products/{p.id}/variants",
            json={"name": "Blue", "option_type": "color"},
            headers=auth_headers,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Blue"
        assert data["option_type"] == "color"
        assert data["product_id"] == str(p.id)
        assert data["swatch_hex"] is None
        assert data["image_id"] is None
        assert data["price_cents"] is None

    async def test_creates_with_all_optional_fields(self, client, auth_headers, db_engine):
        c = await _make_collection(db_engine)
        p = await _make_product(db_engine, c.id)
        img = await _make_image(db_engine, p.id)
        resp = await client.post(
            f"/admin/products/{p.id}/variants",
            json={
                "name": "Pink",
                "option_type": "color",
                "swatch_hex": "#FF69B4",
                "image_id": str(img.id),
                "price_cents": 3000,
            },
            headers=auth_headers,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["swatch_hex"] == "#FF69B4"
        assert data["image_id"] == str(img.id)
        assert data["price_cents"] == 3000

    async def test_rejects_invalid_swatch_hex(self, client, auth_headers, db_engine):
        c = await _make_collection(db_engine)
        p = await _make_product(db_engine, c.id)
        for bad in ("red", "FF0000", "#GG0000", "#FF00001"):
            resp = await client.post(
                f"/admin/products/{p.id}/variants",
                json={"name": "X", "option_type": "color", "swatch_hex": bad},
                headers=auth_headers,
            )
            assert resp.status_code == 422, f"expected 422 for swatch_hex={bad!r}"

    async def test_rejects_image_from_different_product(self, client, auth_headers, db_engine):
        c = await _make_collection(db_engine)
        p1 = await _make_product(db_engine, c.id, name="P1", slug="p1")
        p2 = await _make_product(db_engine, c.id, name="P2", slug="p2")
        img_p2 = await _make_image(db_engine, p2.id)
        resp = await client.post(
            f"/admin/products/{p1.id}/variants",
            json={"name": "Blue", "option_type": "color", "image_id": str(img_p2.id)},
            headers=auth_headers,
        )
        assert resp.status_code == 422

    async def test_404_on_missing_product(self, client, auth_headers):
        resp = await client.post(
            f"/admin/products/{uuid.uuid4()}/variants",
            json={"name": "Blue", "option_type": "color"},
            headers=auth_headers,
        )
        assert resp.status_code == 404

    async def test_requires_auth(self, client, db_engine):
        c = await _make_collection(db_engine)
        p = await _make_product(db_engine, c.id)
        resp = await client.post(
            f"/admin/products/{p.id}/variants",
            json={"name": "Blue", "option_type": "color"},
        )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# PATCH /admin/variants/{id}
# ---------------------------------------------------------------------------


class TestUpdateVariant:
    async def test_updates_name(self, client, auth_headers, db_engine):
        c = await _make_collection(db_engine)
        p = await _make_product(db_engine, c.id)
        v = await _make_variant(db_engine, p.id)
        resp = await client.patch(
            f"/admin/variants/{v.id}",
            json={"name": "Lavender"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "Lavender"

    async def test_updates_option_type(self, client, auth_headers, db_engine):
        c = await _make_collection(db_engine)
        p = await _make_product(db_engine, c.id)
        v = await _make_variant(db_engine, p.id)
        resp = await client.patch(
            f"/admin/variants/{v.id}",
            json={"option_type": "material"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["option_type"] == "material"

    async def test_links_image(self, client, auth_headers, db_engine):
        c = await _make_collection(db_engine)
        p = await _make_product(db_engine, c.id)
        img = await _make_image(db_engine, p.id)
        v = await _make_variant(db_engine, p.id)
        resp = await client.patch(
            f"/admin/variants/{v.id}",
            json={"image_id": str(img.id)},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["image_id"] == str(img.id)

    async def test_clears_image_with_explicit_null(self, client, auth_headers, db_engine):
        c = await _make_collection(db_engine)
        p = await _make_product(db_engine, c.id)
        img = await _make_image(db_engine, p.id)
        v = await _make_variant(db_engine, p.id, image_id=img.id)
        resp = await client.patch(
            f"/admin/variants/{v.id}",
            json={"image_id": None},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["image_id"] is None

    async def test_clears_price_cents_with_explicit_null(self, client, auth_headers, db_engine):
        c = await _make_collection(db_engine)
        p = await _make_product(db_engine, c.id)
        v = await _make_variant(db_engine, p.id, price_cents=1500)
        resp = await client.patch(
            f"/admin/variants/{v.id}",
            json={"price_cents": None},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["price_cents"] is None

    async def test_clears_swatch_hex_with_explicit_null(self, client, auth_headers, db_engine):
        c = await _make_collection(db_engine)
        p = await _make_product(db_engine, c.id)
        v = await _make_variant(db_engine, p.id, swatch_hex="#FF0000")
        resp = await client.patch(
            f"/admin/variants/{v.id}",
            json={"swatch_hex": None},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["swatch_hex"] is None

    async def test_rejects_image_from_different_product(self, client, auth_headers, db_engine):
        c = await _make_collection(db_engine)
        p1 = await _make_product(db_engine, c.id, name="P1", slug="p1")
        p2 = await _make_product(db_engine, c.id, name="P2", slug="p2")
        img_p2 = await _make_image(db_engine, p2.id)
        v = await _make_variant(db_engine, p1.id)
        resp = await client.patch(
            f"/admin/variants/{v.id}",
            json={"image_id": str(img_p2.id)},
            headers=auth_headers,
        )
        assert resp.status_code == 422

    async def test_unset_fields_not_touched(self, client, auth_headers, db_engine):
        c = await _make_collection(db_engine)
        p = await _make_product(db_engine, c.id)
        v = await _make_variant(db_engine, p.id, swatch_hex="#AABBCC", price_cents=800)
        resp = await client.patch(
            f"/admin/variants/{v.id}",
            json={"name": "Updated"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["swatch_hex"] == "#AABBCC"
        assert data["price_cents"] == 800

    async def test_404_on_missing(self, client, auth_headers):
        resp = await client.patch(
            f"/admin/variants/{uuid.uuid4()}",
            json={"name": "x"},
            headers=auth_headers,
        )
        assert resp.status_code == 404

    async def test_requires_auth(self, client, db_engine):
        c = await _make_collection(db_engine)
        p = await _make_product(db_engine, c.id)
        v = await _make_variant(db_engine, p.id)
        resp = await client.patch(f"/admin/variants/{v.id}", json={"name": "x"})
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# DELETE /admin/variants/{id}
# ---------------------------------------------------------------------------


class TestDeleteVariant:
    async def test_deletes_variant(self, client, auth_headers, db_engine):
        c = await _make_collection(db_engine)
        p = await _make_product(db_engine, c.id)
        v = await _make_variant(db_engine, p.id)
        resp = await client.delete(f"/admin/variants/{v.id}", headers=auth_headers)
        assert resp.status_code == 204
        # Confirm gone
        resp2 = await client.patch(
            f"/admin/variants/{v.id}", json={"name": "x"}, headers=auth_headers
        )
        assert resp2.status_code == 404

    async def test_404_on_missing(self, client, auth_headers):
        resp = await client.delete(f"/admin/variants/{uuid.uuid4()}", headers=auth_headers)
        assert resp.status_code == 404

    async def test_requires_auth(self, client, db_engine):
        c = await _make_collection(db_engine)
        p = await _make_product(db_engine, c.id)
        v = await _make_variant(db_engine, p.id)
        resp = await client.delete(f"/admin/variants/{v.id}")
        assert resp.status_code == 401
