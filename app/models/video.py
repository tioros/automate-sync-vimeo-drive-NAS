"""
ORM models for the videos table and status_logs table.
Implements the state machine defined in architecture.md.
"""

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Column, String, BigInteger, Integer, Text, DateTime, ForeignKey, Index, Enum as SAEnum
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.database import Base


class VideoStatus(str, enum.Enum):
    DISCOVERED = "DISCOVERED"
    DRIVE_SYNC_PENDING = "DRIVE_SYNC_PENDING"
    DRIVE_READY = "DRIVE_READY"
    VIMEO_UPLOADING = "VIMEO_UPLOADING"
    VIMEO_TRANSCODING = "VIMEO_TRANSCODING"
    SUCCESS = "SUCCESS"
    ERROR = "ERROR"


class Video(Base):
    __tablename__ = "videos"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    filename = Column(String(512), nullable=False)
    relative_path = Column(String(1024), nullable=False)
    drive_file_id = Column(String(256), nullable=False, unique=True)
    vimeo_uri = Column(String(256), nullable=True)
    vimeo_folder_uri = Column(String(256), nullable=True)
    status = Column(SAEnum(VideoStatus, name="video_status", create_constraint=True), nullable=False, default=VideoStatus.DISCOVERED)
    checksum = Column(String(64), nullable=True)
    file_size = Column(BigInteger, nullable=True)
    retry_count = Column(Integer, nullable=False, default=0)
    last_error = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    status_logs = relationship("StatusLog", back_populates="video", order_by="StatusLog.created_at")

    __table_args__ = (
        Index("idx_videos_status", "status"),
        Index("idx_videos_relative_path", "relative_path"),
        Index("idx_videos_drive_file_id", "drive_file_id"),
    )


class StatusLog(Base):
    __tablename__ = "status_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    video_id = Column(UUID(as_uuid=True), ForeignKey("videos.id"), nullable=False)
    from_status = Column(SAEnum(VideoStatus, name="video_status", create_constraint=False), nullable=True)
    to_status = Column(SAEnum(VideoStatus, name="video_status", create_constraint=False), nullable=False)
    message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    video = relationship("Video", back_populates="status_logs")

    __table_args__ = (
        Index("idx_status_logs_video_id", "video_id"),
    )
