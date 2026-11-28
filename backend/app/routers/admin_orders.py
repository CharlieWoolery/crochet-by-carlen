from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, field_validator, model_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

import app.utils.order_number as _onum
from ..auth import require_admin
from ..database import get_db
from ..models.admin import AdminUser
from ..models.order import (
    FulfillmentMethod,
    FulfillmentStatus,
    Order,
    OrderItem,
    OrderSource,
    PaymentMethod,
    PaymentStatus,
)
from ..models.settings import Settings, _SETTINGS_ID
from ..utils.order_validation import validate_cart_items

router = APIRouter(prefix="/admin/orders", tags=["admin-orders"])

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


# ---------------------------------------------------------------------------
# Shared input schema (re-used in public orders router too)
# ---------------------------------------------------------------------------


class CartItemIn(BaseModel):
    product_id: uuid.UUID
    variant_id: uuid.UUID | None = None
    quantity: int

    @field_validator("quantity")
    @classmethod
    def _positive_quantity(cls, v: int) -> int:
        if v < 1:
            raise ValueError("quantity must be at least 1")
        return v


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------


class AdminOrderIn(BaseModel):
    """Manual order entry — used by the owner for Instagram/Facebook DM orders."""

    customer_name: str
    customer_email: str
    customer_phone: str | None = None
    source: OrderSource
    fulfillment_method: FulfillmentMethod
    address: str | None = None
    items: list[CartItemIn]
    notes: str | None = None

    @field_validator("customer_name")
    @classmethod
    def _non_empty_name(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("customer_name must not be blank")
        return v.strip()

    @field_validator("customer_email")
    @classmethod
    def _valid_email(cls, v: str) -> str:
        if not _EMAIL_RE.match(v):
            raise ValueError("invalid email address")
        return v.lower().strip()

    @field_validator("items")
    @classmethod
    def _non_empty_items(cls, v: list) -> list:
        if not v:
            raise ValueError("at least one item is required")
        return v

    @model_validator(mode="after")
    def _address_required(self) -> "AdminOrderIn":
        if self.fulfillment_method in (FulfillmentMethod.ship, FulfillmentMethod.dropoff):
            if not self.address or not self.address.strip():
                raise ValueError("address is required for ship and dropoff orders")
        return self


class MarkPaidIn(BaseModel):
    payment_method: PaymentMethod


class UpdateFulfillmentIn(BaseModel):
    status: FulfillmentStatus


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------


class AdminOrderItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    product_id: uuid.UUID
    variant_id: uuid.UUID | None
    quantity: int
    unit_price_cents: int


class AdminOrderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    order_number: str
    customer_name: str
    customer_email: str
    customer_phone: str | None
    source: OrderSource
    fulfillment_method: FulfillmentMethod
    address: str | None
    subtotal_cents: int
    fulfillment_fee_cents: int
    total_cents: int
    payment_status: PaymentStatus
    payment_method: PaymentMethod | None
    paid_at: datetime | None
    fulfillment_status: FulfillmentStatus
    notes: str | None
    created_at: datetime
    items: list[AdminOrderItemOut]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def _get_order_or_404(order_id: uuid.UUID, db: AsyncSession) -> Order:
    result = await db.execute(
        select(Order)
        .where(Order.id == order_id)
        .options(selectinload(Order.items))
    )
    order = result.scalar_one_or_none()
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")
    return order


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("", response_model=list[AdminOrderOut])
async def list_orders(
    payment_status: Annotated[PaymentStatus | None, Query()] = None,
    fulfillment_status: Annotated[FulfillmentStatus | None, Query()] = None,
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(require_admin),
) -> list[Order]:
    q = (
        select(Order)
        .options(selectinload(Order.items))
        .order_by(Order.created_at.desc())
    )
    if payment_status is not None:
        q = q.where(Order.payment_status == payment_status)
    if fulfillment_status is not None:
        q = q.where(Order.fulfillment_status == fulfillment_status)
    result = await db.execute(q)
    return list(result.scalars().all())


@router.get("/{order_id}", response_model=AdminOrderOut)
async def get_order(
    order_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(require_admin),
) -> Order:
    return await _get_order_or_404(order_id, db)


@router.post("", response_model=AdminOrderOut, status_code=201)
async def create_order_manual(
    body: AdminOrderIn,
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(require_admin),
) -> Order:
    # Validate cart items server-side (same rules as the public checkout)
    now = _utcnow()
    validated, errors = await validate_cart_items(body.items, db, now)

    if errors:
        raise HTTPException(status_code=409, detail=errors)

    # Compute totals from live settings
    settings_result = await db.execute(select(Settings).where(Settings.id == _SETTINGS_ID))
    settings = settings_result.scalar_one_or_none()

    shipping_flat_cents: int = settings.shipping_flat_cents if settings else 600
    dropoff_fee_cents: int = settings.dropoff_fee_cents if settings else 0

    if body.fulfillment_method == FulfillmentMethod.ship:
        fulfillment_fee = shipping_flat_cents
    elif body.fulfillment_method == FulfillmentMethod.dropoff:
        fulfillment_fee = dropoff_fee_cents
    else:
        fulfillment_fee = 0

    subtotal = sum(v["unit_price_cents"] * v["quantity"] for v in validated)
    total = subtotal + fulfillment_fee

    # Persist the order
    order_number = await _onum.next_order_number(db)

    order = Order(
        order_number=order_number,
        customer_name=body.customer_name,
        customer_email=body.customer_email,
        customer_phone=body.customer_phone,
        source=body.source,
        fulfillment_method=body.fulfillment_method,
        address=body.address,
        subtotal_cents=subtotal,
        fulfillment_fee_cents=fulfillment_fee,
        total_cents=total,
        payment_status=PaymentStatus.unpaid,
        fulfillment_status=FulfillmentStatus.received,
        notes=body.notes,
    )
    db.add(order)
    await db.flush()

    for v in validated:
        db.add(OrderItem(
            order_id=order.id,
            product_id=v["product"].id,
            variant_id=v["variant"].id if v["variant"] else None,
            quantity=v["quantity"],
            unit_price_cents=v["unit_price_cents"],
        ))

    await db.commit()
    await db.refresh(order, ["items"])
    return order


@router.patch("/{order_id}/payment", response_model=AdminOrderOut)
async def mark_order_paid(
    order_id: uuid.UUID,
    body: MarkPaidIn,
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(require_admin),
) -> Order:
    order = await _get_order_or_404(order_id, db)
    order.payment_status = PaymentStatus.paid
    order.payment_method = body.payment_method
    order.paid_at = _utcnow()
    await db.commit()
    await db.refresh(order, ["items"])
    return order


@router.patch("/{order_id}/fulfillment", response_model=AdminOrderOut)
async def update_fulfillment_status(
    order_id: uuid.UUID,
    body: UpdateFulfillmentIn,
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(require_admin),
) -> Order:
    order = await _get_order_or_404(order_id, db)
    order.fulfillment_status = body.status
    await db.commit()
    await db.refresh(order, ["items"])
    return order
