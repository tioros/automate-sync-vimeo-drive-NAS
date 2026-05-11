"""
Pydantic schemas for system configuration.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class ConfigOut(BaseModel):
    drive_root_folder_id: str
    vimeo_root_folder_uri: str
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class ConfigUpdate(BaseModel):
    drive_root_folder_id: str
    vimeo_root_folder_uri: str
