from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import require_admin
from ..database import get_db
from ..models.admin import AdminUser
from ..models.collection import Collection, CollectionStatus
from ..utils.slugs import unique_slug

router = APIRouter(prefix="/admin/collections", tags=["admin-collections"])


class CollectionCreate(BaseModel):
    name: str
    description: str | None = None
    opens_at: datetime | None = None
    closes_at: datetime | None = None
    status: CollectionStatus = CollectionStatus.draft


class CollectionUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    opens_at: datetime | None = None
    closes_at: datetime | None = None
    status: CollectionStatus | None = None


class CollectionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    slug: str
    description: str | None
    opens_at: datetime | None
    closes_at: datetime | None
    status: CollectionStatus


@router.get("", response_model=list[CollectionOut])
async def list_collections(
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(require_admin),
) -> list[Collection]:
    result = await db.execute(select(Collection).order_by(Collection.name))
    return list(result.scalars().all())


@router.post("", response_model=CollectionOut, status_code=201)
async def create_collection(
    body: CollectionCreate,
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(require_admin),
) -> Collection:
    slug = await unique_slug(body.name, db, Collection)
    collection = Collection(
        name=body.name,
        slug=slug,
        description=body.description,
        opens_at=body.opens_at,
        closes_at=body.closes_at,
        status=body.status,
    )
    db.add(collection)
    await db.commit()
    await db.refresh(collection)
    return collection


@router.patch("/{collection_id}", response_model=CollectionOut)
async def update_collection(
    collection_id: uuid.UUID,
    body: CollectionUpdate,
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(require_admin),
) -> Collection:
    result = await db.execute(select(Collection).where(Collection.id == collection_id))
    collection = result.scalar_one_or_none()
    if collection is None:
        raise HTTPException(status_code=404, detail="Collection not found")

    if "name" in body.model_fields_set:
        collection.name = body.name
        collection.slug = await unique_slug(body.name, db, Collection, exclude_id=collection_id)
    if "description" in body.model_fields_set:
        collection.description = body.description
    if "opens_at" in body.model_fields_set:
        collection.opens_at = body.opens_at
    if "closes_at" in body.model_fields_set:
        collection.closes_at = body.closes_at
    if "status" in body.model_fields_set:
        collection.status = body.status

    await db.commit()
    await db.refresh(collection)
    return collection


@router.post("/{collection_id}/archive", response_model=CollectionOut)
async def archive_collection(
    collection_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(require_admin),
) -> Collection:
    result = await db.execute(select(Collection).where(Collection.id == collection_id))
    collection = result.scalar_one_or_none()
    if collection is None:
        raise HTTPException(status_code=404, detail="Collection not found")

    collection.status = CollectionStatus.archived
    await db.commit()
    await db.refresh(collection)
    return collection
