from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone

from fastapi import Depends, HTTPException
from fastapi.routing import APIRouter
from pydantic import BaseModel, ConfigDict, field_validator, model_validator
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

import app.utils.order_number as _onum
from ..database import get_db
from ..email import OrderConfirmationData, OrderItemSummary, send_order_confirmation
from ..models.collection import Collection, CollectionStatus
from ..models.order import (
    FulfillmentMethod,
    FulfillmentStatus,
    Order,
    OrderItem,
    OrderSource,
    PaymentStatus,
)
from ..models.product import Product, ProductStatus
from ..models.settings import Settings, _SETTINGS_ID
from ..models.variant import Variant

router = APIRouter(tags=["orders"])

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


# ---------------------------------------------------------------------------
# Request schemas
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


class OrderIn(BaseModel):
    customer_name: str
    customer_email: str
    customer_phone: str | None = None
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
    def _address_required(self) -> "OrderIn":
        if self.fulfillment_method in (FulfillmentMethod.ship, FulfillmentMethod.dropoff):
            if not self.address or not self.address.strip():
                raise ValueError("address is required for ship and dropoff orders")
        return self


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------


class OrderItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    product_id: uuid.UUID
    variant_id: uuid.UUID | None
    quantity: int
    unit_price_cents: int


class OrderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    order_number: str
    customer_name: str
    customer_email: str
    customer_phone: str | None
    fulfillment_method: FulfillmentMethod
    address: str | None
    subtotal_cents: int
    fulfillment_fee_cents: int
    total_cents: int
    payment_status: PaymentStatus
    items: list[OrderItemOut]
    created_at: datetime


# ---------------------------------------------------------------------------
# POST /orders
# ---------------------------------------------------------------------------


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@router.post("/orders", response_model=OrderOut, status_code=201)
async def create_order(
    body: OrderIn,
    db: AsyncSession = Depends(get_db),
) -> Order:
    # ------------------------------------------------------------------ #
    # 1. Validate every cart item server-side; collect all errors up front
    # ------------------------------------------------------------------ #
    errors: list[dict] = []
    validated: list[dict] = []  # {product, variant, unit_price_cents, quantity}

    now = _utcnow()

    for item in body.items:
        # Load product with its collection
        product_result = await db.execute(
            select(Product)
            .where(Product.id == item.product_id)
            .options(selectinload(Product.collection))
        )
        product = product_result.scalar_one_or_none()

        if product is None:
            errors.append({"product_id": str(item.product_id), "error": "product not found"})
            continue

        if product.status != ProductStatus.live:
            errors.append({"product_id": str(item.product_id), "error": "product is not available"})
            continue

        # Verify the product's collection is live and within its date window
        coll: Collection = product.collection
        if coll.status != CollectionStatus.live:
            errors.append({
                "product_id": str(item.product_id),
                "error": "collection is not open for orders",
            })
            continue

        if coll.opens_at is not None and coll.opens_at > now:
            errors.append({
                "product_id": str(item.product_id),
                "error": "collection has not opened yet",
            })
            continue

        if coll.closes_at is not None and coll.closes_at < now:
            errors.append({
                "product_id": str(item.product_id),
                "error": "collection is closed",
            })
            continue

        # Resolve variant (if supplied)
        variant: Variant | None = None
        if item.variant_id is not None:
            variant_result = await db.execute(
                select(Variant).where(Variant.id == item.variant_id)
            )
            variant = variant_result.scalar_one_or_none()
            if variant is None or variant.product_id != product.id:
                errors.append({
                    "product_id": str(item.product_id),
                    "error": "variant not found for this product",
                })
                continue

        # Check per-product order cap (total units across all orders)
        if product.order_cap is not None:
            existing_qty = await db.scalar(
                select(func.coalesce(func.sum(OrderItem.quantity), 0)).where(
                    OrderItem.product_id == product.id
                )
            )
            if (existing_qty or 0) + item.quantity > product.order_cap:
                errors.append({
                    "product_id": str(item.product_id),
                    "error": f"order cap of {product.order_cap} units exceeded",
                })
                continue

        # Variant price overrides the product price when set
        unit_price = variant.price_cents if (variant and variant.price_cents is not None) else product.price_cents

        validated.append({
            "product": product,
            "variant": variant,
            "unit_price_cents": unit_price,
            "quantity": item.quantity,
        })

    if errors:
        raise HTTPException(status_code=409, detail=errors)

    # ------------------------------------------------------------------ #
    # 2. Compute totals from live settings
    # ------------------------------------------------------------------ #
    settings_result = await db.execute(
        select(Settings).where(Settings.id == _SETTINGS_ID)
    )
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

    # ------------------------------------------------------------------ #
    # 3. Persist the order
    # ------------------------------------------------------------------ #
    order_number = await _onum.next_order_number(db)

    order = Order(
        order_number=order_number,
        customer_name=body.customer_name,
        customer_email=body.customer_email,
        customer_phone=body.customer_phone,
        source=OrderSource.website,
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
    await db.flush()  # populate order.id before inserting items

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

    # ------------------------------------------------------------------ #
    # 4. Send confirmation email (console stub until deploy)
    # ------------------------------------------------------------------ #
    item_summaries = [
        OrderItemSummary(
            product_name=v["product"].name,
            variant_name=v["variant"].name if v["variant"] else None,
            quantity=v["quantity"],
            unit_price_cents=v["unit_price_cents"],
        )
        for v in validated
    ]

    await send_order_confirmation(
        OrderConfirmationData(
            order_number=order_number,
            customer_name=body.customer_name,
            customer_email=body.customer_email,
            fulfillment_method=body.fulfillment_method.value,
            address=body.address,
            subtotal_cents=subtotal,
            fulfillment_fee_cents=fulfillment_fee,
            total_cents=total,
            items=item_summaries,
            venmo_handle=settings.venmo_handle if settings else None,
            zelle_contact=settings.zelle_contact if settings else None,
            paypal_link=settings.paypal_link if settings else None,
        )
    )

    return order
