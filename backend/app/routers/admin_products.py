from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, field_validator
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import require_admin
from ..database import get_db
from ..models.admin import AdminUser
from ..models.order import OrderItem
from ..models.product import Product, ProductStatus
from ..utils.slugs import unique_slug

router = APIRouter(prefix="/admin/products", tags=["admin-products"])


class ProductCreate(BaseModel):
    collection_id: uuid.UUID
    name: str
    description: str
    price_cents: int
    materials: str
    dimensions: str | None = None
    pattern_credit: str | None = None
    pattern_credit_url: str | None = None
    lead_time: str | None = None
    order_cap: int | None = None
    status: ProductStatus = ProductStatus.draft

    @field_validator("price_cents")
    @classmethod
    def price_must_be_positive(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("price_cents must be positive")
        return v


class ProductUpdate(BaseModel):
    collection_id: uuid.UUID | None = None
    name: str | None = None
    description: str | None = None
    price_cents: int | None = None
    materials: str | None = None
    dimensions: str | None = None
    pattern_credit: str | None = None
    pattern_credit_url: str | None = None
    lead_time: str | None = None
    order_cap: int | None = None
    status: ProductStatus | None = None

    @field_validator("price_cents")
    @classmethod
    def price_must_be_positive(cls, v: int | None) -> int | None:
        if v is not None and v <= 0:
            raise ValueError("price_cents must be positive")
        return v


class ProductOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    collection_id: uuid.UUID
    name: str
    slug: str
    description: str
    price_cents: int
    materials: str
    dimensions: str | None
    pattern_credit: str | None
    pattern_credit_url: str | None
    lead_time: str | None
    order_cap: int | None
    status: ProductStatus
    created_at: datetime


@router.get("", response_model=list[ProductOut])
async def list_products(
    status: Annotated[ProductStatus | None, Query()] = None,
    collection: Annotated[uuid.UUID | None, Query()] = None,
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(require_admin),
) -> list[Product]:
    q = select(Product).order_by(Product.created_at.desc())
    if status is not None:
        q = q.where(Product.status == status)
    if collection is not None:
        q = q.where(Product.collection_id == collection)
    result = await db.execute(q)
    return list(result.scalars().all())


@router.post("", response_model=ProductOut, status_code=201)
async def create_product(
    body: ProductCreate,
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(require_admin),
) -> Product:
    slug = await unique_slug(body.name, db, Product)
    product = Product(
        collection_id=body.collection_id,
        name=body.name,
        slug=slug,
        description=body.description,
        price_cents=body.price_cents,
        materials=body.materials,
        dimensions=body.dimensions,
        pattern_credit=body.pattern_credit,
        pattern_credit_url=body.pattern_credit_url,
        lead_time=body.lead_time,
        order_cap=body.order_cap,
        status=body.status,
    )
    db.add(product)
    await db.commit()
    await db.refresh(product)
    return product


@router.get("/{product_id}", response_model=ProductOut)
async def get_product(
    product_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(require_admin),
) -> Product:
    result = await db.execute(select(Product).where(Product.id == product_id))
    product = result.scalar_one_or_none()
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    return product


@router.patch("/{product_id}", response_model=ProductOut)
async def update_product(
    product_id: uuid.UUID,
    body: ProductUpdate,
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(require_admin),
) -> Product:
    result = await db.execute(select(Product).where(Product.id == product_id))
    product = result.scalar_one_or_none()
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")

    fields = body.model_fields_set
    if "name" in fields:
        product.name = body.name
        # Slug follows the name; exclude_id prevents the product's own current
        # slug from being treated as a collision
        product.slug = await unique_slug(body.name, db, Product, exclude_id=product_id)
    if "collection_id" in fields:
        product.collection_id = body.collection_id
    if "description" in fields:
        product.description = body.description
    if "price_cents" in fields:
        product.price_cents = body.price_cents
    if "materials" in fields:
        product.materials = body.materials
    if "dimensions" in fields:
        product.dimensions = body.dimensions
    if "pattern_credit" in fields:
        product.pattern_credit = body.pattern_credit
    if "pattern_credit_url" in fields:
        product.pattern_credit_url = body.pattern_credit_url
    if "lead_time" in fields:
        product.lead_time = body.lead_time
    if "order_cap" in fields:
        product.order_cap = body.order_cap
    if "status" in fields:
        product.status = body.status

    await db.commit()
    await db.refresh(product)
    return product


@router.post("/{product_id}/archive", response_model=ProductOut)
async def archive_product(
    product_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(require_admin),
) -> Product:
    result = await db.execute(select(Product).where(Product.id == product_id))
    product = result.scalar_one_or_none()
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")

    product.status = ProductStatus.archived
    await db.commit()
    await db.refresh(product)
    return product


@router.delete("/{product_id}", status_code=204)
async def delete_product(
    product_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(require_admin),
) -> None:
    result = await db.execute(select(Product).where(Product.id == product_id))
    product = result.scalar_one_or_none()
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")

    order_count = await db.scalar(
        select(func.count()).select_from(OrderItem).where(OrderItem.product_id == product_id)
    )
    if order_count:
        raise HTTPException(
            status_code=409,
            detail="Product has existing orders and cannot be deleted. Archive it instead.",
        )

    await db.delete(product)
    await db.commit()
