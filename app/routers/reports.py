"""
Reports router: summary, by-folder, and CSV export endpoints.
Accessible by both Admin and Auditor.
"""

import csv
import io
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select, func, case
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.auth import get_current_user
from app.models.user import User
from app.models.video import Video, VideoStatus

router = APIRouter(prefix="/api/v1/reports", tags=["reports"])


@router.get("/summary")
async def reports_summary(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Returns total file count and breakdown by status."""
    # Count total
    total_result = await db.execute(select(func.count(Video.id)))
    total = total_result.scalar()

    # Count by status
    by_status = {}
    for s in VideoStatus:
        count_result = await db.execute(
            select(func.count(Video.id)).where(Video.status == s)
        )
        by_status[s.value] = count_result.scalar()

    return {"total_files": total, "by_status": by_status}


@router.get("/by-folder")
async def reports_by_folder(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Groups video count by relative_path and status."""
    result = await db.execute(
        select(Video.relative_path, Video.status, func.count(Video.id))
        .group_by(Video.relative_path, Video.status)
        .order_by(Video.relative_path)
    )
    rows = result.all()

    # Aggregate into per-folder dicts
    folders = {}
    for path, status, count in rows:
        if path not in folders:
            folders[path] = {"relative_path": path, "counts": {}, "total": 0}
        folders[path]["counts"][status.value] = count
        folders[path]["total"] += count

    return list(folders.values())


@router.get("/export")
async def reports_export(
    status: str | None = Query(None),
    relative_path: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Exports filtered videos as CSV."""
    query = select(Video)

    if status:
        try:
            query = query.where(Video.status == VideoStatus(status))
        except ValueError:
            pass

    if relative_path:
        query = query.where(Video.relative_path == relative_path)

    query = query.order_by(Video.updated_at.desc())
    result = await db.execute(query)
    videos = result.scalars().all()

    # Build CSV
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["id", "filename", "relative_path", "status", "vimeo_uri", "retry_count", "last_error", "updated_at"])

    for v in videos:
        writer.writerow([
            str(v.id),
            v.filename,
            v.relative_path,
            v.status.value,
            v.vimeo_uri or "",
            v.retry_count,
            v.last_error or "",
            v.updated_at.isoformat() if v.updated_at else "",
        ])

    output.seek(0)
    filename = f"relatorio_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
