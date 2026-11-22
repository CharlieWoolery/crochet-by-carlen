from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text, func
from sqlalchemy import Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

if TYPE_CHECKING:
    from .variant import Variant


class OrderSource(str, enum.Enum):
    website = "website"
    instagram = "instagram"
    facebook = "facebook"
    other = "other"


class FulfillmentMethod(str, enum.Enum):
    ship = "ship"
    pickup = "pickup"
    dropoff = "dropoff"


class PaymentStatus(str, enum.Enum):
    unpaid = "unpaid"
    paid = "paid"


class PaymentMethod(str, enum.Enum):
    venmo = "venmo"
    zelle = "zelle"
    paypal = "paypal"
    cash = "cash"
    other = "other"


class FulfillmentStatus(str, enum.Enum):
    received = "received"
    in_progress = "in_progress"
    shipped = "shipped"
    ready_for_pickup = "ready_for_pickup"
    out_for_dropoff = "out_for_dropoff"
    delivered = "delivered"


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    order_number: Mapped[str] = mapped_column(String, nullable=False, unique=True, index=True)
    customer_name: Mapped[str] = mapped_column(String, nullable=False)
    customer_email: Mapped[str] = mapped_column(String, nullable=False)
    customer_phone: Mapped[str | None] = mapped_column(String)
    source: Mapped[OrderSource] = mapped_column(
        Enum(OrderSource, name="order_source"),
        nullable=False,
        default=OrderSource.website,
        server_default=OrderSource.website.value,
    )
    fulfillment_method: Mapped[FulfillmentMethod] = mapped_column(
        Enum(FulfillmentMethod, name="fulfillment_method"),
        nullable=False,
    )
    # Required for ship and dropoff; null for pickup
    address: Mapped[str | None] = mapped_column(Text)
    subtotal_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    fulfillment_fee_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    total_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    payment_status: Mapped[PaymentStatus] = mapped_column(
        Enum(PaymentStatus, name="payment_status"),
        nullable=False,
        default=PaymentStatus.unpaid,
        server_default=PaymentStatus.unpaid.value,
    )
    payment_method: Mapped[PaymentMethod | None] = mapped_column(
        Enum(PaymentMethod, name="payment_method"),
        nullable=True,
    )
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    fulfillment_status: Mapped[FulfillmentStatus] = mapped_column(
        Enum(FulfillmentStatus, name="fulfillment_status"),
        nullable=False,
        default=FulfillmentStatus.received,
        server_default=FulfillmentStatus.received.value,
    )
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    items: Mapped[list[OrderItem]] = relationship(
        back_populates="order",
        cascade="all, delete-orphan",
    )


class OrderItem(Base):
    __tablename__ = "order_items"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    order_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # RESTRICT: DB-level guard so a product with orders can never be hard-deleted
    product_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("products.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    # SET NULL so deleting a variant doesn't cascade-delete the order item
    variant_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("variants.id", ondelete="SET NULL"),
        nullable=True,
    )
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    # Snapshot of price at order time — never recalculated from the product
    unit_price_cents: Mapped[int] = mapped_column(Integer, nullable=False)

    order: Mapped[Order] = relationship(back_populates="items")
    variant: Mapped[Variant | None] = relationship()
