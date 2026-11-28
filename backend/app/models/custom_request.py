from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, String, Text, func
from sqlalchemy import Uuid
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class CustomRequestStatus(str, enum.Enum):
    new = "new"
    quoted = "quoted"
    accepted = "accepted"
    declined = "declined"


class CustomRequest(Base):
    __tablename__ = "custom_requests"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String, nullable=False)
    email: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    reference_image_url: Mapped[str | None] = mapped_column(Text)
    status: Mapped[CustomRequestStatus] = mapped_column(
        Enum(CustomRequestStatus, name="custom_request_status"),
        nullable=False,
        default=CustomRequestStatus.new,
        server_default=CustomRequestStatus.new.value,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
