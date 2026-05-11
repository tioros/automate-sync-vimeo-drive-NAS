"""
Admin router: retry and scan endpoints.
All endpoints require Admin role.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.auth import RequireRole
from app.models.video import Video, VideoStatus, StatusLog
from app.schemas.video import RetryResponse, ScanResponse

router = APIRouter(
    prefix="/api/v1/admin",
    tags=["admin"],
    dependencies=[Depends(RequireRole("admin"))],
)


@router.post("/videos/{video_id}/retry", response_model=RetryResponse)
async def retry_video(
    video_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """
    Force retry of a video in ERROR state. Resets retry_count to 0.
    Admin only (UC-07).
    """
    result = await db.execute(select(Video).where(Video.id == video_id))
    video = result.scalar_one_or_none()

    if not video:
        raise HTTPException(status_code=404, detail="Vídeo não encontrado")

    if video.status != VideoStatus.ERROR:
        raise HTTPException(status_code=400, detail=f"Vídeo não está em ERROR (status atual: {video.status.value})")

    # Reset and re-enqueue
    old_status = video.status
    video.retry_count = 0
    video.last_error = None
    video.status = VideoStatus.DRIVE_READY

    log = StatusLog(
        video_id=video.id,
        from_status=old_status,
        to_status=VideoStatus.DRIVE_READY,
        message="Retry manual pelo Admin",
    )
    db.add(log)
    await db.flush()

    # Enqueue Celery task
    from worker.tasks.uploader import upload_to_vimeo
    upload_to_vimeo.delay(str(video.id))

    return RetryResponse(message="Retry enqueued", video_id=str(video.id))


@router.post("/scan", response_model=ScanResponse)
async def trigger_scan():
    """
    Triggers an immediate drive scan. Admin only.
    """
    from worker.tasks.scanner import scan_drive
    result = scan_drive.delay()
    return ScanResponse(message="Scan started", task_id=str(result.id))
