"""
Config router: system configuration endpoints.
GET is accessible by Admin and Auditor. PUT is Admin only.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.auth import get_current_user, RequireRole
from app.models.user import User
from app.models.config import SystemConfig
from app.schemas.config import ConfigOut, ConfigUpdate

router = APIRouter(prefix="/api/v1/config", tags=["config"])


@router.get("", response_model=ConfigOut | dict)
async def get_config(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Returns the current system configuration."""
    result = await db.execute(select(SystemConfig))
    config = result.scalar_one_or_none()

    if not config:
        return {"drive_root_folder_id": "", "vimeo_root_folder_uri": "", "updated_at": None}

    return ConfigOut.model_validate(config)


@router.put("", response_model=ConfigOut, dependencies=[Depends(RequireRole("admin"))])
async def update_config(
    payload: ConfigUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Updates system configuration. Admin only."""
    result = await db.execute(select(SystemConfig))
    config = result.scalar_one_or_none()

    if config:
        config.drive_root_folder_id = payload.drive_root_folder_id
        config.vimeo_root_folder_uri = payload.vimeo_root_folder_uri
    else:
        config = SystemConfig(
            drive_root_folder_id=payload.drive_root_folder_id,
            vimeo_root_folder_uri=payload.vimeo_root_folder_uri,
        )
        db.add(config)

    await db.flush()
    return ConfigOut.model_validate(config)
