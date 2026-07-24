"""add_client_one_page_reports

Revision ID: g6h7i8j9k0l1
Revises: f5a6b7c8d9e0
Create Date: 2026-07-24 23:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "g6h7i8j9k0l1"
down_revision: Union[str, None] = "f5a6b7c8d9e0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "client_one_page_report_run",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("data_quality_run_id", sa.String(255), nullable=False),
        sa.Column("prediction_readiness_run_id", sa.String(255), nullable=False),
        sa.Column("quantitative_study_id", sa.String(255), nullable=True),
        sa.Column("source_table_id", sa.String(255), nullable=False),
        sa.Column("source_file_id", sa.String(255), nullable=False),
        sa.Column("import_session_id", sa.String(255), nullable=False),
        sa.Column("project_id", sa.String(255), nullable=False),
        sa.Column("client_id", sa.String(255), nullable=True),
        sa.Column("run_number", sa.Integer(), nullable=False),
        sa.Column("generator_name", sa.String(100), nullable=False),
        sa.Column("generator_version", sa.String(50), nullable=False),
        sa.Column("input_fingerprint", sa.String(64), nullable=False),
        sa.Column("status", sa.String(50), nullable=False, server_default="completed"),
        sa.Column("locale", sa.String(10), nullable=False, server_default="ru"),
        sa.Column("verdict", sa.String(100), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("bundle_storage_path", sa.Text(), nullable=False),
        sa.Column("artifacts_json", sa.Text(), nullable=False),
        sa.Column("manifest_filename", sa.String(255), nullable=False),
        sa.Column("manifest_storage_path", sa.Text(), nullable=False),
        sa.Column("manifest_sha256", sa.String(64), nullable=False),
        sa.Column("manifest_size_bytes", sa.Integer(), nullable=False),
        sa.Column("slide_count", sa.Integer(), nullable=False, server_default="1"),
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
            name="uq_client_one_page_report_input_version_number",
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
        "client_id",
        "input_fingerprint",
        "status",
        "verdict",
    ):
        op.create_index(
            f"ix_client_one_page_report_run_{column}",
            "client_one_page_report_run",
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
            "client_id",
            "input_fingerprint",
            "status",
            "verdict",
        )
    ):
        op.drop_index(
            f"ix_client_one_page_report_run_{column}",
            table_name="client_one_page_report_run",
        )
    op.drop_table("client_one_page_report_run")
