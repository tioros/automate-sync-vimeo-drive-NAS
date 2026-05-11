"""
Vimeo API service.
Handles folder resolution, pull upload, and status polling.
See contracts.md §3 for full API contract details.
"""

import logging

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

VIMEO_BASE = "https://api.vimeo.com"
HEADERS = {
    "Authorization": f"Bearer {settings.vimeo_access_token}",
    "Content-Type": "application/json",
    "Accept": "application/vnd.vimeo.*+json;version=3.4",
}


def _get_headers() -> dict:
    """Returns fresh headers with current token."""
    return {
        "Authorization": f"Bearer {get_settings().vimeo_access_token}",
        "Content-Type": "application/json",
        "Accept": "application/vnd.vimeo.*+json;version=3.4",
    }


def resolve_folder(root_uri: str, relative_path: str) -> str:
    """
    Navigates the Vimeo folder hierarchy to find the folder matching relative_path.
    The folder structure must already exist in Vimeo (never created by the system).

    Args:
        root_uri: Vimeo root folder URI (e.g., "/folders/12345")
        relative_path: Path relative to root (e.g., "/01 - Janeiro/15/EJA/INTEGRAL/")

    Returns:
        The vimeo_folder_uri of the target folder.

    Raises:
        ValueError: If any folder in the path is not found.
    """
    parts = [p for p in relative_path.strip("/").split("/") if p]

    if not parts:
        return root_uri

    current_uri = root_uri
    headers = _get_headers()

    for part in parts:
        url = f"{VIMEO_BASE}{current_uri}/items?type=folder&per_page=100"
        found = False

        while url:
            resp = httpx.get(url, headers=headers, timeout=30)
            resp.raise_for_status()
            data = resp.json()

            for item in data.get("data", []):
                if item.get("name") == part:
                    current_uri = item["uri"]
                    found = True
                    break

            if found:
                break

            # Handle pagination
            paging = data.get("paging", {})
            next_page = paging.get("next")
            url = f"{VIMEO_BASE}{next_page}" if next_page else None

        if not found:
            raise ValueError(
                f"Pasta não encontrada no Vimeo: '{part}' em '{current_uri}'. "
                f"Caminho completo: {relative_path}. "
                f"A estrutura de pastas deve existir no Vimeo antes da sincronização."
            )

    return current_uri


def pull_upload(link: str, name: str, folder_uri: str, size: int) -> str:
    """
    Initiates a pull upload on Vimeo.
    Vimeo will download the file directly from the provided link (Google Drive).

    Args:
        link: Authenticated download URL from Google Drive
        name: Video filename
        folder_uri: Vimeo folder URI where the video should be placed
        size: File size in bytes

    Returns:
        The vimeo_uri (e.g., "/videos/123456789")
    """
    headers = _get_headers()
    payload = {
        "upload": {
            "approach": "pull",
            "link": link,
            "size": size,
        },
        "name": name,
        "folder_uri": folder_uri,
        "privacy": {
            "view": "nobody"
        },
    }

    resp = httpx.post(f"{VIMEO_BASE}/me/videos", json=payload, headers=headers, timeout=60)
    resp.raise_for_status()
    data = resp.json()

    vimeo_uri = data.get("uri")
    if not vimeo_uri:
        raise ValueError(f"Vimeo não retornou URI do vídeo. Resposta: {data}")

    logger.info(f"Pull upload iniciado: {name} → {vimeo_uri} (pasta: {folder_uri})")
    return vimeo_uri


def get_status(vimeo_uri: str) -> dict:
    """
    Polls the Vimeo API for upload/transcode status of a video.

    Returns:
        Dict with 'upload' and 'transcode' status dicts.
    """
    headers = _get_headers()
    resp = httpx.get(
        f"{VIMEO_BASE}{vimeo_uri}",
        headers=headers,
        params={"fields": "uri,upload.status,transcode.status"},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()
