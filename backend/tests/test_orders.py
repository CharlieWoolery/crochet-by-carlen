from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models.collection import Collection, CollectionStatus
from app.models.order import FulfillmentMethod, Order, OrderItem, PaymentStatus
from app.models.product import Product, ProductStatus
from app.models.product_image import ProductImage
from app.models.settings import Settings, _SETTINGS_ID
from app.models.variant import OptionType, Variant


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now() -> datetime:
    return datetime.now(timezone.utc)


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


async def _make_settings(db_engine, **kwargs) -> Settings:
    defaults = dict(
        id=_SETTINGS_ID,
        shipping_flat_cents=600,
        dropoff_fee_cents=0,
    )
    defaults.update(kwargs)
    SessionLocal = async_sessionmaker(db_engine, expire_on_commit=False)
    async with SessionLocal() as db:
        s = Settings(**defaults)
        db.add(s)
        await db.commit()
        await db.refresh(s)
        return s


def _order_payload(**kwargs) -> dict:
    """Minimal valid order payload (ship, single item)."""
    base = {
        "customer_name": "Jane Smith",
        "customer_email": "jane@example.com",
        "fulfillment_method": "ship",
        "address": "123 Main St, Springfield",
        "items": [],
    }
    base.update(kwargs)
    return base


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


