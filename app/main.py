"""
Drive → Vimeo Sync: FastAPI Application Entry Point.
Mounts all routers, configures Jinja2 templates, and startup events.
"""

import logging

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.routers import auth, videos, config, admin, reports, pages

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)-25s | %(levelname)-7s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

app = FastAPI(
    title="Drive → Vimeo Sync",
    description="Sistema de sincronização automática de vídeos do Google Drive para o Vimeo",
    version="1.0.0",
)

# ─── API Routers ──────────────────────────────────────────────────────────────
app.include_router(auth.router)
app.include_router(videos.router)
app.include_router(config.router)
app.include_router(admin.router)
app.include_router(reports.router)

# ─── Page (Template) Router ──────────────────────────────────────────────────
app.include_router(pages.router)


@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "drive-vimeo-sync"}
