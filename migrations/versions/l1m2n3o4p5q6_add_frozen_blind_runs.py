"""add frozen blind diagnostic revisions

Revision ID: l1m2n3o4p5q6
Revises: k0l1m2n3o4p5
Create Date: 2026-08-04 21:15:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "l1m2n3o4p5q6"
down_revision: Union[str, None] = "k0l1m2n3o4p5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "blind_diagnostic_revision",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("project_id", sa.String(255), nullable=False),
        sa.Column("pilot_case_id", sa.String(255), nullable=False),
        sa.Column("case_key", sa.String(255), nullable=False),
        sa.Column("revision_number", sa.Integer(), nullable=False),
        sa.Column("execution_id", sa.String(255), nullable=False),
        sa.Column("supersedes_revision_id", sa.String(255), nullable=True),
        sa.Column("previous_revision_sha256", sa.String(64), nullable=True),
        sa.Column("diagnostic_output_json", sa.Text(), nullable=False),
        sa.Column("diagnostic_output_sha256", sa.String(64), nullable=False),
        sa.Column("input_provenance_json", sa.Text(), nullable=False),
        sa.Column("input_provenance_sha256", sa.String(64), nullable=False),
        sa.Column("prompt_manifest_json", sa.Text(), nullable=False),
        sa.Column("prompt_manifest_sha256", sa.String(64), nullable=False),
        sa.Column("model_profile_json", sa.Text(), nullable=False),
        sa.Column("model_profile_sha256", sa.String(64), nullable=False),
        sa.Column("code_revision", sa.String(64), nullable=False),
        sa.Column("execution_metadata_json", sa.Text(), nullable=False),
        sa.Column("execution_metadata_sha256", sa.String(64), nullable=False),
        sa.Column("revision_manifest_json", sa.Text(), nullable=False),
        sa.Column("revision_sha256", sa.String(64), nullable=False),
        sa.Column("created_by_user_id", sa.String(255), nullable=True),
        sa.Column("frozen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "project_id",
            "pilot_case_id",
            "revision_number",
            name="uq_blind_diag_project_case_revision",
        ),
        sa.UniqueConstraint(
            "project_id",
            "pilot_case_id",
            "execution_id",
            name="uq_blind_diag_project_case_execution",
        ),
    )
    for column in (
        "project_id",
        "pilot_case_id",
        "case_key",
        "execution_id",
        "supersedes_revision_id",
        "previous_revision_sha256",
        "diagnostic_output_sha256",
        "input_provenance_sha256",
        "prompt_manifest_sha256",
        "model_profile_sha256",
        "code_revision",
        "execution_metadata_sha256",
        "revision_sha256",
    ):
        op.create_index(
            f"ix_blind_diagnostic_revision_{column}",
            "blind_diagnostic_revision",
            [column],
        )

    op.create_table(
        "blind_outcome_envelope",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("project_id", sa.String(255), nullable=False),
        sa.Column("pilot_case_id", sa.String(255), nullable=False),
        sa.Column("case_key", sa.String(255), nullable=False),
        sa.Column("outcome_schema_version", sa.String(120), nullable=False),
        sa.Column("outcome_payload_json", sa.Text(), nullable=False),
        sa.Column("outcome_payload_sha256", sa.String(64), nullable=False),
        sa.Column("provenance_json", sa.Text(), nullable=False),
        sa.Column("provenance_sha256", sa.String(64), nullable=False),
        sa.Column("created_by_user_id", sa.String(255), nullable=True),
        sa.Column("sealed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "project_id",
            "pilot_case_id",
            name="uq_blind_outcome_project_case",
        ),
    )
    for column in (
        "project_id",
        "pilot_case_id",
        "case_key",
        "outcome_payload_sha256",
        "provenance_sha256",
    ):
        op.create_index(
            f"ix_blind_outcome_envelope_{column}",
            "blind_outcome_envelope",
            [column],
        )


def downgrade() -> None:
    for column in reversed(
        (
            "project_id",
            "pilot_case_id",
            "case_key",
            "outcome_payload_sha256",
            "provenance_sha256",
        )
    ):
        op.drop_index(
            f"ix_blind_outcome_envelope_{column}",
            table_name="blind_outcome_envelope",
        )
    op.drop_table("blind_outcome_envelope")

    for column in reversed(
        (
            "project_id",
            "pilot_case_id",
            "case_key",
            "execution_id",
            "supersedes_revision_id",
            "previous_revision_sha256",
            "diagnostic_output_sha256",
            "input_provenance_sha256",
            "prompt_manifest_sha256",
            "model_profile_sha256",
            "code_revision",
            "execution_metadata_sha256",
            "revision_sha256",
        )
    ):
        op.drop_index(
            f"ix_blind_diagnostic_revision_{column}",
            table_name="blind_diagnostic_revision",
        )
    op.drop_table("blind_diagnostic_revision")
