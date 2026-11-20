from __future__ import annotations

from sqlalchemy import Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base

# Singleton: there is exactly one row in this table, always id=1.
_SETTINGS_ID = 1


class Settings(Base):
    __tablename__ = "settings"

    # Fixed primary key — having an integer PK of 1 makes the singleton intent explicit.
    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=_SETTINGS_ID)
    venmo_handle: Mapped[str | None] = mapped_column(String)
    zelle_contact: Mapped[str | None] = mapped_column(String)
    paypal_link: Mapped[str | None] = mapped_column(Text)
    # Money in cents; defaults match the spec
    shipping_flat_cents: Mapped[int] = mapped_column(
        Integer, nullable=False, default=600, server_default="600"
    )
    dropoff_fee_cents: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    # PRIVATE — must only appear in admin-authenticated responses, never public ones
    pickup_address: Mapped[str | None] = mapped_column(Text)
    contact_email: Mapped[str | None] = mapped_column(String)
    instagram_url: Mapped[str | None] = mapped_column(Text)
    facebook_url: Mapped[str | None] = mapped_column(Text)
    tiktok_url: Mapped[str | None] = mapped_column(Text)
