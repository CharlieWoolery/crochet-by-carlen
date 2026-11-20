from __future__ import annotations

import pytest
from fastapi.routing import APIRoute

from app.main import app


# ---------------------------------------------------------------------------
# GET /admin/settings
# ---------------------------------------------------------------------------


class TestGetSettings:
    async def test_returns_defaults_when_no_row_exists(self, client, auth_headers):
        resp = await client.get("/admin/settings", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["shipping_flat_cents"] == 600
        assert data["dropoff_fee_cents"] == 0
        # All text fields default to null
        for field in ("venmo_handle", "zelle_contact", "paypal_link", "pickup_address",
                      "contact_email", "instagram_url", "facebook_url", "tiktok_url"):
            assert data[field] is None, f"{field} should default to null"

    async def test_returns_values_set_via_patch(self, client, auth_headers):
        await client.patch(
            "/admin/settings",
            json={"venmo_handle": "@CarlenCrochet", "shipping_flat_cents": 800},
            headers=auth_headers,
        )
        resp = await client.get("/admin/settings", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["venmo_handle"] == "@CarlenCrochet"
        assert data["shipping_flat_cents"] == 800

    async def test_admin_can_read_pickup_address(self, client, auth_headers):
        """Admin must be able to read and update the private pickup address."""
        await client.patch(
            "/admin/settings",
            json={"pickup_address": "123 Maple St, Springfield"},
            headers=auth_headers,
        )
        resp = await client.get("/admin/settings", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["pickup_address"] == "123 Maple St, Springfield"

    async def test_requires_auth(self, client):
        resp = await client.get("/admin/settings")
        assert resp.status_code == 401

    def test_pickup_address_only_on_auth_protected_routes(self):
        """
        pickup_address must never be served by a public (unauthenticated) endpoint.

        This test verifies the structural guarantee: every route whose path
        contains 'settings' requires the admin dependency.  When public settings
        endpoints are added later (e.g. for social links), they must use a
        separate PublicSettingsOut schema that omits pickup_address, and this
        test must be updated to whitelist them.
        """
        from app.auth import require_admin

        for route in app.routes:
            if not isinstance(route, APIRoute):
                continue
            if "settings" not in route.path:
                continue
            dep_calls = {d.call for d in route.dependant.dependencies}
            assert require_admin in dep_calls, (
                f"Route {route.path} touches settings but does not require admin auth. "
                "Add require_admin or use a PublicSettingsOut schema that excludes pickup_address."
            )


# ---------------------------------------------------------------------------
# PATCH /admin/settings
# ---------------------------------------------------------------------------


class TestUpdateSettings:
    async def test_creates_row_on_first_patch(self, client, auth_headers):
        resp = await client.patch(
            "/admin/settings",
            json={"venmo_handle": "@test"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["venmo_handle"] == "@test"

    async def test_second_patch_updates_existing_row(self, client, auth_headers):
        await client.patch(
            "/admin/settings", json={"venmo_handle": "@first"}, headers=auth_headers
        )
        resp = await client.patch(
            "/admin/settings", json={"venmo_handle": "@second"}, headers=auth_headers
        )
        assert resp.status_code == 200
        assert resp.json()["venmo_handle"] == "@second"

    async def test_updates_shipping_rate(self, client, auth_headers):
        resp = await client.patch(
            "/admin/settings",
            json={"shipping_flat_cents": 900},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["shipping_flat_cents"] == 900

    async def test_updates_dropoff_fee(self, client, auth_headers):
        resp = await client.patch(
            "/admin/settings",
            json={"dropoff_fee_cents": 250},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["dropoff_fee_cents"] == 250

    async def test_null_shipping_flat_cents_returns_422(self, client, auth_headers):
        resp = await client.patch(
            "/admin/settings",
            json={"shipping_flat_cents": None},
            headers=auth_headers,
        )
        assert resp.status_code == 422

    async def test_null_dropoff_fee_cents_returns_422(self, client, auth_headers):
        resp = await client.patch(
            "/admin/settings",
            json={"dropoff_fee_cents": None},
            headers=auth_headers,
        )
        assert resp.status_code == 422

    async def test_negative_shipping_returns_422(self, client, auth_headers):
        resp = await client.patch(
            "/admin/settings",
            json={"shipping_flat_cents": -1},
            headers=auth_headers,
        )
        assert resp.status_code == 422

    async def test_clears_nullable_field_with_explicit_null(self, client, auth_headers):
        await client.patch(
            "/admin/settings", json={"venmo_handle": "@v"}, headers=auth_headers
        )
        resp = await client.patch(
            "/admin/settings", json={"venmo_handle": None}, headers=auth_headers
        )
        assert resp.status_code == 200
        assert resp.json()["venmo_handle"] is None

    async def test_unset_fields_not_touched(self, client, auth_headers):
        await client.patch(
            "/admin/settings",
            json={"venmo_handle": "@keep", "shipping_flat_cents": 700},
            headers=auth_headers,
        )
        resp = await client.patch(
            "/admin/settings",
            json={"zelle_contact": "owner@email.com"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["venmo_handle"] == "@keep"
        assert data["shipping_flat_cents"] == 700
        assert data["zelle_contact"] == "owner@email.com"

    async def test_sets_all_fields(self, client, auth_headers):
        payload = {
            "venmo_handle": "@v",
            "zelle_contact": "z@z.com",
            "paypal_link": "https://paypal.me/x",
            "shipping_flat_cents": 600,
            "dropoff_fee_cents": 0,
            "pickup_address": "1 Main St",
            "contact_email": "hi@example.com",
            "instagram_url": "https://instagram.com/x",
            "facebook_url": "https://facebook.com/x",
            "tiktok_url": "https://tiktok.com/@x",
        }
        resp = await client.patch("/admin/settings", json=payload, headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        for k, v in payload.items():
            assert data[k] == v

    async def test_requires_auth(self, client):
        resp = await client.patch("/admin/settings", json={"venmo_handle": "@x"})
        assert resp.status_code == 401
