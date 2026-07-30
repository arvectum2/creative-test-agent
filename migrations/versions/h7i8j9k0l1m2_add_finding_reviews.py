"""add_finding_reviews

Revision ID: h7i8j9k0l1m2
Revises: g6h7i8j9k0l1
Create Date: 2026-07-30 16:40:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "h7i8j9k0l1m2"
down_revision: Union[str, None] = "g6h7i8j9k0l1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "finding_review",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("project_id", sa.String(255), nullable=False),
        sa.Column("campaign_id", sa.String(255), nullable=True),
        sa.Column("case_id", sa.String(255), nullable=True),
        sa.Column("creative_record_id", sa.String(255), nullable=True),
        sa.Column("creative_asset_id", sa.String(255), nullable=True),
        sa.Column("test_run_id", sa.String(255), nullable=True),
        sa.Column("finding_id", sa.String(255), nullable=False),
        sa.Column("source_kind", sa.String(32), nullable=False),
        sa.Column("system_finding_snapshot_json", sa.Text(), nullable=True),
        sa.Column("system_finding_snapshot_sha256", sa.String(64), nullable=True),
        sa.Column("human_finding_snapshot_json", sa.Text(), nullable=True),
        sa.Column("human_finding_snapshot_sha256", sa.String(64), nullable=True),
        sa.Column("reviewer_user_id", sa.String(255), nullable=True),
        sa.Column("reviewer_display_name", sa.String(255), nullable=False),
        sa.Column("reviewer_role", sa.String(160), nullable=False),
        sa.Column("decision", sa.String(64), nullable=False),
        sa.Column("correctness", sa.Integer(), nullable=False),
        sa.Column("relevance", sa.Integer(), nullable=False),
        sa.Column("actionability", sa.Integer(), nullable=False),
        sa.Column("traceability", sa.Integer(), nullable=False),
        sa.Column("severity_correctness", sa.String(32), nullable=False),
        sa.Column("reviewer_confidence", sa.Float(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("revision_number", sa.Integer(), nullable=False),
        sa.Column("supersedes_review_id", sa.String(255), nullable=True),
        sa.Column("created_by_user_id", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "project_id",
            "finding_id",
            "revision_number",
            name="uq_finding_review_project_finding_revision",
        ),
    )
    for column in (
        "project_id",
        "campaign_id",
        "case_id",
        "creative_record_id",
        "creative_asset_id",
        "test_run_id",
        "finding_id",
        "source_kind",
        "system_finding_snapshot_sha256",
        "human_finding_snapshot_sha256",
        "reviewer_user_id",
        "decision",
        "supersedes_review_id",
    ):
        op.create_index(f"ix_finding_review_{column}", "finding_review", [column])


def downgrade() -> None:
    for column in reversed(
        (
            "project_id",
            "campaign_id",
            "case_id",
            "creative_record_id",
            "creative_asset_id",
            "test_run_id",
            "finding_id",
            "source_kind",
            "system_finding_snapshot_sha256",
            "human_finding_snapshot_sha256",
            "reviewer_user_id",
            "decision",
            "supersedes_review_id",
        )
    ):
        op.drop_index(f"ix_finding_review_{column}", table_name="finding_review")
    op.drop_table("finding_review")
