"""
Pydantic schemas for authentication and user management.
"""

from pydantic import BaseModel


class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    email: str


class UserOut(BaseModel):
    email: str
    role: str

    model_config = {"from_attributes": True}
