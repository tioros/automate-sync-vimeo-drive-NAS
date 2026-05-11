"""
ORM model for the system_config table.
Always contains exactly one row with the global configuration.
"""

from datetime import datetime, timezone

from sqlalchemy import Column, Integer, String, DateTime

from app.database import Base


class SystemConfig(Base):
    __tablename__ = "system_config"

    id = Column(Integer, primary_key=True, autoincrement=True)
    drive_root_folder_id = Column(String(256), nullable=False)
    vimeo_root_folder_uri = Column(String(256), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
