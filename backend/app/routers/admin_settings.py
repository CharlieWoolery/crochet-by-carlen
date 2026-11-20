from __future__ import annotations

from fastapi import Depends, HTTPException
from fastapi.routing import APIRouter
from pydantic import BaseModel, ConfigDict, model_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import require_admin
from ..database import get_db
from ..models.admin import AdminUser
from ..models.settings import Settings, _SETTINGS_ID

router = APIRouter(prefix="/admin", tags=["admin-settings"])


class AdminSettingsOut(BaseModel):
    """
    Admin-only response schema for settings.

    pickup_address is included here because the owner must be able to read and
    update it. This schema must NEVER be reused for public endpoints — build a
    separate PublicSettingsOut (without pickup_address) for any unauthenticated
    settings exposure.
    """

    model_config = ConfigDict(from_attributes=True)

    venmo_handle: str | None
    zelle_contact: str | None
    paypal_link: str | None
    shipping_flat_cents: int
    dropoff_fee_cents: int
    pickup_address: str | None
    contact_email: str | None
    instagram_url: str | None
    facebook_url: str | None
    tiktok_url: str | None


_DEFAULTS = dict(
    venmo_handle=None,
    zelle_contact=None,
    paypal_link=None,
    shipping_flat_cents=600,
    dropoff_fee_cents=0,
    pickup_address=None,
    contact_email=None,
    instagram_url=None,
    facebook_url=None,
    tiktok_url=None,
)


class SettingsUpdate(BaseModel):
    venmo_handle: str | None = None
    zelle_contact: str | None = None
    paypal_link: str | None = None
    shipping_flat_cents: int | None = None
    dropoff_fee_cents: int | None = None
    pickup_address: str | None = None
    contact_email: str | None = None
    instagram_url: str | None = None
    facebook_url: str | None = None
    tiktok_url: str | None = None

    @model_validator(mode="after")
    def _non_nullable_fields(self) -> "SettingsUpdate":
        # shipping_flat_cents and dropoff_fee_cents always have a value in the DB.
        # Explicit null in a PATCH body would break that invariant.
        for field in ("shipping_flat_cents", "dropoff_fee_cents"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} cannot be set to null")
        return self

    @model_validator(mode="after")
    def _non_negative_fees(self) -> "SettingsUpdate":
        for field in ("shipping_flat_cents", "dropoff_fee_cents"):
            v = getattr(self, field)
            if v is not None and v < 0:
                raise ValueError(f"{field} must be >= 0")
        return self


@router.get("/settings", response_model=AdminSettingsOut)
async def get_settings(
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(require_admin),
) -> AdminSettingsOut:
    result = await db.execute(select(Settings).where(Settings.id == _SETTINGS_ID))
    row = result.scalar_one_or_none()
    if row is None:
        return AdminSettingsOut(**_DEFAULTS)
    return AdminSettingsOut.model_validate(row)


@router.patch("/settings", response_model=AdminSettingsOut)
async def update_settings(
    body: SettingsUpdate,
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(require_admin),
) -> AdminSettingsOut:
    result = await db.execute(select(Settings).where(Settings.id == _SETTINGS_ID))
    row = result.scalar_one_or_none()
    if row is None:
        row = Settings(id=_SETTINGS_ID, **{k: v for k, v in _DEFAULTS.items()})
        db.add(row)

    fields = body.model_fields_set
    if "venmo_handle" in fields:
        row.venmo_handle = body.venmo_handle
    if "zelle_contact" in fields:
        row.zelle_contact = body.zelle_contact
    if "paypal_link" in fields:
        row.paypal_link = body.paypal_link
    if "shipping_flat_cents" in fields:
        row.shipping_flat_cents = body.shipping_flat_cents
    if "dropoff_fee_cents" in fields:
        row.dropoff_fee_cents = body.dropoff_fee_cents
    if "pickup_address" in fields:
        row.pickup_address = body.pickup_address
    if "contact_email" in fields:
        row.contact_email = body.contact_email
    if "instagram_url" in fields:
        row.instagram_url = body.instagram_url
    if "facebook_url" in fields:
        row.facebook_url = body.facebook_url
    if "tiktok_url" in fields:
        row.tiktok_url = body.tiktok_url

    await db.commit()
    await db.refresh(row)
    return AdminSettingsOut.model_validate(row)
