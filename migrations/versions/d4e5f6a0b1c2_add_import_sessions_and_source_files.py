"""add_import_sessions_and_source_files

Revision ID: d4e5f6a0b1c2
Revises: c3d4e5f6a0b1
Create Date: 2026-07-24 14:30:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d4e5f6a0b1c2"
down_revision: Union[str, None] = "c3d4e5f6a0b1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "import_session",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("project_id", sa.String(255), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("status", sa.String(50), nullable=False, server_default="open"),
        sa.Column("created_by_user_id", sa.String(255), nullable=True),
        sa.Column("metadata_json", sa.Text(), nullable=True),
        sa.Column("file_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("total_bytes", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_import_session_project_id", "import_session", ["project_id"])
    op.create_index("ix_import_session_status", "import_session", ["status"])

    op.create_table(
        "import_source_file",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("import_session_id", sa.String(255), nullable=False),
        sa.Column("project_id", sa.String(255), nullable=False),
        sa.Column("original_filename", sa.String(512), nullable=False),
        sa.Column("extension", sa.String(32), nullable=True),
        sa.Column("declared_mime_type", sa.String(255), nullable=True),
        sa.Column("file_size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("storage_path", sa.String(512), nullable=False),
        sa.Column("uploaded_by_user_id", sa.String(255), nullable=True),
        sa.Column("metadata_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_import_source_file_import_session_id",
        "import_source_file",
        ["import_session_id"],
    )
    op.create_index(
        "ix_import_source_file_project_id",
        "import_source_file",
        ["project_id"],
    )
    op.create_index("ix_import_source_file_sha256", "import_source_file", ["sha256"])


def downgrade() -> None:
    op.drop_index("ix_import_source_file_sha256", table_name="import_source_file")
    op.drop_index("ix_import_source_file_project_id", table_name="import_source_file")
    op.drop_index(
        "ix_import_source_file_import_session_id", table_name="import_source_file"
    )
    op.drop_table("import_source_file")
    op.drop_index("ix_import_session_status", table_name="import_session")
    op.drop_index("ix_import_session_project_id", table_name="import_session")
    op.drop_table("import_session")
