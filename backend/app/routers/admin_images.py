from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from pydantic import BaseModel, ConfigDict, field_validator
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import require_admin
from ..database import get_db
from ..images import processing
from ..images import storage as image_storage
from ..models.admin import AdminUser
from ..models.product import Product
from ..models.product_image import ProductImage

router = APIRouter(prefix="/admin", tags=["admin-images"])

ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/heic", "image/heif"}
MAX_UPLOAD_BYTES = 25 * 1024 * 1024  # 25 MB


class ImageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    product_id: uuid.UUID
    storage_key: str
    url_small: str
    url_medium: str
    url_large: str
    width: int
    height: int
    focal_x: int
    focal_y: int
    alt_text: str | None
    sort_order: int


class ImageUpdate(BaseModel):
    focal_x: int | None = None
    focal_y: int | None = None
    alt_text: str | None = None

    @field_validator("focal_x", "focal_y")
    @classmethod
    def _in_range(cls, v: int | None) -> int | None:
        if v is not None and not (0 <= v <= 100):
            raise ValueError("must be between 0 and 100")
        return v


class ImageOrderBody(BaseModel):
    image_ids: list[uuid.UUID]


@router.post("/products/{product_id}/images", response_model=ImageOut, status_code=201)
async def upload_image(
    product_id: uuid.UUID,
    file: UploadFile,
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(require_admin),
) -> ProductImage:
    result = await db.execute(select(Product).where(Product.id == product_id))
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Product not found")

    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported file type '{file.content_type}'. Accepted: JPEG, PNG, HEIC.",
        )

    raw = await file.read()
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File exceeds 25 MB limit.")

    try:
        processed = processing.process_image(raw)
    except Exception:
        raise HTTPException(
            status_code=422,
            detail="Could not process image. File may be corrupt or unsupported.",
        )

    # storage_key is the shared prefix; the three objects are {prefix}/{size}.webp
    image_id = uuid.uuid4()
    prefix = f"products/{product_id}/{image_id}"

    url_small = image_storage.upload(f"{prefix}/small.webp", processed.small)
    url_medium = image_storage.upload(f"{prefix}/medium.webp", processed.medium)
    url_large = image_storage.upload(f"{prefix}/large.webp", processed.large)

    # Place the new image after all existing ones for this product
    max_order = await db.scalar(
        select(func.coalesce(func.max(ProductImage.sort_order), -1))
        .where(ProductImage.product_id == product_id)
    )

    image = ProductImage(
        id=image_id,
        product_id=product_id,
        storage_key=prefix,
        url_small=url_small,
        url_medium=url_medium,
        url_large=url_large,
        width=processed.original_width,
        height=processed.original_height,
        sort_order=max_order + 1,
    )
    db.add(image)
    await db.commit()
    await db.refresh(image)
    return image


@router.patch("/images/{image_id}", response_model=ImageOut)
async def update_image(
    image_id: uuid.UUID,
    body: ImageUpdate,
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(require_admin),
) -> ProductImage:
    result = await db.execute(select(ProductImage).where(ProductImage.id == image_id))
    image = result.scalar_one_or_none()
    if image is None:
        raise HTTPException(status_code=404, detail="Image not found")

    fields = body.model_fields_set
    if "focal_x" in fields:
        image.focal_x = body.focal_x
    if "focal_y" in fields:
        image.focal_y = body.focal_y
    if "alt_text" in fields:
        image.alt_text = body.alt_text

    await db.commit()
    await db.refresh(image)
    return image


@router.put("/products/{product_id}/images/order", response_model=list[ImageOut])
async def reorder_images(
    product_id: uuid.UUID,
    body: ImageOrderBody,
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(require_admin),
) -> list[ProductImage]:
    result = await db.execute(select(Product).where(Product.id == product_id))
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Product not found")

    result = await db.execute(
        select(ProductImage).where(ProductImage.product_id == product_id)
    )
    images = result.scalars().all()
    image_map = {img.id: img for img in images}

    # Require the submitted list to exactly match the product's current images
    if set(body.image_ids) != set(image_map.keys()) or len(body.image_ids) != len(image_map):
        raise HTTPException(
            status_code=422,
            detail="image_ids must contain exactly the product's current image IDs with no duplicates.",
        )

    for order, img_id in enumerate(body.image_ids):
        image_map[img_id].sort_order = order

    await db.commit()
    return [image_map[img_id] for img_id in body.image_ids]


@router.delete("/images/{image_id}", status_code=204)
async def delete_image(
    image_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(require_admin),
) -> None:
    result = await db.execute(select(ProductImage).where(ProductImage.id == image_id))
    image = result.scalar_one_or_none()
    if image is None:
        raise HTTPException(status_code=404, detail="Image not found")

    # Remove all three sizes from object storage before deleting the DB row
    image_storage.delete_keys([
        f"{image.storage_key}/small.webp",
        f"{image.storage_key}/medium.webp",
        f"{image.storage_key}/large.webp",
    ])

    await db.delete(image)
    await db.commit()
