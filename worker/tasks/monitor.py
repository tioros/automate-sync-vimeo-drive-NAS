"""
Monitor task (UC-05): Polls Vimeo for upload/transcode status.
Transitions: VIMEO_UPLOADING → VIMEO_TRANSCODING → SUCCESS.
Handles errors with automatic retry up to 3 attempts.
Runs every 1 minute via Celery Beat.
"""

import logging

from sqlalchemy import select

from worker.celery_app import celery_app
from app.database import get_sync_db
from app.models.video import Video, VideoStatus, StatusLog
from app.services import vimeo as vimeo_service

logger = logging.getLogger(__name__)


@celery_app.task(name="tasks.monitor_vimeo", bind=True, max_retries=1)
def monitor_vimeo(self):
    """
    Polls Vimeo API for all videos in VIMEO_UPLOADING or VIMEO_TRANSCODING status.
    Transitions states according to the state machine in architecture.md §4.
    """
    db = get_sync_db()
    try:
        videos = db.execute(
            select(Video).where(
                Video.status.in_([VideoStatus.VIMEO_UPLOADING, VideoStatus.VIMEO_TRANSCODING])
            )
        ).scalars().all()

        if not videos:
            return {"status": "completed", "monitored": 0}

        logger.info(f"Monitorando {len(videos)} vídeos no Vimeo")
        success_count = 0
        error_count = 0

        for video in videos:
            if not video.vimeo_uri:
                logger.warning(f"Vídeo {video.filename} sem vimeo_uri — ignorando")
                continue

            try:
                data = vimeo_service.get_status(video.vimeo_uri)
                upload_status = data.get("upload", {}).get("status", "unknown")
                transcode_status = data.get("transcode", {}).get("status", "unknown")

                # SUCCESS: transcode complete
                if transcode_status == "complete":
                    old_status = video.status
                    video.status = VideoStatus.SUCCESS
                    log = StatusLog(
                        video_id=video.id,
                        from_status=old_status,
                        to_status=VideoStatus.SUCCESS,
                        message="Transcodificação concluída",
                    )
                    db.add(log)
                    success_count += 1
                    logger.info(f"✅ {video.filename} → SUCCESS")

                # TRANSCODING: upload complete, transcode in progress
                elif upload_status == "complete" and video.status == VideoStatus.VIMEO_UPLOADING:
                    video.status = VideoStatus.VIMEO_TRANSCODING
                    log = StatusLog(
                        video_id=video.id,
                        from_status=VideoStatus.VIMEO_UPLOADING,
                        to_status=VideoStatus.VIMEO_TRANSCODING,
                        message="Upload concluído, transcodificação em andamento",
                    )
                    db.add(log)
                    logger.info(f"🎬 {video.filename} → VIMEO_TRANSCODING")

                # ERROR: any error in upload or transcode
                elif upload_status == "error" or transcode_status == "error":
                    msg = f"upload={upload_status}, transcode={transcode_status}"
                    video.retry_count += 1
                    video.last_error = msg

                    if video.retry_count >= 3:
                        old_status = video.status
                        video.status = VideoStatus.ERROR
                        log = StatusLog(
                            video_id=video.id,
                            from_status=old_status,
                            to_status=VideoStatus.ERROR,
                            message=f"Falha no Vimeo após {video.retry_count} tentativas: {msg}",
                        )
                        db.add(log)
                        error_count += 1
                        logger.error(f"❌ {video.filename} → ERROR: {msg}")
                    else:
                        # Re-enqueue upload with new token
                        from worker.tasks.uploader import upload_to_vimeo
                        upload_to_vimeo.apply_async(args=[str(video.id)], countdown=60)
                        logger.warning(f"⏳ Retry {video.retry_count}/3 para {video.filename}")

            except Exception as e:
                logger.error(f"Erro monitorando {video.filename}: {e}")
                continue

        db.commit()
        logger.info(f"Monitor: {success_count} success, {error_count} errors, {len(videos)} total")
        return {"status": "completed", "success": success_count, "errors": error_count}

    except Exception as e:
        db.rollback()
        logger.error(f"Erro no monitor_vimeo: {e}")
        raise
    finally:
        db.close()