class TestCreateOrderHappyPath:
    async def test_returns_201_with_order_number(self, client, db_engine):
        c = await _make_collection(db_engine)
        p = await _make_product(db_engine, c.id)
        payload = _order_payload(items=[{"product_id": str(p.id), "quantity": 1}])
        resp = await client.post("/orders", json=payload)
        assert resp.status_code == 201
        data = resp.json()
        assert data["order_number"].startswith("CBC-")

    async def test_order_number_format(self, client, db_engine):
        c = await _make_collection(db_engine)
        p = await _make_product(db_engine, c.id)
        payload = _order_payload(items=[{"product_id": str(p.id), "quantity": 1}])
        resp = await client.post("/orders", json=payload)
        import re
        assert re.match(r"^CBC-\d+$", resp.json()["order_number"])

    async def test_computes_subtotal_from_product_price(self, client, db_engine):
        c = await _make_collection(db_engine)
        p = await _make_product(db_engine, c.id, price_cents=1500)
        payload = _order_payload(items=[{"product_id": str(p.id), "quantity": 2}])
        resp = await client.post("/orders", json=payload)
        assert resp.json()["subtotal_cents"] == 3000

    async def test_shipping_fee_from_settings(self, client, db_engine):
        await _make_settings(db_engine, shipping_flat_cents=800)
        c = await _make_collection(db_engine)
        p = await _make_product(db_engine, c.id, price_cents=1000)
        payload = _order_payload(items=[{"product_id": str(p.id), "quantity": 1}])
        resp = await client.post("/orders", json=payload)
        data = resp.json()
        assert data["fulfillment_fee_cents"] == 800
        assert data["total_cents"] == 1800

    async def test_shipping_fee_flat_per_order_not_per_item(self, client, db_engine):
        await _make_settings(db_engine, shipping_flat_cents=600)
        c = await _make_collection(db_engine)
        p = await _make_product(db_engine, c.id, price_cents=1000)
        payload = _order_payload(items=[{"product_id": str(p.id), "quantity": 3}])
        resp = await client.post("/orders", json=payload)
        # Shipping is $6 flat, not 3×$6
        assert resp.json()["fulfillment_fee_cents"] == 600

    async def test_dropoff_fee_from_settings(self, client, db_engine):
        await _make_settings(db_engine, dropoff_fee_cents=250)
        c = await _make_collection(db_engine)
        p = await _make_product(db_engine, c.id, price_cents=1000)
        payload = _order_payload(
            fulfillment_method="dropoff",
            address="456 Oak Ave",
            items=[{"product_id": str(p.id), "quantity": 1}],
        )
        resp = await client.post("/orders", json=payload)
        assert resp.json()["fulfillment_fee_cents"] == 250

    async def test_pickup_has_no_fulfillment_fee(self, client, db_engine):
        await _make_settings(db_engine, shipping_flat_cents=600)
        c = await _make_collection(db_engine)
        p = await _make_product(db_engine, c.id, price_cents=1000)
        payload = _order_payload(
            fulfillment_method="pickup",
            address=None,
            items=[{"product_id": str(p.id), "quantity": 1}],
        )
        resp = await client.post("/orders", json=payload)
        assert resp.json()["fulfillment_fee_cents"] == 0
        assert resp.json()["total_cents"] == 1000

    async def test_uses_default_shipping_when_no_settings_row(self, client, db_engine):
        # No settings row → defaults: shipping_flat_cents=600
        c = await _make_collection(db_engine)
        p = await _make_product(db_engine, c.id, price_cents=1000)
        payload = _order_payload(items=[{"product_id": str(p.id), "quantity": 1}])
        resp = await client.post("/orders", json=payload)
        assert resp.json()["fulfillment_fee_cents"] == 600

    async def test_variant_price_overrides_product_price(self, client, db_engine):
        c = await _make_collection(db_engine)
        p = await _make_product(db_engine, c.id, price_cents=2000)
        v = await _make_variant(db_engine, p.id, price_cents=3000)
        payload = _order_payload(
            items=[{"product_id": str(p.id), "variant_id": str(v.id), "quantity": 1}]
        )
        resp = await client.post("/orders", json=payload)
        assert resp.json()["subtotal_cents"] == 3000

    async def test_product_price_used_when_variant_has_no_override(self, client, db_engine):
        c = await _make_collection(db_engine)
        p = await _make_product(db_engine, c.id, price_cents=2000)
        v = await _make_variant(db_engine, p.id, price_cents=None)
        payload = _order_payload(
            items=[{"product_id": str(p.id), "variant_id": str(v.id), "quantity": 1}]
        )
        resp = await client.post("/orders", json=payload)
        assert resp.json()["subtotal_cents"] == 2000

    async def test_order_saved_to_db(self, client, db_engine):
        c = await _make_collection(db_engine)
        p = await _make_product(db_engine, c.id)
        payload = _order_payload(items=[{"product_id": str(p.id), "quantity": 1}])
        resp = await client.post("/orders", json=payload)
        order_number = resp.json()["order_number"]
        SessionLocal = async_sessionmaker(db_engine, expire_on_commit=False)
        async with SessionLocal() as db:
            result = await db.execute(
                select(Order).where(Order.order_number == order_number)
            )
            order = result.scalar_one_or_none()
        assert order is not None
        assert order.payment_status == PaymentStatus.unpaid

    async def test_items_snapshot_price(self, client, db_engine):
        """Unit price in the order item is a snapshot, frozen at order time."""
        c = await _make_collection(db_engine)
        p = await _make_product(db_engine, c.id, price_cents=5000)
        payload = _order_payload(items=[{"product_id": str(p.id), "quantity": 2}])
        resp = await client.post("/orders", json=payload)
        items = resp.json()["items"]
        assert len(items) == 1
        assert items[0]["unit_price_cents"] == 5000
        assert items[0]["quantity"] == 2

    async def test_response_contains_expected_fields(self, client, db_engine):
        c = await _make_collection(db_engine)
        p = await _make_product(db_engine, c.id)
        payload = _order_payload(
            customer_name="Alice",
            customer_email="alice@test.com",
            customer_phone="555-1234",
            items=[{"product_id": str(p.id), "quantity": 1}],
        )
        resp = await client.post("/orders", json=payload)
        data = resp.json()
        assert data["customer_name"] == "Alice"
        assert data["customer_email"] == "alice@test.com"
        assert data["customer_phone"] == "555-1234"
        assert data["payment_status"] == "unpaid"
        assert "id" in data
        assert "created_at" in data

    async def test_confirmation_email_sent(self, client, db_engine):
        c = await _make_collection(db_engine)
        p = await _make_product(db_engine, c.id)
        payload = _order_payload(items=[{"product_id": str(p.id), "quantity": 1}])
        with patch("app.routers.orders.send_order_confirmation", new_callable=AsyncMock) as mock_email:
            resp = await client.post("/orders", json=payload)
        assert resp.status_code == 201
        mock_email.assert_called_once()
        call_data = mock_email.call_args[0][0]
        assert call_data.order_number == resp.json()["order_number"]
        assert call_data.customer_email == "jane@example.com"

    async def test_multiple_items_in_one_order(self, client, db_engine):
        c = await _make_collection(db_engine)
        p1 = await _make_product(db_engine, c.id, name="Bag", slug="bag", price_cents=2000)
        p2 = await _make_product(db_engine, c.id, name="Hat", slug="hat", price_cents=1500)
        payload = _order_payload(
            items=[
                {"product_id": str(p1.id), "quantity": 1},
                {"product_id": str(p2.id), "quantity": 2},
            ]
        )
        resp = await client.post("/orders", json=payload)
        assert resp.status_code == 201
        # subtotal = 2000 + 2×1500 = 5000
        assert resp.json()["subtotal_cents"] == 5000
        assert len(resp.json()["items"]) == 2


