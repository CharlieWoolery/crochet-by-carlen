from __future__ import annotations

import re
import uuid
from datetime import datetime

from fastapi import Depends, HTTPException
from fastapi.routing import APIRouter
from pydantic import BaseModel, ConfigDict, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..email import CustomRequestNotificationData, send_custom_request_notification
from ..models.custom_request import CustomRequest, CustomRequestStatus
from ..models.settings import Settings, _SETTINGS_ID

router = APIRouter(tags=["custom-requests"])

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class CustomRequestIn(BaseModel):
    name: str
    email: str
    description: str
    reference_image_url: str | None = None

    @field_validator("name")
    @classmethod
    def _non_empty_name(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("name must not be blank")
        return v.strip()

    @field_validator("email")
    @classmethod
    def _valid_email(cls, v: str) -> str:
        if not _EMAIL_RE.match(v):
            raise ValueError("invalid email address")
        return v.lower().strip()

    @field_validator("description")
    @classmethod
    def _non_empty_description(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("description must not be blank")
        return v.strip()


class CustomRequestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    email: str
    description: str
    reference_image_url: str | None
    status: CustomRequestStatus
    created_at: datetime


@router.post("/custom-requests", response_model=CustomRequestOut, status_code=201)
async def submit_custom_request(
    body: CustomRequestIn,
    db: AsyncSession = Depends(get_db),
) -> CustomRequest:
    request = CustomRequest(
        name=body.name,
        email=body.email,
        description=body.description,
        reference_image_url=body.reference_image_url,
        status=CustomRequestStatus.new,
    )
    db.add(request)
    await db.commit()
    await db.refresh(request)

    # Load owner's contact email for the notification (None if not configured)
    settings_result = await db.execute(select(Settings).where(Settings.id == _SETTINGS_ID))
    settings = settings_result.scalar_one_or_none()
    owner_email = settings.contact_email if settings else None

    await send_custom_request_notification(
        CustomRequestNotificationData(
            request_id=request.id,
            customer_name=request.name,
            customer_email=request.email,
            description=request.description,
            reference_image_url=request.reference_image_url,
            owner_email=owner_email,
        )
    )

    return request
