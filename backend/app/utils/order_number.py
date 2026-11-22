from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def next_order_number(db: AsyncSession) -> str:
    """
    Return the next order number using the Postgres sequence.
    Atomic and race-safe: two concurrent requests can never get the same number.
    """
    val = await db.scalar(text("SELECT nextval('order_number_seq')"))
    return f"CBC-{val}"
