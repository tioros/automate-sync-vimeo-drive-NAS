"""
Authentication router: login endpoint.
"""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.auth import verify_password, create_access_token
from app.schemas.user import LoginRequest, TokenResponse

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest, db: AsyncSession = Depends(get_db)):
    """Authenticates user and returns JWT token."""
    result = await db.execute(select(User).where(User.email == payload.email))
    user = result.scalar_one_or_none()

    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="E-mail ou senha incorretos")

    token = create_access_token(data={"sub": user.email, "role": user.role.value})

    response = JSONResponse(content={
        "access_token": token,
        "token_type": "bearer",
        "role": user.role.value,
        "email": user.email,
    })
    # Set cookie for Jinja2 template pages
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        max_age=60 * 480,
        samesite="lax",
    )
    return response
