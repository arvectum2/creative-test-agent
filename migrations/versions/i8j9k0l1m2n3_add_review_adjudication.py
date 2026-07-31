"""add independent review adjudication

Revision ID: i8j9k0l1m2n3
Revises: h7i8j9k0l1m2
Create Date: 2026-07-30 18:05:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "i8j9k0l1m2n3"
down_revision: Union[str, None] = "h7i8j9k0l1m2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("finding_review") as batch_op:
        batch_op.add_column(sa.Column("reviewer_subject_id", sa.String(255), nullable=True))
        batch_op.add_column(sa.Column("reviewer_subject_kind", sa.String(32), nullable=True))
        batch_op.add_column(sa.Column("reviewer_revision_number", sa.Integer(), nullable=True))

    op.execute(
        """
        UPDATE finding_review
        SET reviewer_subject_id = CASE
            WHEN reviewer_user_id IS NOT NULL AND reviewer_user_id <> '' AND reviewer_user_id <> 'system'
                THEN 'user:' || reviewer_user_id
            ELSE 'legacy:' || lower(replace(reviewer_display_name, ' ', '-'))
        END,
        reviewer_subject_kind = CASE
            WHEN reviewer_user_id IS NOT NULL AND reviewer_user_id <> '' AND reviewer_user_id <> 'system'
                THEN 'authenticated_user'
            ELSE 'legacy'
        END,
        reviewer_revision_number = revision_number
        """
    )

    with op.batch_alter_table("finding_review") as batch_op:
        batch_op.alter_column("reviewer_subject_id", existing_type=sa.String(255), nullable=False)
        batch_op.alter_column("reviewer_subject_kind", existing_type=sa.String(32), nullable=False)
        batch_op.alter_column("reviewer_revision_number", existing_type=sa.Integer(), nullable=False)
        batch_op.create_unique_constraint(
            "uq_finding_review_project_finding_reviewer_revision",
            ["project_id", "finding_id", "reviewer_subject_id", "reviewer_revision_number"],
        )
        batch_op.create_index("ix_finding_review_reviewer_subject_id", ["reviewer_subject_id"])

    op.create_table(
        "finding_adjudication",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("project_id", sa.String(255), nullable=False),
        sa.Column("campaign_id", sa.String(255), nullable=True),
        sa.Column("case_id", sa.String(255), nullable=True),
        sa.Column("creative_record_id", sa.String(255), nullable=True),
        sa.Column("creative_asset_id", sa.String(255), nullable=True),
        sa.Column("test_run_id", sa.String(255), nullable=True),
        sa.Column("finding_id", sa.String(255), nullable=False),
        sa.Column("source_kind", sa.String(32), nullable=False),
        sa.Column("policy_id", sa.String(120), nullable=False),
        sa.Column("basis_review_ids_json", sa.Text(), nullable=False),
        sa.Column("basis_fingerprint_sha256", sa.String(64), nullable=False),
        sa.Column("adjudicator_user_id", sa.String(255), nullable=True),
        sa.Column("adjudicator_subject_id", sa.String(255), nullable=False),
        sa.Column("adjudicator_subject_kind", sa.String(32), nullable=False),
        sa.Column("adjudicator_display_name", sa.String(255), nullable=False),
        sa.Column("adjudicator_role", sa.String(160), nullable=False),
        sa.Column("decision", sa.String(64), nullable=False),
        sa.Column("correctness", sa.Integer(), nullable=False),
        sa.Column("relevance", sa.Integer(), nullable=False),
        sa.Column("actionability", sa.Integer(), nullable=False),
        sa.Column("traceability", sa.Integer(), nullable=False),
        sa.Column("severity_correctness", sa.String(32), nullable=False),
        sa.Column("adjudicator_confidence", sa.Float(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("adjudication_round", sa.Integer(), nullable=False),
        sa.Column("supersedes_adjudication_id", sa.String(255), nullable=True),
        sa.Column("created_by_user_id", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "project_id",
            "finding_id",
            "adjudication_round",
            name="uq_finding_adjudication_project_finding_round",
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
        "basis_fingerprint_sha256",
        "adjudicator_user_id",
        "adjudicator_subject_id",
        "decision",
        "supersedes_adjudication_id",
    ):
        op.create_index(f"ix_finding_adjudication_{column}", "finding_adjudication", [column])


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
            "basis_fingerprint_sha256",
            "adjudicator_user_id",
            "adjudicator_subject_id",
            "decision",
            "supersedes_adjudication_id",
        )
    ):
        op.drop_index(f"ix_finding_adjudication_{column}", table_name="finding_adjudication")
    op.drop_table("finding_adjudication")

    with op.batch_alter_table("finding_review") as batch_op:
        batch_op.drop_index("ix_finding_review_reviewer_subject_id")
        batch_op.drop_constraint(
            "uq_finding_review_project_finding_reviewer_revision",
            type_="unique",
        )
        batch_op.drop_column("reviewer_revision_number")
        batch_op.drop_column("reviewer_subject_kind")
        batch_op.drop_column("reviewer_subject_id")
