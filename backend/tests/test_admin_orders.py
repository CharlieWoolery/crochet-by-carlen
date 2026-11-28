from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models.collection import Collection, CollectionStatus
from app.models.order import (
    FulfillmentMethod,
    FulfillmentStatus,
    Order,
    OrderItem,
    OrderSource,
    PaymentMethod,
    PaymentStatus,
)
from app.models.product import Product, ProductStatus
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
    defaults = dict(id=_SETTINGS_ID, shipping_flat_cents=600, dropoff_fee_cents=0)
    defaults.update(kwargs)
    SessionLocal = async_sessionmaker(db_engine, expire_on_commit=False)
    async with SessionLocal() as db:
        s = Settings(**defaults)
        db.add(s)
        await db.commit()
        await db.refresh(s)
        return s


async def _make_order(db_engine, **kwargs) -> Order:
    defaults = dict(
        order_number=f"CBC-{uuid.uuid4().hex[:8].upper()}",
        customer_name="Test Customer",
        customer_email="test@example.com",
        source=OrderSource.website,
        fulfillment_method=FulfillmentMethod.pickup,
        subtotal_cents=2500,
        fulfillment_fee_cents=0,
        total_cents=2500,
        payment_status=PaymentStatus.unpaid,
        fulfillment_status=FulfillmentStatus.received,
    )
    defaults.update(kwargs)
    SessionLocal = async_sessionmaker(db_engine, expire_on_commit=False)
    async with SessionLocal() as db:
        o = Order(**defaults)
        db.add(o)
        await db.commit()
        await db.refresh(o)
        return o


def _dm_order_payload(**kwargs) -> dict:
    """Minimal valid admin order payload (instagram source, pickup, single item)."""
    base = {
        "customer_name": "Jane Smith",
        "customer_email": "jane@example.com",
        "source": "instagram",
        "fulfillment_method": "pickup",
        "items": [],
    }
    base.update(kwargs)
    return base


# ---------------------------------------------------------------------------
# GET /admin/orders
# ---------------------------------------------------------------------------


class TestListOrders:
    async def test_returns_200_with_list(self, client, auth_headers, db_engine):
        await _make_order(db_engine)
        resp = await client.get("/admin/orders", headers=auth_headers)
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)
        assert len(resp.json()) >= 1

    async def test_requires_auth(self, client):
        resp = await client.get("/admin/orders")
        assert resp.status_code == 401

    async def test_filter_by_payment_status_unpaid(self, client, auth_headers, db_engine):
        await _make_order(db_engine, payment_status=PaymentStatus.unpaid)
        await _make_order(
            db_engine,
            order_number=f"CBC-{uuid.uuid4().hex[:8]}",
            payment_status=PaymentStatus.paid,
            payment_method=PaymentMethod.venmo,
        )
        resp = await client.get("/admin/orders?payment_status=unpaid", headers=auth_headers)
        assert resp.status_code == 200
        statuses = [o["payment_status"] for o in resp.json()]
        assert all(s == "unpaid" for s in statuses)

    async def test_filter_by_payment_status_paid(self, client, auth_headers, db_engine):
        await _make_order(
            db_engine,
            payment_status=PaymentStatus.paid,
            payment_method=PaymentMethod.zelle,
        )
        resp = await client.get("/admin/orders?payment_status=paid", headers=auth_headers)
        assert resp.status_code == 200
        assert all(o["payment_status"] == "paid" for o in resp.json())

    async def test_filter_by_fulfillment_status(self, client, auth_headers, db_engine):
        await _make_order(db_engine, fulfillment_status=FulfillmentStatus.in_progress)
        resp = await client.get(
            "/admin/orders?fulfillment_status=in_progress", headers=auth_headers
        )
        assert resp.status_code == 200
        assert all(o["fulfillment_status"] == "in_progress" for o in resp.json())

    async def test_response_includes_items(self, client, auth_headers, db_engine):
        order = await _make_order(db_engine)
        c = await _make_collection(db_engine)
        p = await _make_product(db_engine, c.id)
        SessionLocal = async_sessionmaker(db_engine, expire_on_commit=False)
        async with SessionLocal() as db:
            db.add(OrderItem(
                order_id=order.id,
                product_id=p.id,
                quantity=2,
                unit_price_cents=p.price_cents,
            ))
            await db.commit()
        resp = await client.get("/admin/orders", headers=auth_headers)
        assert resp.status_code == 200
        orders_with_items = [o for o in resp.json() if str(order.id) == o["id"]]
        assert len(orders_with_items) == 1
        assert len(orders_with_items[0]["items"]) == 1
        assert orders_with_items[0]["items"][0]["quantity"] == 2

    async def test_response_includes_all_order_fields(self, client, auth_headers, db_engine):
        await _make_order(db_engine)
        resp = await client.get("/admin/orders", headers=auth_headers)
        order = resp.json()[0]
        for field in (
            "id", "order_number", "customer_name", "customer_email",
            "source", "fulfillment_method", "payment_status", "payment_method",
            "paid_at", "fulfillment_status", "subtotal_cents", "total_cents",
            "created_at", "items",
        ):
            assert field in order, f"missing field: {field}"

    async def test_ordered_most_recent_first(self, client, auth_headers, db_engine):
        base = _now()
        o1 = await _make_order(
            db_engine, order_number="CBC-FIRST1", created_at=base - timedelta(hours=2)
        )
        o2 = await _make_order(
            db_engine, order_number="CBC-SECOND2", created_at=base - timedelta(hours=1)
        )
        resp = await client.get("/admin/orders", headers=auth_headers)
        ids = [o["id"] for o in resp.json()]
        # o2 is newer so it must appear before o1
        assert ids.index(str(o2.id)) < ids.index(str(o1.id))


