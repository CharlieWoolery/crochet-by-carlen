from __future__ import annotations

import uuid
from io import BytesIO

import pytest
import pytest_asyncio
from PIL import Image
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models.collection import Collection, CollectionStatus
from app.models.product import Product, ProductStatus
from app.models.product_image import ProductImage

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_jpeg(width: int = 800, height: int = 600) -> bytes:
    img = Image.new("RGB", (width, height), color=(100, 150, 200))
    buf = BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


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


async def _make_image(db_engine, product_id: uuid.UUID, sort_order: int = 0, **kwargs) -> ProductImage:
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
        sort_order=sort_order,
    )
    defaults.update(kwargs)
    SessionLocal = async_sessionmaker(db_engine, expire_on_commit=False)
    async with SessionLocal() as db:
        img = ProductImage(**defaults)
        db.add(img)
        await db.commit()
        await db.refresh(img)
        return img


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_upload(monkeypatch):
    """Patch storage.upload; returns a list of (key, len(data)) tuples uploaded."""
    calls: list[tuple[str, int]] = []

    def fake(key: str, data: bytes, content_type: str = "image/webp") -> str:
        calls.append((key, len(data)))
        return f"https://storage.test/{key}"

    monkeypatch.setattr("app.images.storage.upload", fake)
    return calls


@pytest.fixture
def mock_delete_keys(monkeypatch):
    """Patch storage.delete_keys; returns a list of deleted keys."""
    deleted: list[str] = []

    def fake(keys: list[str]) -> None:
        deleted.extend(keys)

    monkeypatch.setattr("app.images.storage.delete_keys", fake)
    return deleted


# ---------------------------------------------------------------------------
# POST /admin/products/{id}/images
# ---------------------------------------------------------------------------


