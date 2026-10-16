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
    from .collection import Collection
    from .product_image import ProductImage
    from .variant import Variant


class ProductStatus(str, enum.Enum):
    draft = "draft"
    live = "live"
    archived = "archived"


class Product(Base):
    __tablename__ = "products"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    # RESTRICT prevents accidentally deleting a collection that still has products
    collection_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("collections.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    slug: Mapped[str] = mapped_column(String, nullable=False, unique=True, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    # Money stored as integer cents — never floats
    price_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    materials: Mapped[str] = mapped_column(Text, nullable=False)
    dimensions: Mapped[str | None] = mapped_column(Text)
    pattern_credit: Mapped[str | None] = mapped_column(Text)
    pattern_credit_url: Mapped[str | None] = mapped_column(Text)
    lead_time: Mapped[str | None] = mapped_column(Text)
    # Null means no cap; the spec says off by default
    order_cap: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[ProductStatus] = mapped_column(
        Enum(ProductStatus, name="product_status"),
        nullable=False,
        default=ProductStatus.draft,
        server_default=ProductStatus.draft.value,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    collection: Mapped[Collection] = relationship(back_populates="products")
    images: Mapped[list[ProductImage]] = relationship(
        back_populates="product",
        cascade="all, delete-orphan",
        order_by="ProductImage.sort_order",
    )
    variants: Mapped[list[Variant]] = relationship(
        back_populates="product",
        cascade="all, delete-orphan",
    )
