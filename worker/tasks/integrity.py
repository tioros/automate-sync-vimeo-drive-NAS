"""
Integrity check task (UC-03): Validates MD5 checksum stability using a
size-proportional verification window before allowing upload.
Runs every 2 minutes via Celery Beat.
"""

import time
import logging

from sqlalchemy import select

from worker.celery_app import celery_app
from app.database import get_sync_db
from app.models.video import Video, VideoStatus, StatusLog
from app.services.drive import get_file_meta, get_verification_window

logger = logging.getLogger(__name__)


@celery_app.task(name="tasks.check_integrity", bind=True, max_retries=1)
def check_integrity(self):
    """
    Checks MD5 stability for files in DISCOVERED or DRIVE_SYNC_PENDING status.
    Uses a proportional verification window based on file size.
    """
    db = get_sync_db()
    try:
        videos = db.execute(
            select(Video).where(
                Video.status.in_([VideoStatus.DISCOVERED, VideoStatus.DRIVE_SYNC_PENDING])
            )
        ).scalars().all()

        if not videos:
            return {"status": "completed", "checked": 0}

        logger.info(f"Verificando integridade de {len(videos)} arquivos")
        ready_count = 0
        pending_count = 0

        for video in videos:
            try:
                file_size = video.file_size or 0
                verifications, interval = get_verification_window(file_size)
                checksums = []
                final_data = None

                for i in range(verifications):
                    data = get_file_meta(video.drive_file_id)
                    md5 = data.get("md5Checksum")

                    if not md5:
                        # File still being uploaded to Drive
                        if video.status != VideoStatus.DRIVE_SYNC_PENDING:
                            video.status = VideoStatus.DRIVE_SYNC_PENDING
                            log = StatusLog(
                                video_id=video.id,
                                from_status=VideoStatus.DISCOVERED,
                                to_status=VideoStatus.DRIVE_SYNC_PENDING,
                                message="MD5 ausente — arquivo ainda sincronizando no Drive",
                            )
                            db.add(log)
                        pending_count += 1
                        checksums = []  # Reset to break out
                        break

                    checksums.append(md5)
                    final_data = data

                    # Wait between checks (except after the last one)
                    if i < verifications - 1:
                        time.sleep(interval)

                # Check if MD5 was stable across all verifications
                if len(checksums) == verifications and len(set(checksums)) == 1:
                    old_status = video.status
                    video.status = VideoStatus.DRIVE_READY
                    video.checksum = checksums[0]
                    video.file_size = int(final_data.get("size", video.file_size or 0))

                    log = StatusLog(
                        video_id=video.id,
                        from_status=old_status,
                        to_status=VideoStatus.DRIVE_READY,
                        message=f"MD5 estável após {verifications} verificações ({interval}s intervalo)",
                    )
                    db.add(log)
                    ready_count += 1
                    logger.info(f"✅ {video.filename} → DRIVE_READY (MD5: {checksums[0][:12]}...)")

                elif checksums and len(set(checksums)) > 1:
                    # MD5 changed between checks — file still being written
                    if video.status != VideoStatus.DRIVE_SYNC_PENDING:
                        video.status = VideoStatus.DRIVE_SYNC_PENDING
                        log = StatusLog(
                            video_id=video.id,
                            from_status=video.status,
                            to_status=VideoStatus.DRIVE_SYNC_PENDING,
                            message="MD5 instável entre verificações",
                        )
                        db.add(log)
                    pending_count += 1

            except Exception as e:
                logger.error(f"Erro verificando {video.filename}: {e}")
                continue

        db.commit()
        logger.info(f"Integridade: {ready_count} prontos, {pending_count} pendentes")
        return {"status": "completed", "ready": ready_count, "pending": pending_count}

    except Exception as e:
        db.rollback()
        logger.error(f"Erro no check_integrity: {e}")
        raise
    finally:
        db.close()
