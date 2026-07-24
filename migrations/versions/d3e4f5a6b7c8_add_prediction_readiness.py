"""add_prediction_readiness

Revision ID: d3e4f5a6b7c8
Revises: c2d3e4f5a6b7
Create Date: 2026-07-24 18:30:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "d3e4f5a6b7c8"
down_revision: Union[str, None] = "c2d3e4f5a6b7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "prediction_readiness_run",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("data_quality_run_id", sa.String(255), nullable=False),
        sa.Column("source_table_id", sa.String(255), nullable=False),
        sa.Column("source_file_id", sa.String(255), nullable=False),
        sa.Column("import_session_id", sa.String(255), nullable=False),
        sa.Column("project_id", sa.String(255), nullable=False),
        sa.Column("run_number", sa.Integer(), nullable=False),
        sa.Column("evaluator_name", sa.String(100), nullable=False),
        sa.Column("evaluator_version", sa.String(50), nullable=False),
        sa.Column("input_fingerprint", sa.String(64), nullable=False),
        sa.Column("status", sa.String(50), nullable=False, server_default="completed"),
        sa.Column("overall_status", sa.String(50), nullable=False, server_default="unavailable"),
        sa.Column("capability_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("ready_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("degraded_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("unavailable_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("not_applicable_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("unresolved_client_question_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("unresolved_analyst_question_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("summary_json", sa.Text(), nullable=True),
        sa.Column("error_code", sa.String(100), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "data_quality_run_id",
            "evaluator_version",
            "input_fingerprint",
            "run_number",
            name="uq_prediction_readiness_run_input_version_number",
        ),
    )
    for column in (
        "data_quality_run_id", "source_table_id", "source_file_id", "import_session_id",
        "project_id", "input_fingerprint", "status", "overall_status",
    ):
        op.create_index(f"ix_prediction_readiness_run_{column}", "prediction_readiness_run", [column])

    op.create_table(
        "prediction_capability_readiness",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("prediction_readiness_run_id", sa.String(255), nullable=False),
        sa.Column("capability_key", sa.String(100), nullable=False),
        sa.Column("status", sa.String(50), nullable=False),
        sa.Column("mode", sa.String(100), nullable=False),
        sa.Column("evidence_strength", sa.String(50), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("user_message", sa.Text(), nullable=False),
        sa.Column("internal_message", sa.Text(), nullable=False),
        sa.Column("reasons_json", sa.Text(), nullable=True),
        sa.Column("required_inputs_json", sa.Text(), nullable=True),
        sa.Column("missing_inputs_json", sa.Text(), nullable=True),
        sa.Column("degraded_inputs_json", sa.Text(), nullable=True),
        sa.Column("allowed_operations_json", sa.Text(), nullable=True),
        sa.Column("prohibited_operations_json", sa.Text(), nullable=True),
        sa.Column("evidence_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "prediction_readiness_run_id", "capability_key",
            name="uq_prediction_capability_run_key",
        ),
    )
    for column in ("prediction_readiness_run_id", "capability_key", "status"):
        op.create_index(
            f"ix_prediction_capability_readiness_{column}",
            "prediction_capability_readiness",
            [column],
        )


def downgrade() -> None:
    for column in reversed(("prediction_readiness_run_id", "capability_key", "status")):
        op.drop_index(
            f"ix_prediction_capability_readiness_{column}",
            table_name="prediction_capability_readiness",
        )
    op.drop_table("prediction_capability_readiness")
    for column in reversed((
        "data_quality_run_id", "source_table_id", "source_file_id", "import_session_id",
        "project_id", "input_fingerprint", "status", "overall_status",
    )):
        op.drop_index(f"ix_prediction_readiness_run_{column}", table_name="prediction_readiness_run")
    op.drop_table("prediction_readiness_run")
