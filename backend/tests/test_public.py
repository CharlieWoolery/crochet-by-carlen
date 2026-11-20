from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

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


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


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
        status=ProductStatus.live,
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
# GET /collections
# ---------------------------------------------------------------------------


class TestListCollections:
    async def test_returns_live_open_collection(self, client, db_engine):
        await _make_collection(db_engine, name="Fall 2026", slug="fall-2026")
        resp = await client.get("/collections")
        assert resp.status_code == 200
        slugs = [c["slug"] for c in resp.json()]
        assert "fall-2026" in slugs

    async def test_excludes_draft_collections(self, client, db_engine):
        await _make_collection(
            db_engine, name="Draft", slug="draft-col", status=CollectionStatus.draft
        )
        resp = await client.get("/collections")
        assert resp.status_code == 200
        assert "draft-col" not in [c["slug"] for c in resp.json()]

    async def test_excludes_archived_collections(self, client, db_engine):
        await _make_collection(
            db_engine, name="Old", slug="old-col", status=CollectionStatus.archived
        )
        resp = await client.get("/collections")
        assert "old-col" not in [c["slug"] for c in resp.json()]

    async def test_excludes_collection_not_yet_open(self, client, db_engine):
        future = _now() + timedelta(days=1)
        await _make_collection(
            db_engine, name="Coming Soon", slug="coming-soon", opens_at=future
        )
        resp = await client.get("/collections")
        assert "coming-soon" not in [c["slug"] for c in resp.json()]

    async def test_excludes_collection_already_closed(self, client, db_engine):
        past = _now() - timedelta(days=1)
        await _make_collection(
            db_engine, name="Closed", slug="closed-col", closes_at=past
        )
        resp = await client.get("/collections")
        assert "closed-col" not in [c["slug"] for c in resp.json()]

    async def test_includes_collection_with_no_dates(self, client, db_engine):
        await _make_collection(
            db_engine,
            name="Always Open",
            slug="always-open",
            opens_at=None,
            closes_at=None,
        )
        resp = await client.get("/collections")
        assert "always-open" in [c["slug"] for c in resp.json()]

    async def test_response_fields(self, client, db_engine):
        await _make_collection(db_engine, description="Autumn vibes")
        resp = await client.get("/collections")
        c = resp.json()[0]
        for field in ("id", "name", "slug", "description", "opens_at", "closes_at"):
            assert field in c

    async def test_no_auth_required(self, client):
        resp = await client.get("/collections")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# GET /collections/archived
# ---------------------------------------------------------------------------


class TestListArchivedCollections:
    async def test_returns_archived_collections(self, client, db_engine):
        await _make_collection(
            db_engine, name="Past", slug="past-col", status=CollectionStatus.archived
        )
        resp = await client.get("/collections/archived")
        assert resp.status_code == 200
        assert "past-col" in [c["slug"] for c in resp.json()]

    async def test_excludes_live_collections(self, client, db_engine):
        await _make_collection(
            db_engine, name="Live", slug="live-col", status=CollectionStatus.live
        )
        resp = await client.get("/collections/archived")
        assert "live-col" not in [c["slug"] for c in resp.json()]

    async def test_excludes_draft_collections(self, client, db_engine):
        await _make_collection(
            db_engine, name="Draft", slug="draft-col2", status=CollectionStatus.draft
        )
        resp = await client.get("/collections/archived")
        assert "draft-col2" not in [c["slug"] for c in resp.json()]

    async def test_no_auth_required(self, client):
        resp = await client.get("/collections/archived")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# GET /products?collection=
# ---------------------------------------------------------------------------


