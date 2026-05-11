"""
Scanner task (UC-02): Discovers new .mp4 files in the configured Drive root folder.
Runs every 5 minutes via Celery Beat.
"""

import logging

from sqlalchemy import select

from worker.celery_app import celery_app
from app.database import get_sync_db
from app.models.config import SystemConfig
from app.models.video import Video, VideoStatus, StatusLog
from app.services import drive

logger = logging.getLogger(__name__)


@celery_app.task(name="tasks.scan_drive", bind=True, max_retries=1)
def scan_drive(self):
    """
    Scans the configured Drive root folder for new .mp4 files.
    Creates a record with status=DISCOVERED for each new file found.
    Idempotent: UNIQUE constraint on drive_file_id prevents duplicates.
    """
    db = get_sync_db()
    try:
        # Get config
        config = db.execute(select(SystemConfig)).scalar_one_or_none()
        if not config:
            logger.warning("Scan abortado: system_config não configurado")
            return {"status": "skipped", "reason": "no_config"}

        # List all mp4 files in Drive
        logger.info(f"Iniciando scan na pasta raiz: {config.drive_root_folder_id}")
        files = drive.list_all_mp4(config.drive_root_folder_id)
        logger.info(f"Encontrados {len(files)} arquivos .mp4 no Drive")

        new_count = 0
        for file in files:
            # Check if already exists
            existing = db.execute(
                select(Video).where(Video.drive_file_id == file["id"])
            ).scalar_one_or_none()

            if existing:
                continue

            # Create new video record
            video = Video(
                filename=file["name"],
                drive_file_id=file["id"],
                relative_path=file["path"],
                file_size=int(file.get("size", 0)),
                status=VideoStatus.DISCOVERED,
            )
            db.add(video)
            db.flush()

            # Log the state transition
            log = StatusLog(
                video_id=video.id,
                from_status=None,
                to_status=VideoStatus.DISCOVERED,
                message=f"Arquivo descoberto: {file['name']}",
            )
            db.add(log)
            new_count += 1

        db.commit()
        logger.info(f"Scan concluído: {new_count} novos arquivos adicionados")
        return {"status": "completed", "new_files": new_count, "total_scanned": len(files)}

    except Exception as e:
        db.rollback()
        logger.error(f"Erro no scan: {e}")
        raise
    finally:
        db.close()
