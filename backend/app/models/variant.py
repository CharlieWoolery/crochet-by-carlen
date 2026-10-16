from __future__ import annotations

import enum
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Enum, ForeignKey, Integer, String
from sqlalchemy import Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

if TYPE_CHECKING:
    from .product import Product
    from .product_image import ProductImage


class OptionType(str, enum.Enum):
    color = "color"
    material = "material"


class Variant(Base):
    __tablename__ = "variants"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    product_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    option_type: Mapped[OptionType] = mapped_column(
        Enum(OptionType, name="option_type"),
        nullable=False,
    )
    # 6-digit hex colour for swatch display, e.g. "#FF5733"
    swatch_hex: Mapped[str | None] = mapped_column(String(7))
    # When set, the product page switches to this image when the swatch is tapped.
    # SET NULL so deleting an image doesn't cascade-delete the variant.
    image_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("product_images.id", ondelete="SET NULL"),
    )
    # Null = use the parent product's price; set to override per variant
    price_cents: Mapped[int | None] = mapped_column(Integer)

    product: Mapped[Product] = relationship(back_populates="variants")
    image: Mapped[ProductImage | None] = relationship(
        back_populates="variants_using",
        foreign_keys="[Variant.image_id]",
    )
