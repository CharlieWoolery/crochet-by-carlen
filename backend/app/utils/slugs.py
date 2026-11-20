from __future__ import annotations

import re
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


def _base_slug(name: str) -> str:
    s = name.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = s.strip("-")
    return s or "item"  # fallback if the name is entirely non-ASCII


async def unique_slug(
    name: str,
    db: AsyncSession,
    model: Any,
    exclude_id: uuid.UUID | None = None,
) -> str:
    """
    Derive a URL-safe slug from name. If the base slug is already taken,
    append -2, -3, etc. until a free one is found.

    Pass exclude_id when updating an existing row so the row's current slug
    is not counted as a collision against itself.
    """
    base = _base_slug(name)
    candidate = base
    n = 2
    while True:
        q = select(model.id).where(model.slug == candidate)
        if exclude_id is not None:
            q = q.where(model.id != exclude_id)
        exists = (await db.execute(q)).scalar_one_or_none()
        if exists is None:
            return candidate
        candidate = f"{base}-{n}"
        n += 1
