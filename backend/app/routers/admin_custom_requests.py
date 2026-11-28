from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import require_admin
from ..database import get_db
from ..models.admin import AdminUser
from ..models.custom_request import CustomRequest, CustomRequestStatus

router = APIRouter(prefix="/admin/custom-requests", tags=["admin-custom-requests"])


class CustomRequestStatusUpdate(BaseModel):
    status: CustomRequestStatus


class AdminCustomRequestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    email: str
    description: str
    reference_image_url: str | None
    status: CustomRequestStatus
    created_at: datetime


@router.get("", response_model=list[AdminCustomRequestOut])
async def list_custom_requests(
    status: Annotated[CustomRequestStatus | None, Query()] = None,
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(require_admin),
) -> list[CustomRequest]:
    q = select(CustomRequest).order_by(CustomRequest.created_at.desc())
    if status is not None:
        q = q.where(CustomRequest.status == status)
    result = await db.execute(q)
    return list(result.scalars().all())


@router.patch("/{request_id}", response_model=AdminCustomRequestOut)
async def update_custom_request_status(
    request_id: uuid.UUID,
    body: CustomRequestStatusUpdate,
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(require_admin),
) -> CustomRequest:
    result = await db.execute(
        select(CustomRequest).where(CustomRequest.id == request_id)
    )
    request = result.scalar_one_or_none()
    if request is None:
        raise HTTPException(status_code=404, detail="Custom request not found")

    request.status = body.status
    await db.commit()
    await db.refresh(request)
    return request
