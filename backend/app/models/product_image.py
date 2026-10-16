from __future__ import annotations

import uuid

from sqlalchemy import CheckConstraint, ForeignKey, Integer, String, Text
from sqlalchemy import Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class ProductImage(Base):
    __tablename__ = "product_images"
    __table_args__ = (
        # Focal point controls object-position for square-crop display (0–100)
        CheckConstraint("focal_x BETWEEN 0 AND 100", name="ck_product_images_focal_x"),
        CheckConstraint("focal_y BETWEEN 0 AND 100", name="ck_product_images_focal_y"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    product_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Key within object storage (R2/Supabase); URLs are derived from this
    storage_key: Mapped[str] = mapped_column(String, nullable=False)
    url_small: Mapped[str] = mapped_column(Text, nullable=False)
    url_medium: Mapped[str] = mapped_column(Text, nullable=False)
    url_large: Mapped[str] = mapped_column(Text, nullable=False)
    width: Mapped[int] = mapped_column(Integer, nullable=False)
    height: Mapped[int] = mapped_column(Integer, nullable=False)
    focal_x: Mapped[int] = mapped_column(Integer, nullable=False, default=50, server_default="50")
    focal_y: Mapped[int] = mapped_column(Integer, nullable=False, default=50, server_default="50")
    alt_text: Mapped[str | None] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")

    product: Mapped[Product] = relationship(back_populates="images")
    # Variants that use this image as their swatch photo
    variants_using: Mapped[list[Variant]] = relationship(
        back_populates="image",
        foreign_keys="[Variant.image_id]",
    )
