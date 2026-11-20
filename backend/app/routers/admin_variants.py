from __future__ import annotations

import re
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import require_admin
from ..database import get_db
from ..models.admin import AdminUser
from ..models.product import Product
from ..models.product_image import ProductImage
from ..models.variant import OptionType, Variant

router = APIRouter(prefix="/admin", tags=["admin-variants"])

_HEX_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")


class VariantCreate(BaseModel):
    name: str
    option_type: OptionType
    swatch_hex: str | None = None
    image_id: uuid.UUID | None = None
    price_cents: int | None = None

    @field_validator("swatch_hex")
    @classmethod
    def _valid_hex(cls, v: str | None) -> str | None:
        if v is not None and not _HEX_RE.match(v):
            raise ValueError("swatch_hex must be a 7-character hex colour like #FF5733")
        return v


class VariantUpdate(BaseModel):
    name: str | None = None
    option_type: OptionType | None = None
    swatch_hex: str | None = None
    image_id: uuid.UUID | None = None
    price_cents: int | None = None

    @field_validator("swatch_hex")
    @classmethod
    def _valid_hex(cls, v: str | None) -> str | None:
        if v is not None and not _HEX_RE.match(v):
            raise ValueError("swatch_hex must be a 7-character hex colour like #FF5733")
        return v


class VariantOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    product_id: uuid.UUID
    name: str
    option_type: OptionType
    swatch_hex: str | None
    image_id: uuid.UUID | None
    price_cents: int | None


async def _assert_image_belongs_to_product(
    image_id: uuid.UUID, product_id: uuid.UUID, db: AsyncSession
) -> None:
    """Raise 422 if image_id is not an image of product_id."""
    result = await db.execute(
        select(ProductImage.id).where(
            ProductImage.id == image_id,
            ProductImage.product_id == product_id,
        )
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=422,
            detail="image_id does not belong to this product.",
        )


@router.post("/products/{product_id}/variants", response_model=VariantOut, status_code=201)
async def create_variant(
    product_id: uuid.UUID,
    body: VariantCreate,
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(require_admin),
) -> Variant:
    result = await db.execute(select(Product).where(Product.id == product_id))
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Product not found")

    if body.image_id is not None:
        await _assert_image_belongs_to_product(body.image_id, product_id, db)

    variant = Variant(
        product_id=product_id,
        name=body.name,
        option_type=body.option_type,
        swatch_hex=body.swatch_hex,
        image_id=body.image_id,
        price_cents=body.price_cents,
    )
    db.add(variant)
    await db.commit()
    await db.refresh(variant)
    return variant


@router.patch("/variants/{variant_id}", response_model=VariantOut)
async def update_variant(
    variant_id: uuid.UUID,
    body: VariantUpdate,
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(require_admin),
) -> Variant:
    result = await db.execute(select(Variant).where(Variant.id == variant_id))
    variant = result.scalar_one_or_none()
    if variant is None:
        raise HTTPException(status_code=404, detail="Variant not found")

    fields = body.model_fields_set

    if "image_id" in fields and body.image_id is not None:
        await _assert_image_belongs_to_product(body.image_id, variant.product_id, db)

    if "name" in fields:
        variant.name = body.name
    if "option_type" in fields:
        variant.option_type = body.option_type
    if "swatch_hex" in fields:
        variant.swatch_hex = body.swatch_hex
    if "image_id" in fields:
        variant.image_id = body.image_id
    if "price_cents" in fields:
        variant.price_cents = body.price_cents

    await db.commit()
    await db.refresh(variant)
    return variant


@router.delete("/variants/{variant_id}", status_code=204)
async def delete_variant(
    variant_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(require_admin),
) -> None:
    result = await db.execute(select(Variant).where(Variant.id == variant_id))
    variant = result.scalar_one_or_none()
    if variant is None:
        raise HTTPException(status_code=404, detail="Variant not found")

    await db.delete(variant)
    await db.commit()
