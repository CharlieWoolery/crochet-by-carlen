"""
Stub order models. Only the columns needed for the product-delete foreign-key
check are defined here. The orders sprint will add the full Order model and
remaining OrderItem columns via a migration.
"""
from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class OrderItem(Base):
    __tablename__ = "order_items"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    # FK to orders.id added in orders sprint; plain UUID until then
    order_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    # RESTRICT: DB-level guard so a product with orders can never be hard-deleted
    product_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("products.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
