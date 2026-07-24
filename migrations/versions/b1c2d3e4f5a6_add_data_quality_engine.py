"""add_data_quality_engine

Revision ID: b1c2d3e4f5a6
Revises: a0b1c2d3e4f5
Create Date: 2026-07-24 17:05:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b1c2d3e4f5a6"
down_revision: Union[str, None] = "a0b1c2d3e4f5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "data_quality_run",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("source_table_id", sa.String(255), nullable=False),
        sa.Column("source_file_id", sa.String(255), nullable=False),
        sa.Column("import_session_id", sa.String(255), nullable=False),
        sa.Column("project_id", sa.String(255), nullable=False),
        sa.Column("normalization_run_id", sa.String(255), nullable=True),
        sa.Column("run_number", sa.Integer(), nullable=False),
        sa.Column("engine_name", sa.String(100), nullable=False),
        sa.Column("engine_version", sa.String(50), nullable=False),
        sa.Column("input_fingerprint", sa.String(64), nullable=False),
        sa.Column("status", sa.String(50), nullable=False, server_default="completed"),
        sa.Column("overall_status", sa.String(50), nullable=False, server_default="passed"),
        sa.Column("source_file_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("source_table_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("source_row_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("source_column_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("confirmed_mapping_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("suggested_mapping_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("rejected_mapping_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("unmapped_mapping_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("normalized_row_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("partial_row_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("skipped_row_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("failed_row_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("creative_record_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("linked_creative_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("unlinked_creative_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("ambiguous_creative_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("performance_observation_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("info_issue_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("warning_issue_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("blocking_issue_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("total_issue_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("category_counts_json", sa.Text(), nullable=True),
        sa.Column("summary_json", sa.Text(), nullable=True),
        sa.Column("error_code", sa.String(100), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "source_table_id",
            "engine_version",
            "input_fingerprint",
            "run_number",
            name="uq_data_quality_run_table_version_fingerprint_number",
        ),
    )
    for column in (
        "source_table_id",
        "source_file_id",
        "import_session_id",
        "project_id",
        "normalization_run_id",
        "input_fingerprint",
        "status",
        "overall_status",
    ):
        op.create_index(f"ix_data_quality_run_{column}", "data_quality_run", [column])

    op.create_table(
        "data_quality_issue",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("data_quality_run_id", sa.String(255), nullable=False),
        sa.Column("category", sa.String(50), nullable=False),
        sa.Column("code", sa.String(100), nullable=False),
        sa.Column("severity", sa.String(50), nullable=False),
        sa.Column("scope_type", sa.String(50), nullable=False, server_default="run"),
        sa.Column("scope_id", sa.String(255), nullable=True),
        sa.Column("source_file_id", sa.String(255), nullable=True),
        sa.Column("source_table_id", sa.String(255), nullable=True),
        sa.Column("source_row_id", sa.String(255), nullable=True),
        sa.Column("source_column_id", sa.String(255), nullable=True),
        sa.Column("affected_count", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("remediation_hint", sa.Text(), nullable=True),
        sa.Column("details_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in (
        "data_quality_run_id",
        "category",
        "code",
        "severity",
        "scope_type",
        "scope_id",
        "source_file_id",
        "source_table_id",
        "source_row_id",
        "source_column_id",
    ):
        op.create_index(f"ix_data_quality_issue_{column}", "data_quality_issue", [column])


def downgrade() -> None:
    for column in reversed(
        (
            "data_quality_run_id",
            "category",
            "code",
            "severity",
            "scope_type",
            "scope_id",
            "source_file_id",
            "source_table_id",
            "source_row_id",
            "source_column_id",
        )
    ):
        op.drop_index(f"ix_data_quality_issue_{column}", table_name="data_quality_issue")
    op.drop_table("data_quality_issue")

    for column in reversed(
        (
            "source_table_id",
            "source_file_id",
            "import_session_id",
            "project_id",
            "normalization_run_id",
            "input_fingerprint",
            "status",
            "overall_status",
        )
    ):
        op.drop_index(f"ix_data_quality_run_{column}", table_name="data_quality_run")
    op.drop_table("data_quality_run")
