"""
Videos router: list and detail endpoints.
Accessible by both Admin and Auditor.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.auth import get_current_user
from app.models.user import User
from app.models.video import Video, VideoStatus, StatusLog
from app.schemas.video import VideoOut, VideoDetailOut, VideoPaginatedOut, StatusLogOut

router = APIRouter(prefix="/api/v1/videos", tags=["videos"])


@router.get("", response_model=VideoPaginatedOut)
async def list_videos(
    status: str | None = Query(None),
    relative_path: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Lists videos with optional filters and pagination."""
    query = select(Video)
    count_query = select(func.count(Video.id))

    if status:
        try:
            status_enum = VideoStatus(status)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Status inválido: {status}")
        query = query.where(Video.status == status_enum)
        count_query = count_query.where(Video.status == status_enum)

    if relative_path:
        query = query.where(Video.relative_path == relative_path)
        count_query = count_query.where(Video.relative_path == relative_path)

    # Total count
    total_result = await db.execute(count_query)
    total = total_result.scalar()

    # Paginated results
    query = query.order_by(Video.updated_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    items = result.scalars().all()

    return VideoPaginatedOut(
        total=total,
        page=page,
        page_size=page_size,
        items=[VideoOut.model_validate(v) for v in items],
    )


@router.get("/{video_id}", response_model=VideoDetailOut)
async def get_video(
    video_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Returns video detail with full state history."""
    result = await db.execute(
        select(Video)
        .options(selectinload(Video.status_logs))
        .where(Video.id == video_id)
    )
    video = result.scalar_one_or_none()

    if not video:
        raise HTTPException(status_code=404, detail="Vídeo não encontrado")

    video_data = VideoOut.model_validate(video).model_dump()
    video_data["history"] = [
        StatusLogOut.model_validate(log) for log in video.status_logs
    ]

    return VideoDetailOut(**video_data)
