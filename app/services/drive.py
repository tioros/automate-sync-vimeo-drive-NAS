"""
Google Drive API service.
Handles recursive listing, MD5 integrity checks, and authenticated download URL generation.
See contracts.md §2 for full API contract details.
"""

import os
import logging

from google.oauth2 import service_account
import google.auth.transport.requests
from googleapiclient.discovery import build

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]


def _get_drive_service():
    """Build an authenticated Google Drive API service."""
    creds = service_account.Credentials.from_service_account_file(
        settings.google_sa_key_path, scopes=SCOPES
    )
    return build("drive", "v3", credentials=creds)


def list_all_mp4(root_folder_id: str) -> list[dict]:
    """
    Recursively lists all .mp4 files under the root folder.
    Returns list of dicts with: id, name, path (full folder path), size, md5Checksum.
    """
    service = _get_drive_service()
    results = []

    def _scan_folder(folder_id: str, current_path: str):
        # List subfolders
        page_token = None
        while True:
            resp = service.files().list(
                q=f"'{folder_id}' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false",
                fields="files(id,name),nextPageToken",
                pageSize=100,
                pageToken=page_token,
            ).execute()
            for folder in resp.get("files", []):
                _scan_folder(folder["id"], f"{current_path}{folder['name']}/")
            page_token = resp.get("nextPageToken")
            if not page_token:
                break

        # List mp4 files
        page_token = None
        while True:
            resp = service.files().list(
                q=f"'{folder_id}' in parents and mimeType='video/mp4' and trashed=false",
                fields="files(id,name,md5Checksum,size),nextPageToken",
                pageSize=100,
                pageToken=page_token,
            ).execute()
            for f in resp.get("files", []):
                results.append({
                    "id": f["id"],
                    "name": f["name"],
                    "path": current_path,
                    "size": f.get("size", "0"),
                    "md5Checksum": f.get("md5Checksum"),
                })
            page_token = resp.get("nextPageToken")
            if not page_token:
                break

    _scan_folder(root_folder_id, "/")
    return results


def get_file_meta(file_id: str) -> dict:
    """
    Returns MD5 checksum and size for a specific file.
    md5Checksum will be None if the file is still being uploaded to Drive.
    """
    service = _get_drive_service()
    return service.files().get(
        fileId=file_id,
        fields="id,md5Checksum,size"
    ).execute()


def generate_download_url(file_id: str) -> str:
    """
    Generates an authenticated download URL using Service Account credentials.
    Valid for ~1 hour. MUST be called immediately before POST to Vimeo.
    The URL is NEVER stored in the database.
    """
    creds = service_account.Credentials.from_service_account_file(
        settings.google_sa_key_path, scopes=SCOPES
    )
    request = google.auth.transport.requests.Request()
    creds.refresh(request)

    return (
        f"https://www.googleapis.com/drive/v3/files/{file_id}"
        f"?alt=media&access_token={creds.token}"
    )


def resolve_relative_path(file_path: str, root_folder_id: str) -> str:
    """
    The file_path is already relative since _scan_folder builds it from root.
    Returns the directory portion only (without filename).
    """
    return file_path


def get_verification_window(file_size_bytes: int) -> tuple[int, int]:
    """
    Returns (number_of_checks, interval_seconds) based on file size.
    Per spec.md §UC-03 and contracts.md §2.2.
    """
    mb = file_size_bytes / (1024 * 1024)
    if mb < 100:
        return (2, 30)
    elif mb < 500:
        return (2, 60)
    else:
        return (3, 90)
