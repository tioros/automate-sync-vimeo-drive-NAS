"""Initial schema: videos, status_logs, system_config, users

Revision ID: 001_initial
Revises: None
Create Date: 2026-05-11
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers
revision: str = "001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create enums
    video_status_enum = sa.Enum(
        "DISCOVERED", "DRIVE_SYNC_PENDING", "DRIVE_READY",
        "VIMEO_UPLOADING", "VIMEO_TRANSCODING", "SUCCESS", "ERROR",
        name="video_status",
    )
    user_role_enum = sa.Enum("admin", "auditor", name="user_role")

    # system_config table
    op.create_table(
        "system_config",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("drive_root_folder_id", sa.String(256), nullable=False),
        sa.Column("vimeo_root_folder_uri", sa.String(256), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    # users table
    op.create_table(
        "users",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("email", sa.String(256), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(256), nullable=False),
        sa.Column("role", user_role_enum, nullable=False, server_default="auditor"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    # videos table
    op.create_table(
        "videos",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("filename", sa.String(512), nullable=False),
        sa.Column("relative_path", sa.String(1024), nullable=False),
        sa.Column("drive_file_id", sa.String(256), nullable=False, unique=True),
        sa.Column("vimeo_uri", sa.String(256), nullable=True),
        sa.Column("vimeo_folder_uri", sa.String(256), nullable=True),
        sa.Column("status", video_status_enum, nullable=False, server_default="DISCOVERED"),
        sa.Column("checksum", sa.String(64), nullable=True),
        sa.Column("file_size", sa.BigInteger, nullable=True),
        sa.Column("retry_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_videos_status", "videos", ["status"])
    op.create_index("idx_videos_relative_path", "videos", ["relative_path"])
    op.create_index("idx_videos_drive_file_id", "videos", ["drive_file_id"])

    # status_logs table
    op.create_table(
        "status_logs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("video_id", UUID(as_uuid=True), sa.ForeignKey("videos.id"), nullable=False),
        sa.Column("from_status", video_status_enum, nullable=True),
        sa.Column("to_status", video_status_enum, nullable=False),
        sa.Column("message", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_status_logs_video_id", "status_logs", ["video_id"])


def downgrade() -> None:
    op.drop_table("status_logs")
    op.drop_table("videos")
    op.drop_table("users")
    op.drop_table("system_config")
    op.execute("DROP TYPE IF EXISTS video_status")
    op.execute("DROP TYPE IF EXISTS user_role")
