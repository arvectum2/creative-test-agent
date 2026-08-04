"""add controlled pilot intake case register

Revision ID: k0l1m2n3o4p5
Revises: j9k0l1m2n3o4
Create Date: 2026-08-04 12:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "k0l1m2n3o4p5"
down_revision: Union[str, None] = "j9k0l1m2n3o4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "pilot_case",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("project_id", sa.String(255), nullable=False),
        sa.Column("case_key", sa.String(255), nullable=False),
        sa.Column("import_session_id", sa.String(255), nullable=False),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column("source_package_sha256", sa.String(64), nullable=False),
        sa.Column("source_files_json", sa.Text(), nullable=False),
        sa.Column("provenance_json", sa.Text(), nullable=False),
        sa.Column("source_linkage_confidence", sa.String(32), nullable=False),
        sa.Column("linkage_confidence", sa.String(32), nullable=False),
        sa.Column("asset_references_json", sa.Text(), nullable=False),
        sa.Column("asset_count", sa.Integer(), nullable=False),
        sa.Column("reported_impressions", sa.BigInteger(), nullable=True),
        sa.Column("reported_clicks", sa.BigInteger(), nullable=True),
        sa.Column("reported_rate", sa.Float(), nullable=True),
        sa.Column("data_quality_snapshot_json", sa.Text(), nullable=False),
        sa.Column("data_quality_run_count", sa.Integer(), nullable=False),
        sa.Column("overall_data_quality_status", sa.String(32), nullable=False),
        sa.Column("warning_issue_count", sa.Integer(), nullable=False),
        sa.Column("blocking_issue_count", sa.Integer(), nullable=False),
        sa.Column("created_by_user_id", sa.String(255), nullable=True),
        sa.Column("updated_by_user_id", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "case_key", name="uq_pilot_case_project_key"),
    )
    for column in (
        "project_id",
        "case_key",
        "import_session_id",
        "state",
        "source_package_sha256",
        "linkage_confidence",
        "overall_data_quality_status",
    ):
        op.create_index(f"ix_pilot_case_{column}", "pilot_case", [column])

    op.create_table(
        "pilot_case_decision",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("project_id", sa.String(255), nullable=False),
        sa.Column("pilot_case_id", sa.String(255), nullable=False),
        sa.Column("case_key", sa.String(255), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("from_state", sa.String(32), nullable=True),
        sa.Column("to_state", sa.String(32), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("decided_by_user_id", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "pilot_case_id",
            "sequence",
            name="uq_pilot_case_decision_case_sequence",
        ),
    )
    for column in ("project_id", "pilot_case_id", "case_key", "to_state"):
        op.create_index(
            f"ix_pilot_case_decision_{column}",
            "pilot_case_decision",
            [column],
        )


def downgrade() -> None:
    for column in reversed(("project_id", "pilot_case_id", "case_key", "to_state")):
        op.drop_index(
            f"ix_pilot_case_decision_{column}",
            table_name="pilot_case_decision",
        )
    op.drop_table("pilot_case_decision")

    for column in reversed(
        (
            "project_id",
            "case_key",
            "import_session_id",
            "state",
            "source_package_sha256",
            "linkage_confidence",
            "overall_data_quality_status",
        )
    ):
        op.drop_index(f"ix_pilot_case_{column}", table_name="pilot_case")
    op.drop_table("pilot_case")
