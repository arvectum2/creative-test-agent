"""add calibration quality dashboard evidence

Revision ID: j9k0l1m2n3o4
Revises: i8j9k0l1m2n3
Create Date: 2026-07-31 12:15:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "j9k0l1m2n3o4"
down_revision: Union[str, None] = "i8j9k0l1m2n3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "calibration_case_evidence",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("project_id", sa.String(255), nullable=False),
        sa.Column("case_id", sa.String(255), nullable=False),
        sa.Column("evidence_class", sa.String(32), nullable=False),
        sa.Column("inclusion_status", sa.String(32), nullable=False),
        sa.Column("source_reference", sa.String(500), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("updated_by_user_id", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "project_id",
            "case_id",
            name="uq_calibration_case_project_case",
        ),
    )
    for column in ("project_id", "case_id", "evidence_class", "inclusion_status"):
        op.create_index(
            f"ix_calibration_case_evidence_{column}",
            "calibration_case_evidence",
            [column],
        )

    op.create_table(
        "calibration_workflow_measurement",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("project_id", sa.String(255), nullable=False),
        sa.Column("case_id", sa.String(255), nullable=False),
        sa.Column("stage", sa.String(120), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("wall_clock_seconds", sa.Float(), nullable=False),
        sa.Column("operator_touch_seconds", sa.Float(), nullable=False),
        sa.Column("manual_action_count", sa.Integer(), nullable=False),
        sa.Column("report_version", sa.String(120), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("project_id", "case_id", "stage", "status"):
        op.create_index(
            f"ix_calibration_workflow_measurement_{column}",
            "calibration_workflow_measurement",
            [column],
        )


def downgrade() -> None:
    for column in reversed(("project_id", "case_id", "stage", "status")):
        op.drop_index(
            f"ix_calibration_workflow_measurement_{column}",
            table_name="calibration_workflow_measurement",
        )
    op.drop_table("calibration_workflow_measurement")

    for column in reversed(("project_id", "case_id", "evidence_class", "inclusion_status")):
        op.drop_index(
            f"ix_calibration_case_evidence_{column}",
            table_name="calibration_case_evidence",
        )
    op.drop_table("calibration_case_evidence")
