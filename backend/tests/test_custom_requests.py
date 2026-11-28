from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models.custom_request import CustomRequest, CustomRequestStatus
from app.models.settings import Settings, _SETTINGS_ID


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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


async def _make_custom_request(db_engine, **kwargs) -> CustomRequest:
    defaults = dict(
        name="Alice",
        email="alice@example.com",
        description="I'd like a blue tote bag",
        status=CustomRequestStatus.new,
    )
    defaults.update(kwargs)
    SessionLocal = async_sessionmaker(db_engine, expire_on_commit=False)
    async with SessionLocal() as db:
        r = CustomRequest(**defaults)
        db.add(r)
        await db.commit()
        await db.refresh(r)
        return r


def _request_payload(**kwargs) -> dict:
    base = {
        "name": "Jane Doe",
        "email": "jane@example.com",
        "description": "I want a custom crocheted blanket in earth tones.",
    }
    base.update(kwargs)
    return base


# ---------------------------------------------------------------------------
# POST /custom-requests
# ---------------------------------------------------------------------------


class TestSubmitCustomRequest:
    async def test_returns_201_with_new_status(self, client):
        resp = await client.post("/custom-requests", json=_request_payload())
        assert resp.status_code == 201
        assert resp.json()["status"] == "new"

    async def test_no_auth_required(self, client):
        resp = await client.post("/custom-requests", json=_request_payload())
        assert resp.status_code == 201

    async def test_response_includes_expected_fields(self, client):
        resp = await client.post("/custom-requests", json=_request_payload())
        data = resp.json()
        for field in ("id", "name", "email", "description", "status", "created_at"):
            assert field in data, f"missing field: {field}"

    async def test_saves_to_db(self, client, db_engine):
        payload = _request_payload(name="Bob", email="bob@test.com")
        resp = await client.post("/custom-requests", json=payload)
        assert resp.status_code == 201
        req_id = uuid.UUID(resp.json()["id"])
        SessionLocal = async_sessionmaker(db_engine, expire_on_commit=False)
        async with SessionLocal() as db:
            result = await db.execute(
                select(CustomRequest).where(CustomRequest.id == req_id)
            )
            saved = result.scalar_one_or_none()
        assert saved is not None
        assert saved.name == "Bob"
        assert saved.email == "bob@test.com"
        assert saved.status == CustomRequestStatus.new

    async def test_saves_reference_image_url(self, client):
        payload = _request_payload(reference_image_url="https://instagram.com/p/abc123")
        resp = await client.post("/custom-requests", json=payload)
        assert resp.status_code == 201
        assert resp.json()["reference_image_url"] == "https://instagram.com/p/abc123"

    async def test_reference_image_url_optional(self, client):
        payload = _request_payload()
        # no reference_image_url key
        resp = await client.post("/custom-requests", json=payload)
        assert resp.status_code == 201
        assert resp.json()["reference_image_url"] is None

    async def test_notification_email_sent_to_owner(self, client, db_engine):
        await _make_settings(db_engine, contact_email="owner@crochetbycarlen.com")
        payload = _request_payload()
        with patch(
            "app.routers.custom_requests.send_custom_request_notification",
            new_callable=AsyncMock,
        ) as mock_notify:
            resp = await client.post("/custom-requests", json=payload)
        assert resp.status_code == 201
        mock_notify.assert_called_once()
        call_data = mock_notify.call_args[0][0]
        assert call_data.owner_email == "owner@crochetbycarlen.com"
        assert call_data.customer_email == "jane@example.com"

    async def test_notification_sent_even_without_settings(self, client):
        """No settings row — notification is still sent; owner_email will be None."""
        with patch(
            "app.routers.custom_requests.send_custom_request_notification",
            new_callable=AsyncMock,
        ) as mock_notify:
            resp = await client.post("/custom-requests", json=_request_payload())
        assert resp.status_code == 201
        mock_notify.assert_called_once()
        call_data = mock_notify.call_args[0][0]
        assert call_data.owner_email is None

    async def test_notification_includes_description(self, client):
        payload = _request_payload(description="A big cozy blanket please")
        with patch(
            "app.routers.custom_requests.send_custom_request_notification",
            new_callable=AsyncMock,
        ) as mock_notify:
            resp = await client.post("/custom-requests", json=payload)
        call_data = mock_notify.call_args[0][0]
        assert call_data.description == "A big cozy blanket please"

    async def test_notification_includes_request_id(self, client):
        with patch(
            "app.routers.custom_requests.send_custom_request_notification",
            new_callable=AsyncMock,
        ) as mock_notify:
            resp = await client.post("/custom-requests", json=_request_payload())
        call_data = mock_notify.call_args[0][0]
        assert str(call_data.request_id) == resp.json()["id"]


# ---------------------------------------------------------------------------
# POST /custom-requests — input validation (422)
# ---------------------------------------------------------------------------


