"""
Pages router: serves Jinja2 templates for the dashboard.
Handles authentication via cookies for SSR pages.
"""

from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.auth import get_current_user, RequireRole
from app.models.user import User

router = APIRouter(tags=["pages"])
templates = Jinja2Templates(directory="app/templates")


def _get_optional_user(request: Request):
    """Try to get user from cookie, return None if not authenticated."""
    from jose import JWTError, jwt
    from app.config import get_settings
    settings = get_settings()

    token = request.cookies.get("access_token")
    if not token:
        return None

    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        return {"email": payload.get("sub"), "role": payload.get("role")}
    except JWTError:
        return None


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    user = _get_optional_user(request)
    if user:
        return RedirectResponse(url="/", status_code=302)
    return templates.TemplateResponse("login.html", {"request": request})


@router.get("/logout")
async def logout():
    response = RedirectResponse(url="/login", status_code=302)
    response.delete_cookie("access_token")
    return response


@router.get("/", response_class=HTMLResponse)
async def dashboard_page(request: Request):
    user = _get_optional_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    return templates.TemplateResponse("dashboard.html", {"request": request, "user": user})


@router.get("/videos", response_class=HTMLResponse)
async def videos_page(request: Request):
    user = _get_optional_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    return templates.TemplateResponse("videos.html", {"request": request, "user": user})


@router.get("/videos/{video_id}", response_class=HTMLResponse)
async def video_detail_page(request: Request, video_id: str):
    user = _get_optional_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    return templates.TemplateResponse("video_detail.html", {"request": request, "user": user, "video_id": video_id})


@router.get("/config", response_class=HTMLResponse)
async def config_page(request: Request):
    user = _get_optional_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Acesso negado")
    return templates.TemplateResponse("config.html", {"request": request, "user": user})


@router.get("/reports", response_class=HTMLResponse)
async def reports_page(request: Request):
    user = _get_optional_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    return templates.TemplateResponse("reports.html", {"request": request, "user": user})