# ---------------------------------------------------------------------------
# Input validation (422)
# ---------------------------------------------------------------------------


class TestOrderInputValidation:
    async def test_ship_without_address_returns_422(self, client, db_engine):
        c = await _make_collection(db_engine)
        p = await _make_product(db_engine, c.id)
        payload = _order_payload(
            fulfillment_method="ship",
            address=None,
            items=[{"product_id": str(p.id), "quantity": 1}],
        )
        resp = await client.post("/orders", json=payload)
        assert resp.status_code == 422

    async def test_dropoff_without_address_returns_422(self, client, db_engine):
        c = await _make_collection(db_engine)
        p = await _make_product(db_engine, c.id)
        payload = _order_payload(
            fulfillment_method="dropoff",
            address=None,
            items=[{"product_id": str(p.id), "quantity": 1}],
        )
        resp = await client.post("/orders", json=payload)
        assert resp.status_code == 422

    async def test_pickup_without_address_is_valid(self, client, db_engine):
        c = await _make_collection(db_engine)
        p = await _make_product(db_engine, c.id)
        payload = _order_payload(
            fulfillment_method="pickup",
            address=None,
            items=[{"product_id": str(p.id), "quantity": 1}],
        )
        resp = await client.post("/orders", json=payload)
        assert resp.status_code == 201

    async def test_empty_items_list_returns_422(self, client, db_engine):
        payload = _order_payload(items=[])
        resp = await client.post("/orders", json=payload)
        assert resp.status_code == 422

    async def test_zero_quantity_returns_422(self, client, db_engine):
        c = await _make_collection(db_engine)
        p = await _make_product(db_engine, c.id)
        payload = _order_payload(items=[{"product_id": str(p.id), "quantity": 0}])
        resp = await client.post("/orders", json=payload)
        assert resp.status_code == 422

    async def test_invalid_email_returns_422(self, client, db_engine):
        c = await _make_collection(db_engine)
        p = await _make_product(db_engine, c.id)
        payload = _order_payload(
            customer_email="not-an-email",
            items=[{"product_id": str(p.id), "quantity": 1}],
        )
        resp = await client.post("/orders", json=payload)
        assert resp.status_code == 422

    async def test_blank_customer_name_returns_422(self, client, db_engine):
        c = await _make_collection(db_engine)
        p = await _make_product(db_engine, c.id)
        payload = _order_payload(
            customer_name="   ",
            items=[{"product_id": str(p.id), "quantity": 1}],
        )
        resp = await client.post("/orders", json=payload)
        assert resp.status_code == 422

    async def test_ship_with_blank_address_returns_422(self, client, db_engine):
        c = await _make_collection(db_engine)
        p = await _make_product(db_engine, c.id)
        payload = _order_payload(
            fulfillment_method="ship",
            address="   ",
            items=[{"product_id": str(p.id), "quantity": 1}],
        )
        resp = await client.post("/orders", json=payload)
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Business rule validation (409)
# ---------------------------------------------------------------------------