class TestSubmitCustomRequestValidation:
    async def test_missing_name_returns_422(self, client):
        payload = _request_payload()
        del payload["name"]
        resp = await client.post("/custom-requests", json=payload)
        assert resp.status_code == 422

    async def test_blank_name_returns_422(self, client):
        resp = await client.post("/custom-requests", json=_request_payload(name="   "))
        assert resp.status_code == 422

    async def test_invalid_email_returns_422(self, client):
        resp = await client.post(
            "/custom-requests", json=_request_payload(email="not-an-email")
        )
        assert resp.status_code == 422

    async def test_missing_description_returns_422(self, client):
        payload = _request_payload()
        del payload["description"]
        resp = await client.post("/custom-requests", json=payload)
        assert resp.status_code == 422

    async def test_blank_description_returns_422(self, client):
        resp = await client.post(
            "/custom-requests", json=_request_payload(description="   ")
        )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# GET /admin/custom-requests
# ---------------------------------------------------------------------------


class TestListCustomRequests:
    async def test_returns_200_with_list(self, client, auth_headers, db_engine):
        await _make_custom_request(db_engine)
        resp = await client.get("/admin/custom-requests", headers=auth_headers)
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)
        assert len(resp.json()) >= 1

    async def test_requires_auth(self, client):
        resp = await client.get("/admin/custom-requests")
        assert resp.status_code == 401

    async def test_response_includes_all_fields(self, client, auth_headers, db_engine):
        await _make_custom_request(db_engine, reference_image_url="https://example.com/img.jpg")
        resp = await client.get("/admin/custom-requests", headers=auth_headers)
        item = resp.json()[0]
        for field in ("id", "name", "email", "description", "reference_image_url", "status", "created_at"):
            assert field in item, f"missing field: {field}"

    async def test_filter_by_status_new(self, client, auth_headers, db_engine):
        await _make_custom_request(db_engine, status=CustomRequestStatus.new)
        await _make_custom_request(
            db_engine,
            email="other@example.com",
            status=CustomRequestStatus.declined,
        )
        resp = await client.get("/admin/custom-requests?status=new", headers=auth_headers)
        assert resp.status_code == 200
        assert all(r["status"] == "new" for r in resp.json())

    async def test_filter_by_status_quoted(self, client, auth_headers, db_engine):
        await _make_custom_request(db_engine, status=CustomRequestStatus.quoted)
        resp = await client.get("/admin/custom-requests?status=quoted", headers=auth_headers)
        assert resp.status_code == 200
        assert all(r["status"] == "quoted" for r in resp.json())

    async def test_no_filter_returns_all_statuses(self, client, auth_headers, db_engine):
        await _make_custom_request(db_engine, status=CustomRequestStatus.new)
        await _make_custom_request(
            db_engine,
            email="b@example.com",
            status=CustomRequestStatus.accepted,
        )
        resp = await client.get("/admin/custom-requests", headers=auth_headers)
        statuses = {r["status"] for r in resp.json()}
        assert "new" in statuses
        assert "accepted" in statuses

    async def test_ordered_most_recent_first(self, client, auth_headers, db_engine):
        from datetime import timedelta, timezone
        from datetime import datetime as dt
        base = dt.now(timezone.utc)
        r1 = await _make_custom_request(
            db_engine, email="r1@example.com", created_at=base - timedelta(hours=2)
        )
        r2 = await _make_custom_request(
            db_engine, email="r2@example.com", created_at=base - timedelta(hours=1)
        )
        resp = await client.get("/admin/custom-requests", headers=auth_headers)
        ids = [r["id"] for r in resp.json()]
        assert ids.index(str(r2.id)) < ids.index(str(r1.id))


# ---------------------------------------------------------------------------
# PATCH /admin/custom-requests/{id}
# ---------------------------------------------------------------------------


class TestUpdateCustomRequestStatus:
    async def test_updates_status(self, client, auth_headers, db_engine):
        r = await _make_custom_request(db_engine)
        resp = await client.patch(
            f"/admin/custom-requests/{r.id}",
            json={"status": "quoted"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "quoted"

    async def test_all_statuses_accepted(self, client, auth_headers, db_engine):
        for status in ("new", "quoted", "accepted", "declined"):
            r = await _make_custom_request(db_engine, email=f"{status}@example.com")
            resp = await client.patch(
                f"/admin/custom-requests/{r.id}",
                json={"status": status},
                headers=auth_headers,
            )
            assert resp.status_code == 200, f"failed for status={status}"
            assert resp.json()["status"] == status

    async def test_404_for_unknown_id(self, client, auth_headers):
        resp = await client.patch(
            f"/admin/custom-requests/{uuid.uuid4()}",
            json={"status": "quoted"},
            headers=auth_headers,
        )
        assert resp.status_code == 404

    async def test_requires_auth(self, client, db_engine):
        r = await _make_custom_request(db_engine)
        resp = await client.patch(
            f"/admin/custom-requests/{r.id}",
            json={"status": "quoted"},
        )
        assert resp.status_code == 401

    async def test_response_includes_all_fields(self, client, auth_headers, db_engine):
        r = await _make_custom_request(
            db_engine, description="Custom item", reference_image_url="https://example.com/ref.jpg"
        )
        resp = await client.patch(
            f"/admin/custom-requests/{r.id}",
            json={"status": "accepted"},
            headers=auth_headers,
        )
        data = resp.json()
        assert data["description"] == "Custom item"
        assert data["reference_image_url"] == "https://example.com/ref.jpg"
        assert data["status"] == "accepted"
