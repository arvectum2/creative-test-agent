"""add_tabular_source_inspection

Revision ID: e5f6a0b1c2d3
Revises: d4e5f6a0b1c2
Create Date: 2026-07-24 15:20:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e5f6a0b1c2d3"
down_revision: Union[str, None] = "d4e5f6a0b1c2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "source_inspection",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("source_file_id", sa.String(255), nullable=False),
        sa.Column("import_session_id", sa.String(255), nullable=False),
        sa.Column("project_id", sa.String(255), nullable=False),
        sa.Column("inspection_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(50), nullable=False, server_default="running"),
        sa.Column("parser_name", sa.String(100), nullable=False),
        sa.Column("parser_version", sa.String(50), nullable=False),
        sa.Column("file_format", sa.String(32), nullable=True),
        sa.Column("encoding", sa.String(50), nullable=True),
        sa.Column("delimiter", sa.String(10), nullable=True),
        sa.Column("table_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("row_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("column_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("warnings_json", sa.Text(), nullable=True),
        sa.Column("error_code", sa.String(100), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_source_inspection_source_file_id", "source_inspection", ["source_file_id"])
    op.create_index(
        "ix_source_inspection_import_session_id",
        "source_inspection",
        ["import_session_id"],
    )
    op.create_index("ix_source_inspection_project_id", "source_inspection", ["project_id"])
    op.create_index("ix_source_inspection_status", "source_inspection", ["status"])

    op.create_table(
        "source_table",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("inspection_id", sa.String(255), nullable=False),
        sa.Column("source_file_id", sa.String(255), nullable=False),
        sa.Column("sheet_index", sa.Integer(), nullable=False),
        sa.Column("sheet_name", sa.String(255), nullable=False),
        sa.Column("header_row_number", sa.Integer(), nullable=True),
        sa.Column("header_confidence", sa.Float(), nullable=True),
        sa.Column("source_row_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("data_row_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("column_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("truncated", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("warnings_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_source_table_inspection_id", "source_table", ["inspection_id"])
    op.create_index("ix_source_table_source_file_id", "source_table", ["source_file_id"])

    op.create_table(
        "source_column",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("source_table_id", sa.String(255), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("source_header", sa.Text(), nullable=True),
        sa.Column("normalized_header", sa.String(255), nullable=False),
        sa.Column("inferred_type", sa.String(50), nullable=False),
        sa.Column("is_empty", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("duplicate_index", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("duplicate_group", sa.String(255), nullable=True),
        sa.Column("non_empty_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("sample_values_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_source_column_source_table_id", "source_column", ["source_table_id"])

    op.create_table(
        "source_row",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("source_table_id", sa.String(255), nullable=False),
        sa.Column("source_row_number", sa.Integer(), nullable=False),
        sa.Column("row_kind", sa.String(50), nullable=False),
        sa.Column("values_json", sa.Text(), nullable=False),
        sa.Column("cell_types_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_source_row_source_table_id", "source_row", ["source_table_id"])


def downgrade() -> None:
    op.drop_index("ix_source_row_source_table_id", table_name="source_row")
    op.drop_table("source_row")
    op.drop_index("ix_source_column_source_table_id", table_name="source_column")
    op.drop_table("source_column")
    op.drop_index("ix_source_table_source_file_id", table_name="source_table")
    op.drop_index("ix_source_table_inspection_id", table_name="source_table")
    op.drop_table("source_table")
    op.drop_index("ix_source_inspection_status", table_name="source_inspection")
    op.drop_index("ix_source_inspection_project_id", table_name="source_inspection")
    op.drop_index("ix_source_inspection_import_session_id", table_name="source_inspection")
    op.drop_index("ix_source_inspection_source_file_id", table_name="source_inspection")
    op.drop_table("source_inspection")
