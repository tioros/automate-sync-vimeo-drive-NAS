"""
Upload task (UC-04): Dispatches pull upload to Vimeo for DRIVE_READY files.
Token is generated immediately before POST and never stored.
"""

import logging

from sqlalchemy import select

from worker.celery_app import celery_app
from app.database import get_sync_db
from app.models.config import SystemConfig
from app.models.video import Video, VideoStatus, StatusLog
from app.services import drive as drive_service
from app.services import vimeo as vimeo_service

logger = logging.getLogger(__name__)


@celery_app.task(name="tasks.upload_to_vimeo", bind=True, max_retries=3)
def upload_to_vimeo(self, video_id: str):
    """
    Resolves the Vimeo destination folder, generates an SA download URL,
    and initiates a pull upload. Handles retries with fresh tokens.
    """
    db = get_sync_db()
    try:
        video = db.execute(select(Video).where(Video.id == video_id)).scalar_one_or_none()
        if not video:
            logger.error(f"Vídeo não encontrado: {video_id}")
            return

        config = db.execute(select(SystemConfig)).scalar_one_or_none()
        if not config:
            logger.error("Config não encontrada — upload abortado")
            return

        logger.info(f"Iniciando upload: {video.filename} (path: {video.relative_path})")

        # 1. Resolve Vimeo destination folder
        vimeo_folder_uri = vimeo_service.resolve_folder(
            root_uri=config.vimeo_root_folder_uri,
            relative_path=video.relative_path,
        )

        # 2. Generate authenticated download URL (token never stored)
        download_url = drive_service.generate_download_url(video.drive_file_id)

        # 3. POST pull upload to Vimeo
        vimeo_uri = vimeo_service.pull_upload(
            link=download_url,
            name=video.filename,
            folder_uri=vimeo_folder_uri,
            size=video.file_size or 0,
        )

        # 4. Update video record
        old_status = video.status
        video.status = VideoStatus.VIMEO_UPLOADING
        video.vimeo_uri = vimeo_uri
        video.vimeo_folder_uri = vimeo_folder_uri

        log = StatusLog(
            video_id=video.id,
            from_status=old_status,
            to_status=VideoStatus.VIMEO_UPLOADING,
            message=f"Pull upload iniciado → {vimeo_uri}",
        )
        db.add(log)
        db.commit()

        logger.info(f"✅ Upload enfileirado: {video.filename} → {vimeo_uri}")

    except Exception as e:
        db.rollback()
        logger.error(f"Erro no upload de {video_id}: {e}")

        # Handle retry logic
        try:
            video = db.execute(select(Video).where(Video.id == video_id)).scalar_one_or_none()
            if video:
                video.retry_count += 1
                video.last_error = str(e)[:2000]

                if video.retry_count >= 3:
                    old_status = video.status
                    video.status = VideoStatus.ERROR
                    log = StatusLog(
                        video_id=video.id,
                        from_status=old_status,
                        to_status=VideoStatus.ERROR,
                        message=f"Falha após {video.retry_count} tentativas: {str(e)[:500]}",
                    )
                    db.add(log)
                    logger.error(f"❌ {video.filename} → ERROR após {video.retry_count} tentativas")
                else:
                    # Re-enqueue with new token (countdown gives time before retry)
                    upload_to_vimeo.apply_async(args=[video_id], countdown=60)
                    logger.warning(f"⏳ Retry {video.retry_count}/3 agendado para {video.filename}")

                db.commit()
        except Exception as retry_error:
            db.rollback()
            logger.error(f"Erro ao registrar retry: {retry_error}")
    finally:
        db.close()