class TestListProducts:
    async def test_returns_live_products(self, client, db_engine):
        c = await _make_collection(db_engine)
        p = await _make_product(db_engine, c.id)
        resp = await client.get("/products?collection=fall-2026")
        assert resp.status_code == 200
        assert str(p.id) in [item["id"] for item in resp.json()]

    async def test_draft_products_hidden(self, client, db_engine):
        """Draft products must never appear in the public API."""
        c = await _make_collection(db_engine)
        live_p = await _make_product(
            db_engine, c.id, name="Live", slug="live-p", status=ProductStatus.live
        )
        draft_p = await _make_product(
            db_engine, c.id, name="Draft", slug="draft-p", status=ProductStatus.draft
        )
        resp = await client.get("/products?collection=fall-2026")
        assert resp.status_code == 200
        ids = [item["id"] for item in resp.json()]
        assert str(live_p.id) in ids
        assert str(draft_p.id) not in ids, "Draft product must not appear in public API"

    async def test_archived_products_hidden(self, client, db_engine):
        c = await _make_collection(db_engine)
        await _make_product(
            db_engine, c.id, name="Old", slug="old-p", status=ProductStatus.archived
        )
        resp = await client.get("/products?collection=fall-2026")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_images_sorted_by_sort_order(self, client, db_engine):
        c = await _make_collection(db_engine)
        p = await _make_product(db_engine, c.id)
        await _make_image(db_engine, p.id, sort_order=2)
        await _make_image(db_engine, p.id, sort_order=0)
        await _make_image(db_engine, p.id, sort_order=1)
        resp = await client.get("/products?collection=fall-2026")
        images = resp.json()[0]["images"]
        assert [img["sort_order"] for img in images] == [0, 1, 2]

    async def test_includes_focal_points(self, client, db_engine):
        c = await _make_collection(db_engine)
        p = await _make_product(db_engine, c.id)
        await _make_image(db_engine, p.id, focal_x=30, focal_y=70)
        resp = await client.get("/products?collection=fall-2026")
        image = resp.json()[0]["images"][0]
        assert image["focal_x"] == 30
        assert image["focal_y"] == 70

    async def test_includes_variants(self, client, db_engine):
        c = await _make_collection(db_engine)
        p = await _make_product(db_engine, c.id)
        await _make_variant(db_engine, p.id, name="Blue", swatch_hex="#0000FF")
        resp = await client.get("/products?collection=fall-2026")
        variants = resp.json()[0]["variants"]
        assert len(variants) == 1
        assert variants[0]["name"] == "Blue"
        assert variants[0]["swatch_hex"] == "#0000FF"

    async def test_works_for_archived_collection(self, client, db_engine):
        # Archived collections are visible in the past-work gallery
        c = await _make_collection(
            db_engine, slug="past-col", status=CollectionStatus.archived
        )
        p = await _make_product(db_engine, c.id)
        resp = await client.get("/products?collection=past-col")
        assert resp.status_code == 200
        assert str(p.id) in [item["id"] for item in resp.json()]

    async def test_404_for_unknown_collection(self, client):
        resp = await client.get("/products?collection=no-such-collection")
        assert resp.status_code == 404

    async def test_404_for_draft_collection(self, client, db_engine):
        await _make_collection(
            db_engine,
            name="Draft Coll",
            slug="draft-coll",
            status=CollectionStatus.draft,
        )
        resp = await client.get("/products?collection=draft-coll")
        assert resp.status_code == 404

    async def test_422_when_collection_param_missing(self, client):
        resp = await client.get("/products")
        assert resp.status_code == 422

    async def test_no_auth_required(self, client, db_engine):
        await _make_collection(db_engine)
        resp = await client.get("/products?collection=fall-2026")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# GET /products/{slug}
# ---------------------------------------------------------------------------


class TestGetProduct:
    async def test_returns_live_product(self, client, db_engine):
        c = await _make_collection(db_engine)
        p = await _make_product(db_engine, c.id)
        resp = await client.get(f"/products/{p.slug}")
        assert resp.status_code == 200
        assert resp.json()["slug"] == p.slug

    async def test_404_for_draft(self, client, db_engine):
        c = await _make_collection(db_engine)
        p = await _make_product(
            db_engine, c.id, slug="draft-detail", status=ProductStatus.draft
        )
        resp = await client.get(f"/products/{p.slug}")
        assert resp.status_code == 404

    async def test_404_for_archived(self, client, db_engine):
        c = await _make_collection(db_engine)
        p = await _make_product(
            db_engine, c.id, slug="archived-detail", status=ProductStatus.archived
        )
        resp = await client.get(f"/products/{p.slug}")
        assert resp.status_code == 404

    async def test_404_for_nonexistent_slug(self, client):
        resp = await client.get("/products/no-such-product")
        assert resp.status_code == 404

    async def test_includes_images_with_focal_points(self, client, db_engine):
        c = await _make_collection(db_engine)
        p = await _make_product(db_engine, c.id)
        await _make_image(db_engine, p.id, focal_x=25, focal_y=75)
        resp = await client.get(f"/products/{p.slug}")
        images = resp.json()["images"]
        assert len(images) == 1
        assert images[0]["focal_x"] == 25
        assert images[0]["focal_y"] == 75

    async def test_images_sorted_by_sort_order(self, client, db_engine):
        c = await _make_collection(db_engine)
        p = await _make_product(db_engine, c.id)
        await _make_image(db_engine, p.id, sort_order=1)
        await _make_image(db_engine, p.id, sort_order=0)
        resp = await client.get(f"/products/{p.slug}")
        orders = [img["sort_order"] for img in resp.json()["images"]]
        assert orders == [0, 1]

    async def test_includes_variants(self, client, db_engine):
        c = await _make_collection(db_engine)
        p = await _make_product(db_engine, c.id)
        await _make_variant(db_engine, p.id, name="Red", swatch_hex="#FF0000")
        resp = await client.get(f"/products/{p.slug}")
        variants = resp.json()["variants"]
        assert len(variants) == 1
        assert variants[0]["name"] == "Red"
        assert variants[0]["swatch_hex"] == "#FF0000"

    async def test_response_includes_all_product_fields(self, client, db_engine):
        c = await _make_collection(db_engine)
        p = await _make_product(
            db_engine,
            c.id,
            materials="Merino Wool",
            dimensions="10x10 cm",
            pattern_credit="Designer Jane",
            pattern_credit_url="https://example.com",
            lead_time="1-2 weeks",
        )
        resp = await client.get(f"/products/{p.slug}")
        data = resp.json()
        assert data["materials"] == "Merino Wool"
        assert data["dimensions"] == "10x10 cm"
        assert data["pattern_credit"] == "Designer Jane"
        assert data["pattern_credit_url"] == "https://example.com"
        assert data["lead_time"] == "1-2 weeks"

    async def test_no_auth_required(self, client, db_engine):
        c = await _make_collection(db_engine)
        p = await _make_product(db_engine, c.id)
        resp = await client.get(f"/products/{p.slug}")
        assert resp.status_code == 200