# ---------------------------------------------------------------------------
# GET /admin/orders/{id}
# ---------------------------------------------------------------------------


class TestGetOrder:
    async def test_returns_full_order_detail(self, client, auth_headers, db_engine):
        order = await _make_order(db_engine, notes="Handle with care")
        resp = await client.get(f"/admin/orders/{order.id}", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["id"] == str(order.id)
        assert resp.json()["notes"] == "Handle with care"

    async def test_404_for_unknown_id(self, client, auth_headers):
        resp = await client.get(f"/admin/orders/{uuid.uuid4()}", headers=auth_headers)
        assert resp.status_code == 404

    async def test_requires_auth(self, client, db_engine):
        order = await _make_order(db_engine)
        resp = await client.get(f"/admin/orders/{order.id}")
        assert resp.status_code == 401

    async def test_includes_items(self, client, auth_headers, db_engine):
        order = await _make_order(db_engine)
        c = await _make_collection(db_engine)
        p = await _make_product(db_engine, c.id)
        SessionLocal = async_sessionmaker(db_engine, expire_on_commit=False)
        async with SessionLocal() as db:
            db.add(OrderItem(
                order_id=order.id,
                product_id=p.id,
                quantity=1,
                unit_price_cents=p.price_cents,
            ))
            await db.commit()
        resp = await client.get(f"/admin/orders/{order.id}", headers=auth_headers)
        assert len(resp.json()["items"]) == 1


# ---------------------------------------------------------------------------
# POST /admin/orders  (manual DM entry)
# ---------------------------------------------------------------------------


class TestManualOrderEntry:
    async def test_instagram_source_returns_201(self, client, auth_headers, db_engine):
        c = await _make_collection(db_engine)
        p = await _make_product(db_engine, c.id)
        payload = _dm_order_payload(
            source="instagram",
            items=[{"product_id": str(p.id), "quantity": 1}],
        )
        resp = await client.post("/admin/orders", json=payload, headers=auth_headers)
        assert resp.status_code == 201
        assert resp.json()["source"] == "instagram"

    async def test_facebook_source_returns_201(self, client, auth_headers, db_engine):
        c = await _make_collection(db_engine)
        p = await _make_product(db_engine, c.id)
        payload = _dm_order_payload(
            source="facebook",
            items=[{"product_id": str(p.id), "quantity": 1}],
        )
        resp = await client.post("/admin/orders", json=payload, headers=auth_headers)
        assert resp.status_code == 201
        assert resp.json()["source"] == "facebook"

    async def test_other_source_returns_201(self, client, auth_headers, db_engine):
        c = await _make_collection(db_engine)
        p = await _make_product(db_engine, c.id)
        payload = _dm_order_payload(
            source="other",
            items=[{"product_id": str(p.id), "quantity": 1}],
        )
        resp = await client.post("/admin/orders", json=payload, headers=auth_headers)
        assert resp.status_code == 201

    async def test_requires_auth(self, client, db_engine):
        c = await _make_collection(db_engine)
        p = await _make_product(db_engine, c.id)
        payload = _dm_order_payload(items=[{"product_id": str(p.id), "quantity": 1}])
        resp = await client.post("/admin/orders", json=payload)
        assert resp.status_code == 401

    async def test_computes_totals_server_side(self, client, auth_headers, db_engine):
        await _make_settings(db_engine, shipping_flat_cents=600)
        c = await _make_collection(db_engine)
        p = await _make_product(db_engine, c.id, price_cents=1000)
        payload = _dm_order_payload(
            source="instagram",
            fulfillment_method="ship",
            address="123 Main St",
            items=[{"product_id": str(p.id), "quantity": 2}],
        )
        resp = await client.post("/admin/orders", json=payload, headers=auth_headers)
        assert resp.status_code == 201
        data = resp.json()
        assert data["subtotal_cents"] == 2000
        assert data["fulfillment_fee_cents"] == 600
        assert data["total_cents"] == 2600

    async def test_draft_product_returns_409(self, client, auth_headers, db_engine):
        c = await _make_collection(db_engine)
        p = await _make_product(db_engine, c.id, status=ProductStatus.draft)
        payload = _dm_order_payload(items=[{"product_id": str(p.id), "quantity": 1}])
        resp = await client.post("/admin/orders", json=payload, headers=auth_headers)
        assert resp.status_code == 409

    async def test_closed_collection_returns_409(self, client, auth_headers, db_engine):
        past = _now() - timedelta(days=1)
        c = await _make_collection(db_engine, closes_at=past)
        p = await _make_product(db_engine, c.id)
        payload = _dm_order_payload(items=[{"product_id": str(p.id), "quantity": 1}])
        resp = await client.post("/admin/orders", json=payload, headers=auth_headers)
        assert resp.status_code == 409

    async def test_ship_without_address_returns_422(self, client, auth_headers, db_engine):
        c = await _make_collection(db_engine)
        p = await _make_product(db_engine, c.id)
        payload = _dm_order_payload(
            fulfillment_method="ship",
            address=None,
            items=[{"product_id": str(p.id), "quantity": 1}],
        )
        resp = await client.post("/admin/orders", json=payload, headers=auth_headers)
        assert resp.status_code == 422

    async def test_order_number_generated(self, client, auth_headers, db_engine):
        c = await _make_collection(db_engine)
        p = await _make_product(db_engine, c.id)
        payload = _dm_order_payload(items=[{"product_id": str(p.id), "quantity": 1}])
        resp = await client.post("/admin/orders", json=payload, headers=auth_headers)
        assert resp.status_code == 201
        import re
        assert re.match(r"^CBC-\d+$", resp.json()["order_number"])

    async def test_no_confirmation_email_sent(self, client, auth_headers, db_engine):
        """Admin-entered DM orders do not trigger a customer confirmation email."""
        from unittest.mock import AsyncMock, patch
        c = await _make_collection(db_engine)
        p = await _make_product(db_engine, c.id)
        payload = _dm_order_payload(items=[{"product_id": str(p.id), "quantity": 1}])
        with patch("app.routers.orders.send_order_confirmation", new_callable=AsyncMock) as mock_email:
            resp = await client.post("/admin/orders", json=payload, headers=auth_headers)
        assert resp.status_code == 201
        mock_email.assert_not_called()

    async def test_response_includes_source_and_fulfillment_status(
        self, client, auth_headers, db_engine
    ):
        c = await _make_collection(db_engine)
        p = await _make_product(db_engine, c.id)
        payload = _dm_order_payload(
            source="facebook",
            items=[{"product_id": str(p.id), "quantity": 1}],
        )
        resp = await client.post("/admin/orders", json=payload, headers=auth_headers)
        data = resp.json()
        assert data["source"] == "facebook"
        assert data["fulfillment_status"] == "received"
        assert data["payment_status"] == "unpaid"


# ---------------------------------------------------------------------------
# PATCH /admin/orders/{id}/payment
# ---------------------------------------------------------------------------


class TestMarkOrderPaid:
    async def test_marks_payment_status_paid(self, client, auth_headers, db_engine):
        order = await _make_order(db_engine)
        resp = await client.patch(
            f"/admin/orders/{order.id}/payment",
            json={"payment_method": "venmo"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["payment_status"] == "paid"

    async def test_records_payment_method(self, client, auth_headers, db_engine):
        order = await _make_order(db_engine)
        resp = await client.patch(
            f"/admin/orders/{order.id}/payment",
            json={"payment_method": "zelle"},
            headers=auth_headers,
        )
        assert resp.json()["payment_method"] == "zelle"

    async def test_sets_paid_at_timestamp(self, client, auth_headers, db_engine):
        order = await _make_order(db_engine)
        resp = await client.patch(
            f"/admin/orders/{order.id}/payment",
            json={"payment_method": "paypal"},
            headers=auth_headers,
        )
        assert resp.json()["paid_at"] is not None

    async def test_all_payment_methods_accepted(self, client, auth_headers, db_engine):
        for method in ("venmo", "zelle", "paypal", "cash", "other"):
            order = await _make_order(db_engine, order_number=f"CBC-PM-{method}")
            resp = await client.patch(
                f"/admin/orders/{order.id}/payment",
                json={"payment_method": method},
                headers=auth_headers,
            )
            assert resp.status_code == 200
            assert resp.json()["payment_method"] == method

    async def test_404_for_unknown_order(self, client, auth_headers):
        resp = await client.patch(
            f"/admin/orders/{uuid.uuid4()}/payment",
            json={"payment_method": "venmo"},
            headers=auth_headers,
        )
        assert resp.status_code == 404

    async def test_requires_auth(self, client, db_engine):
        order = await _make_order(db_engine)
        resp = await client.patch(
            f"/admin/orders/{order.id}/payment",
            json={"payment_method": "venmo"},
        )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# PATCH /admin/orders/{id}/fulfillment
# ---------------------------------------------------------------------------


class TestUpdateFulfillmentStatus:
    async def test_updates_fulfillment_status(self, client, auth_headers, db_engine):
        order = await _make_order(db_engine)
        resp = await client.patch(
            f"/admin/orders/{order.id}/fulfillment",
            json={"status": "in_progress"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["fulfillment_status"] == "in_progress"

    async def test_all_statuses_accepted(self, client, auth_headers, db_engine):
        statuses = [
            "received", "in_progress", "shipped",
            "ready_for_pickup", "out_for_dropoff", "delivered",
        ]
        for status in statuses:
            order = await _make_order(db_engine, order_number=f"CBC-FS-{status[:4]}")
            resp = await client.patch(
                f"/admin/orders/{order.id}/fulfillment",
                json={"status": status},
                headers=auth_headers,
            )
            assert resp.status_code == 200, f"failed for status={status}"
            assert resp.json()["fulfillment_status"] == status

    async def test_404_for_unknown_order(self, client, auth_headers):
        resp = await client.patch(
            f"/admin/orders/{uuid.uuid4()}/fulfillment",
            json={"status": "shipped"},
            headers=auth_headers,
        )
        assert resp.status_code == 404

    async def test_requires_auth(self, client, db_engine):
        order = await _make_order(db_engine)
        resp = await client.patch(
            f"/admin/orders/{order.id}/fulfillment",
            json={"status": "in_progress"},
        )
        assert resp.status_code == 401

    async def test_shipped_to_delivered_transition(self, client, auth_headers, db_engine):
        order = await _make_order(
            db_engine, fulfillment_status=FulfillmentStatus.shipped
        )
        resp = await client.patch(
            f"/admin/orders/{order.id}/fulfillment",
            json={"status": "delivered"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["fulfillment_status"] == "delivered"
