"""add_data_review_reports

Revision ID: f5a6b7c8d9e0
Revises: e4f5a6b7c8d9
Create Date: 2026-07-24 19:30:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "f5a6b7c8d9e0"
down_revision: Union[str, None] = "e4f5a6b7c8d9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "data_review_report_run",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("data_quality_run_id", sa.String(255), nullable=False),
        sa.Column("prediction_readiness_run_id", sa.String(255), nullable=True),
        sa.Column("quantitative_study_id", sa.String(255), nullable=True),
        sa.Column("source_table_id", sa.String(255), nullable=False),
        sa.Column("source_file_id", sa.String(255), nullable=False),
        sa.Column("import_session_id", sa.String(255), nullable=False),
        sa.Column("project_id", sa.String(255), nullable=False),
        sa.Column("run_number", sa.Integer(), nullable=False),
        sa.Column("generator_name", sa.String(100), nullable=False),
        sa.Column("generator_version", sa.String(50), nullable=False),
        sa.Column("input_fingerprint", sa.String(64), nullable=False),
        sa.Column("status", sa.String(50), nullable=False, server_default="completed"),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("storage_path", sa.Text(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("file_size_bytes", sa.Integer(), nullable=False),
        sa.Column("sheet_count", sa.Integer(), nullable=False),
        sa.Column("summary_json", sa.Text(), nullable=True),
        sa.Column("error_code", sa.String(100), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "data_quality_run_id",
            "generator_version",
            "input_fingerprint",
            "run_number",
            name="uq_data_review_report_input_version_number",
        ),
    )
    for column in (
        "data_quality_run_id",
        "prediction_readiness_run_id",
        "quantitative_study_id",
        "source_table_id",
        "source_file_id",
        "import_session_id",
        "project_id",
        "input_fingerprint",
        "status",
    ):
        op.create_index(
            f"ix_data_review_report_run_{column}",
            "data_review_report_run",
            [column],
        )


def downgrade() -> None:
    for column in reversed(
        (
            "data_quality_run_id",
            "prediction_readiness_run_id",
            "quantitative_study_id",
            "source_table_id",
            "source_file_id",
            "import_session_id",
            "project_id",
            "input_fingerprint",
            "status",
        )
    ):
        op.drop_index(
            f"ix_data_review_report_run_{column}",
            table_name="data_review_report_run",
        )
    op.drop_table("data_review_report_run")