class TestUploadImage:
    async def test_returns_201_with_image_data(self, client, auth_headers, db_engine, mock_upload):
        c = await _make_collection(db_engine)
        p = await _make_product(db_engine, c.id)
        resp = await client.post(
            f"/admin/products/{p.id}/images",
            files={"file": ("photo.jpg", _make_jpeg(), "image/jpeg")},
            headers=auth_headers,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["product_id"] == str(p.id)
        assert data["url_small"].startswith("https://storage.test/")
        assert data["url_medium"].startswith("https://storage.test/")
        assert data["url_large"].startswith("https://storage.test/")

    async def test_uploads_all_three_sizes(self, client, auth_headers, db_engine, mock_upload):
        c = await _make_collection(db_engine)
        p = await _make_product(db_engine, c.id)
        await client.post(
            f"/admin/products/{p.id}/images",
            files={"file": ("photo.jpg", _make_jpeg(), "image/jpeg")},
            headers=auth_headers,
        )
        keys = [k for k, _ in mock_upload]
        assert any(k.endswith("/small.webp") for k in keys)
        assert any(k.endswith("/medium.webp") for k in keys)
        assert any(k.endswith("/large.webp") for k in keys)

    async def test_storage_key_uses_product_and_image_ids(self, client, auth_headers, db_engine, mock_upload):
        c = await _make_collection(db_engine)
        p = await _make_product(db_engine, c.id)
        resp = await client.post(
            f"/admin/products/{p.id}/images",
            files={"file": ("photo.jpg", _make_jpeg(), "image/jpeg")},
            headers=auth_headers,
        )
        data = resp.json()
        assert data["storage_key"].startswith(f"products/{p.id}/")

    async def test_stores_processed_dimensions(self, client, auth_headers, db_engine, mock_upload):
        c = await _make_collection(db_engine)
        p = await _make_product(db_engine, c.id)
        resp = await client.post(
            f"/admin/products/{p.id}/images",
            files={"file": ("photo.jpg", _make_jpeg(1200, 900), "image/jpeg")},
            headers=auth_headers,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["width"] == 1200
        assert data["height"] == 900

    async def test_first_image_gets_sort_order_zero(self, client, auth_headers, db_engine, mock_upload):
        c = await _make_collection(db_engine)
        p = await _make_product(db_engine, c.id)
        resp = await client.post(
            f"/admin/products/{p.id}/images",
            files={"file": ("photo.jpg", _make_jpeg(), "image/jpeg")},
            headers=auth_headers,
        )
        assert resp.json()["sort_order"] == 0

    async def test_subsequent_images_increment_sort_order(self, client, auth_headers, db_engine, mock_upload):
        c = await _make_collection(db_engine)
        p = await _make_product(db_engine, c.id)
        jpeg = _make_jpeg()
        for _ in range(3):
            await client.post(
                f"/admin/products/{p.id}/images",
                files={"file": ("photo.jpg", jpeg, "image/jpeg")},
                headers=auth_headers,
            )
        resp = await client.post(
            f"/admin/products/{p.id}/images",
            files={"file": ("photo.jpg", jpeg, "image/jpeg")},
            headers=auth_headers,
        )
        assert resp.json()["sort_order"] == 3

    async def test_default_focal_point_is_50_50(self, client, auth_headers, db_engine, mock_upload):
        c = await _make_collection(db_engine)
        p = await _make_product(db_engine, c.id)
        resp = await client.post(
            f"/admin/products/{p.id}/images",
            files={"file": ("photo.jpg", _make_jpeg(), "image/jpeg")},
            headers=auth_headers,
        )
        data = resp.json()
        assert data["focal_x"] == 50
        assert data["focal_y"] == 50

    async def test_rejects_unsupported_content_type(self, client, auth_headers, db_engine, mock_upload):
        c = await _make_collection(db_engine)
        p = await _make_product(db_engine, c.id)
        resp = await client.post(
            f"/admin/products/{p.id}/images",
            files={"file": ("doc.pdf", b"%PDF", "application/pdf")},
            headers=auth_headers,
        )
        assert resp.status_code == 422

    async def test_rejects_corrupt_file(self, client, auth_headers, db_engine, mock_upload):
        c = await _make_collection(db_engine)
        p = await _make_product(db_engine, c.id)
        resp = await client.post(
            f"/admin/products/{p.id}/images",
            files={"file": ("bad.jpg", b"not image data", "image/jpeg")},
            headers=auth_headers,
        )
        assert resp.status_code == 422

    async def test_404_on_missing_product(self, client, auth_headers, mock_upload):
        resp = await client.post(
            f"/admin/products/{uuid.uuid4()}/images",
            files={"file": ("photo.jpg", _make_jpeg(), "image/jpeg")},
            headers=auth_headers,
        )
        assert resp.status_code == 404

    async def test_requires_auth(self, client, db_engine):
        c = await _make_collection(db_engine)
        p = await _make_product(db_engine, c.id)
        resp = await client.post(
            f"/admin/products/{p.id}/images",
            files={"file": ("photo.jpg", _make_jpeg(), "image/jpeg")},
        )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# PATCH /admin/images/{id}
# ---------------------------------------------------------------------------


class TestUpdateImage:
    async def test_updates_focal_x(self, client, auth_headers, db_engine):
        c = await _make_collection(db_engine)
        p = await _make_product(db_engine, c.id)
        img = await _make_image(db_engine, p.id)
        resp = await client.patch(
            f"/admin/images/{img.id}",
            json={"focal_x": 75},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["focal_x"] == 75

    async def test_updates_focal_y(self, client, auth_headers, db_engine):
        c = await _make_collection(db_engine)
        p = await _make_product(db_engine, c.id)
        img = await _make_image(db_engine, p.id)
        resp = await client.patch(
            f"/admin/images/{img.id}",
            json={"focal_y": 25},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["focal_y"] == 25

    async def test_updates_alt_text(self, client, auth_headers, db_engine):
        c = await _make_collection(db_engine)
        p = await _make_product(db_engine, c.id)
        img = await _make_image(db_engine, p.id)
        resp = await client.patch(
            f"/admin/images/{img.id}",
            json={"alt_text": "A green tote bag"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["alt_text"] == "A green tote bag"

    async def test_clears_alt_text_with_explicit_null(self, client, auth_headers, db_engine):
        c = await _make_collection(db_engine)
        p = await _make_product(db_engine, c.id)
        img = await _make_image(db_engine, p.id, alt_text="existing text")
        resp = await client.patch(
            f"/admin/images/{img.id}",
            json={"alt_text": None},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["alt_text"] is None

    async def test_focal_out_of_range_returns_422(self, client, auth_headers, db_engine):
        c = await _make_collection(db_engine)
        p = await _make_product(db_engine, c.id)
        img = await _make_image(db_engine, p.id)
        resp = await client.patch(
            f"/admin/images/{img.id}",
            json={"focal_x": 101},
            headers=auth_headers,
        )
        assert resp.status_code == 422

    async def test_focal_negative_returns_422(self, client, auth_headers, db_engine):
        c = await _make_collection(db_engine)
        p = await _make_product(db_engine, c.id)
        img = await _make_image(db_engine, p.id)
        resp = await client.patch(
            f"/admin/images/{img.id}",
            json={"focal_y": -1},
            headers=auth_headers,
        )
        assert resp.status_code == 422

    async def test_unset_fields_are_not_touched(self, client, auth_headers, db_engine):
        c = await _make_collection(db_engine)
        p = await _make_product(db_engine, c.id)
        img = await _make_image(db_engine, p.id, alt_text="keep me")
        resp = await client.patch(
            f"/admin/images/{img.id}",
            json={"focal_x": 20},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["alt_text"] == "keep me"

    async def test_404_on_missing(self, client, auth_headers):
        resp = await client.patch(
            f"/admin/images/{uuid.uuid4()}",
            json={"focal_x": 50},
            headers=auth_headers,
        )
        assert resp.status_code == 404

    async def test_requires_auth(self, client, db_engine):
        c = await _make_collection(db_engine)
        p = await _make_product(db_engine, c.id)
        img = await _make_image(db_engine, p.id)
        resp = await client.patch(f"/admin/images/{img.id}", json={"focal_x": 50})
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# PUT /admin/products/{id}/images/order
# ---------------------------------------------------------------------------


class TestReorderImages:
    async def test_updates_sort_orders(self, client, auth_headers, db_engine):
        c = await _make_collection(db_engine)
        p = await _make_product(db_engine, c.id)
        a = await _make_image(db_engine, p.id, sort_order=0)
        b = await _make_image(db_engine, p.id, sort_order=1)
        c_ = await _make_image(db_engine, p.id, sort_order=2)

        resp = await client.put(
            f"/admin/products/{p.id}/images/order",
            json={"image_ids": [str(c_.id), str(b.id), str(a.id)]},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data[0]["id"] == str(c_.id)
        assert data[0]["sort_order"] == 0
        assert data[1]["id"] == str(b.id)
        assert data[1]["sort_order"] == 1
        assert data[2]["id"] == str(a.id)
        assert data[2]["sort_order"] == 2

    async def test_rejects_id_from_different_product(self, client, auth_headers, db_engine):
        c = await _make_collection(db_engine)
        p1 = await _make_product(db_engine, c.id, name="P1", slug="p1")
        p2 = await _make_product(db_engine, c.id, name="P2", slug="p2")
        img_p1 = await _make_image(db_engine, p1.id)
        img_p2 = await _make_image(db_engine, p2.id)

        resp = await client.put(
            f"/admin/products/{p1.id}/images/order",
            # img_p2 belongs to a different product
            json={"image_ids": [str(img_p2.id)]},
            headers=auth_headers,
        )
        assert resp.status_code == 422

    async def test_rejects_duplicate_ids(self, client, auth_headers, db_engine):
        c = await _make_collection(db_engine)
        p = await _make_product(db_engine, c.id)
        img = await _make_image(db_engine, p.id)

        resp = await client.put(
            f"/admin/products/{p.id}/images/order",
            json={"image_ids": [str(img.id), str(img.id)]},
            headers=auth_headers,
        )
        assert resp.status_code == 422

    async def test_rejects_missing_ids(self, client, auth_headers, db_engine):
        """Submitting fewer IDs than the product has must be rejected."""
        c = await _make_collection(db_engine)
        p = await _make_product(db_engine, c.id)
        await _make_image(db_engine, p.id, sort_order=0)
        b = await _make_image(db_engine, p.id, sort_order=1)

        resp = await client.put(
            f"/admin/products/{p.id}/images/order",
            json={"image_ids": [str(b.id)]},  # missing first image
            headers=auth_headers,
        )
        assert resp.status_code == 422

    async def test_404_on_missing_product(self, client, auth_headers):
        resp = await client.put(
            f"/admin/products/{uuid.uuid4()}/images/order",
            json={"image_ids": []},
            headers=auth_headers,
        )
        assert resp.status_code == 404

    async def test_requires_auth(self, client, db_engine):
        c = await _make_collection(db_engine)
        p = await _make_product(db_engine, c.id)
        resp = await client.put(
            f"/admin/products/{p.id}/images/order",
            json={"image_ids": []},
        )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# DELETE /admin/images/{id}
# ---------------------------------------------------------------------------


class TestDeleteImage:
    async def test_returns_204(self, client, auth_headers, db_engine, mock_delete_keys):
        c = await _make_collection(db_engine)
        p = await _make_product(db_engine, c.id)
        img = await _make_image(db_engine, p.id)
        resp = await client.delete(f"/admin/images/{img.id}", headers=auth_headers)
        assert resp.status_code == 204

    async def test_removes_row_from_db(self, client, auth_headers, db_engine, mock_delete_keys):
        c = await _make_collection(db_engine)
        p = await _make_product(db_engine, c.id)
        img = await _make_image(db_engine, p.id)
        await client.delete(f"/admin/images/{img.id}", headers=auth_headers)

        resp = await client.patch(
            f"/admin/images/{img.id}",
            json={"focal_x": 50},
            headers=auth_headers,
        )
        assert resp.status_code == 404

    async def test_deletes_all_three_storage_keys(self, client, auth_headers, db_engine, mock_delete_keys):
        c = await _make_collection(db_engine)
        p = await _make_product(db_engine, c.id)
        storage_key = f"products/{p.id}/abc123"
        img = await _make_image(db_engine, p.id, storage_key=storage_key)

        await client.delete(f"/admin/images/{img.id}", headers=auth_headers)

        assert f"{storage_key}/small.webp" in mock_delete_keys
        assert f"{storage_key}/medium.webp" in mock_delete_keys
        assert f"{storage_key}/large.webp" in mock_delete_keys
        assert len(mock_delete_keys) == 3

    async def test_404_on_missing(self, client, auth_headers, mock_delete_keys):
        resp = await client.delete(f"/admin/images/{uuid.uuid4()}", headers=auth_headers)
        assert resp.status_code == 404

    async def test_requires_auth(self, client, db_engine):
        c = await _make_collection(db_engine)
        p = await _make_product(db_engine, c.id)
        img = await _make_image(db_engine, p.id)
        resp = await client.delete(f"/admin/images/{img.id}")
        assert resp.status_code == 401
