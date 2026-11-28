from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..models.collection import Collection, CollectionStatus
from ..models.order import OrderItem
from ..models.product import Product, ProductStatus
from ..models.variant import Variant


async def validate_cart_items(
    items: list[Any],  # each item: .product_id, .variant_id, .quantity
    db: AsyncSession,
    now: datetime,
) -> tuple[list[dict], list[dict]]:
    """
    Validate cart items against live DB state; collect all errors before returning.

    Returns (validated, errors).
      validated: [{product, variant, unit_price_cents, quantity}, ...]
      errors:    [{product_id, error}, ...]
    """
    errors: list[dict] = []
    validated: list[dict] = []

    for item in items:
        product_result = await db.execute(
            select(Product)
            .where(Product.id == item.product_id)
            .options(selectinload(Product.collection))
        )
        product = product_result.scalar_one_or_none()

        if product is None:
            errors.append({"product_id": str(item.product_id), "error": "product not found"})
            continue

        if product.status != ProductStatus.live:
            errors.append({"product_id": str(item.product_id), "error": "product is not available"})
            continue

        coll: Collection = product.collection
        if coll.status != CollectionStatus.live:
            errors.append({
                "product_id": str(item.product_id),
                "error": "collection is not open for orders",
            })
            continue

        if coll.opens_at is not None and coll.opens_at > now:
            errors.append({
                "product_id": str(item.product_id),
                "error": "collection has not opened yet",
            })
            continue

        if coll.closes_at is not None and coll.closes_at < now:
            errors.append({
                "product_id": str(item.product_id),
                "error": "collection is closed",
            })
            continue

        variant: Variant | None = None
        if item.variant_id is not None:
            variant_result = await db.execute(
                select(Variant).where(Variant.id == item.variant_id)
            )
            variant = variant_result.scalar_one_or_none()
            if variant is None or variant.product_id != product.id:
                errors.append({
                    "product_id": str(item.product_id),
                    "error": "variant not found for this product",
                })
                continue

        if product.order_cap is not None:
            existing_qty = await db.scalar(
                select(func.coalesce(func.sum(OrderItem.quantity), 0)).where(
                    OrderItem.product_id == product.id
                )
            )
            if (existing_qty or 0) + item.quantity > product.order_cap:
                errors.append({
                    "product_id": str(item.product_id),
                    "error": f"order cap of {product.order_cap} units exceeded",
                })
                continue

        unit_price = (
            variant.price_cents
            if (variant and variant.price_cents is not None)
            else product.price_cents
        )
        validated.append({
            "product": product,
            "variant": variant,
            "unit_price_cents": unit_price,
            "quantity": item.quantity,
        })

    return validated, errors
