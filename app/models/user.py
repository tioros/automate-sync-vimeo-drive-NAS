"""
ORM model for the users table with RBAC roles.
"""

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, String, DateTime, Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID

from app.database import Base


class UserRole(str, enum.Enum):
    admin = "admin"
    auditor = "auditor"


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(256), nullable=False, unique=True)
    password_hash = Column(String(256), nullable=False)
    role = Column(SAEnum(UserRole, name="user_role", create_constraint=True), nullable=False, default=UserRole.auditor)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
