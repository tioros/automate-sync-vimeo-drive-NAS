"""
Pydantic schemas for video-related request/response models.
"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class StatusLogOut(BaseModel):
    from_status: Optional[str] = None
    to_status: str
    message: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class VideoOut(BaseModel):
    id: UUID
    filename: str
    relative_path: str
    drive_file_id: str
    vimeo_uri: Optional[str] = None
    vimeo_folder_uri: Optional[str] = None
    status: str
    checksum: Optional[str] = None
    file_size: Optional[int] = None
    retry_count: int
    last_error: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class VideoDetailOut(VideoOut):
    history: list[StatusLogOut] = []


class VideoPaginatedOut(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[VideoOut]


class RetryResponse(BaseModel):
    message: str
    video_id: str


class ScanResponse(BaseModel):
    message: str
    task_id: Optional[str] = None