class TestOrderBusinessRules:
    async def test_draft_product_returns_409(self, client, db_engine):
        c = await _make_collection(db_engine)
        p = await _make_product(db_engine, c.id, status=ProductStatus.draft)
        payload = _order_payload(items=[{"product_id": str(p.id), "quantity": 1}])
        resp = await client.post("/orders", json=payload)
        assert resp.status_code == 409
        assert any("not available" in e["error"] for e in resp.json()["detail"])

    async def test_archived_product_returns_409(self, client, db_engine):
        c = await _make_collection(db_engine)
        p = await _make_product(db_engine, c.id, status=ProductStatus.archived)
        payload = _order_payload(items=[{"product_id": str(p.id), "quantity": 1}])
        resp = await client.post("/orders", json=payload)
        assert resp.status_code == 409

    async def test_nonexistent_product_returns_409(self, client):
        payload = _order_payload(
            items=[{"product_id": str(uuid.uuid4()), "quantity": 1}]
        )
        resp = await client.post("/orders", json=payload)
        assert resp.status_code == 409
        assert any("not found" in e["error"] for e in resp.json()["detail"])

    async def test_archived_collection_returns_409(self, client, db_engine):
        c = await _make_collection(db_engine, status=CollectionStatus.archived)
        p = await _make_product(db_engine, c.id)
        payload = _order_payload(items=[{"product_id": str(p.id), "quantity": 1}])
        resp = await client.post("/orders", json=payload)
        assert resp.status_code == 409
        assert any("not open" in e["error"] for e in resp.json()["detail"])

    async def test_draft_collection_returns_409(self, client, db_engine):
        c = await _make_collection(db_engine, status=CollectionStatus.draft)
        p = await _make_product(db_engine, c.id)
        payload = _order_payload(items=[{"product_id": str(p.id), "quantity": 1}])
        resp = await client.post("/orders", json=payload)
        assert resp.status_code == 409

    async def test_collection_not_yet_open_returns_409(self, client, db_engine):
        future = _now() + timedelta(days=1)
        c = await _make_collection(db_engine, opens_at=future)
        p = await _make_product(db_engine, c.id)
        payload = _order_payload(items=[{"product_id": str(p.id), "quantity": 1}])
        resp = await client.post("/orders", json=payload)
        assert resp.status_code == 409
        assert any("not opened yet" in e["error"] for e in resp.json()["detail"])

    async def test_collection_closed_returns_409(self, client, db_engine):
        past = _now() - timedelta(days=1)
        c = await _make_collection(db_engine, closes_at=past)
        p = await _make_product(db_engine, c.id)
        payload = _order_payload(items=[{"product_id": str(p.id), "quantity": 1}])
        resp = await client.post("/orders", json=payload)
        assert resp.status_code == 409
        assert any("closed" in e["error"] for e in resp.json()["detail"])

    async def test_order_cap_exceeded_returns_409(self, client, db_engine):
        c = await _make_collection(db_engine)
        p = await _make_product(db_engine, c.id, order_cap=2)
        # Pre-fill cap: create an existing order item directly
        SessionLocal = async_sessionmaker(db_engine, expire_on_commit=False)
        async with SessionLocal() as db:
            # Create a minimal Order row to satisfy the FK
            existing_order = Order(
                order_number="CBC-9000",
                customer_name="Existing",
                customer_email="existing@test.com",
                fulfillment_method=FulfillmentMethod.pickup,
                subtotal_cents=0,
                fulfillment_fee_cents=0,
                total_cents=0,
            )
            db.add(existing_order)
            await db.flush()
            db.add(OrderItem(
                order_id=existing_order.id,
                product_id=p.id,
                quantity=2,
                unit_price_cents=p.price_cents,
            ))
            await db.commit()
        # Trying to order 1 more should fail
        payload = _order_payload(items=[{"product_id": str(p.id), "quantity": 1}])
        resp = await client.post("/orders", json=payload)
        assert resp.status_code == 409
        assert any("cap" in e["error"] for e in resp.json()["detail"])

    async def test_order_cap_not_exceeded_succeeds(self, client, db_engine):
        c = await _make_collection(db_engine)
        p = await _make_product(db_engine, c.id, order_cap=5)
        payload = _order_payload(items=[{"product_id": str(p.id), "quantity": 3}])
        resp = await client.post("/orders", json=payload)
        assert resp.status_code == 201

    async def test_no_cap_allows_any_quantity(self, client, db_engine):
        c = await _make_collection(db_engine)
        p = await _make_product(db_engine, c.id, order_cap=None)
        payload = _order_payload(items=[{"product_id": str(p.id), "quantity": 100}])
        resp = await client.post("/orders", json=payload)
        assert resp.status_code == 201

    async def test_invalid_variant_returns_409(self, client, db_engine):
        c = await _make_collection(db_engine)
        p1 = await _make_product(db_engine, c.id, name="P1", slug="p1")
        p2 = await _make_product(db_engine, c.id, name="P2", slug="p2")
        v2 = await _make_variant(db_engine, p2.id)
        # Send variant from p2 with product p1
        payload = _order_payload(
            items=[{"product_id": str(p1.id), "variant_id": str(v2.id), "quantity": 1}]
        )
        resp = await client.post("/orders", json=payload)
        assert resp.status_code == 409
        assert any("variant" in e["error"] for e in resp.json()["detail"])

    async def test_nonexistent_variant_returns_409(self, client, db_engine):
        c = await _make_collection(db_engine)
        p = await _make_product(db_engine, c.id)
        payload = _order_payload(
            items=[{"product_id": str(p.id), "variant_id": str(uuid.uuid4()), "quantity": 1}]
        )
        resp = await client.post("/orders", json=payload)
        assert resp.status_code == 409

    async def test_multiple_errors_returned_in_one_409(self, client, db_engine):
        """All invalid items are reported together, not just the first one."""
        c = await _make_collection(db_engine)
        draft = await _make_product(db_engine, c.id, name="Draft", slug="d1", status=ProductStatus.draft)
        archived = await _make_product(db_engine, c.id, name="Archived", slug="d2", status=ProductStatus.archived)
        payload = _order_payload(
            items=[
                {"product_id": str(draft.id), "quantity": 1},
                {"product_id": str(archived.id), "quantity": 1},
            ]
        )
        resp = await client.post("/orders", json=payload)
        assert resp.status_code == 409
        assert len(resp.json()["detail"]) == 2

    async def test_409_detail_includes_product_id(self, client, db_engine):
        c = await _make_collection(db_engine)
        p = await _make_product(db_engine, c.id, status=ProductStatus.draft)
        payload = _order_payload(items=[{"product_id": str(p.id), "quantity": 1}])
        resp = await client.post("/orders", json=payload)
        assert resp.status_code == 409
        detail = resp.json()["detail"]
        assert any(e.get("product_id") == str(p.id) for e in detail)


# ---------------------------------------------------------------------------
# Timezone regression
# ---------------------------------------------------------------------------


class TestTimezoneHandling:
    async def test_order_succeeds_with_tz_aware_collection_dates(self, client, db_engine):
        """
        Regression: POST /orders returned 500 (TypeError: can't compare
        offset-naive and offset-aware datetimes) when the production PostgreSQL
        database returned tz-aware datetimes for opens_at / closes_at.

        Now that tests run against PostgreSQL directly, all datetime values
        returned by the ORM are tz-aware and this comparison is exercised on
        every test that touches collection date windows.  This case makes the
        regression explicit with an explicitly bounded collection window.
        """
        past = datetime.now(timezone.utc) - timedelta(days=1)
        future = datetime.now(timezone.utc) + timedelta(days=30)
        c = await _make_collection(db_engine, opens_at=past, closes_at=future)
        p = await _make_product(db_engine, c.id)
        payload = _order_payload(items=[{"product_id": str(p.id), "quantity": 1}])
        resp = await client.post("/orders", json=payload)
        assert resp.status_code == 201
