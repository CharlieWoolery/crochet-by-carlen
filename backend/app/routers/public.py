from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import Depends, HTTPException
from fastapi.routing import APIRouter
from pydantic import BaseModel, ConfigDict
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..database import get_db
from ..models.collection import Collection, CollectionStatus
from ..models.product import Product, ProductStatus
from ..models.variant import OptionType

router = APIRouter(tags=["public"])


class PublicImageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    url_small: str
    url_medium: str
    url_large: str
    focal_x: int
    focal_y: int
    alt_text: str | None
    width: int
    height: int
    sort_order: int


class PublicVariantOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    option_type: OptionType
    swatch_hex: str | None
    image_id: uuid.UUID | None
    price_cents: int | None


class PublicProductOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    slug: str
    description: str
    price_cents: int
    materials: str
    dimensions: str | None
    pattern_credit: str | None
    pattern_credit_url: str | None
    lead_time: str | None
    images: list[PublicImageOut]
    variants: list[PublicVariantOut]


class PublicCollectionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    slug: str
    description: str | None
    opens_at: datetime | None
    closes_at: datetime | None


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@router.get("/collections", response_model=list[PublicCollectionOut])
async def list_collections(db: AsyncSession = Depends(get_db)) -> list[Collection]:
    now = _utcnow()
    stmt = (
        select(Collection)
        .where(
            Collection.status == CollectionStatus.live,
            or_(Collection.opens_at.is_(None), Collection.opens_at <= now),
            or_(Collection.closes_at.is_(None), Collection.closes_at >= now),
        )
        .order_by(Collection.name)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.get("/collections/archived", response_model=list[PublicCollectionOut])
async def list_archived_collections(db: AsyncSession = Depends(get_db)) -> list[Collection]:
    stmt = (
        select(Collection)
        .where(Collection.status == CollectionStatus.archived)
        .order_by(Collection.name)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.get("/products", response_model=list[PublicProductOut])
async def list_products(
    collection: str,
    db: AsyncSession = Depends(get_db),
) -> list[Product]:
    # Draft collections are not publicly accessible; archived are (past-work gallery)
    coll_result = await db.execute(
        select(Collection).where(Collection.slug == collection)
    )
    coll = coll_result.scalar_one_or_none()
    if coll is None or coll.status == CollectionStatus.draft:
        raise HTTPException(status_code=404, detail="Collection not found")

    stmt = (
        select(Product)
        .where(
            Product.collection_id == coll.id,
            Product.status == ProductStatus.live,
        )
        .options(
            selectinload(Product.images),
            selectinload(Product.variants),
        )
        .order_by(Product.name)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.get("/products/{slug}", response_model=PublicProductOut)
async def get_product(slug: str, db: AsyncSession = Depends(get_db)) -> Product:
    stmt = (
        select(Product)
        .where(Product.slug == slug, Product.status == ProductStatus.live)
        .options(
            selectinload(Product.images),
            selectinload(Product.variants),
        )
    )
    result = await db.execute(stmt)
    product = result.scalar_one_or_none()
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    return product
