"""add_progressive_clarifications

Revision ID: c2d3e4f5a6b7
Revises: b1c2d3e4f5a6
Create Date: 2026-07-24 17:45:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c2d3e4f5a6b7"
down_revision: Union[str, None] = "b1c2d3e4f5a6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "clarification_run",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("data_quality_run_id", sa.String(255), nullable=False),
        sa.Column("source_table_id", sa.String(255), nullable=False),
        sa.Column("source_file_id", sa.String(255), nullable=False),
        sa.Column("import_session_id", sa.String(255), nullable=False),
        sa.Column("project_id", sa.String(255), nullable=False),
        sa.Column("run_number", sa.Integer(), nullable=False),
        sa.Column("generator_name", sa.String(100), nullable=False),
        sa.Column("generator_version", sa.String(50), nullable=False),
        sa.Column("input_fingerprint", sa.String(64), nullable=False),
        sa.Column("audience", sa.String(50), nullable=False),
        sa.Column("max_questions", sa.Integer(), nullable=False, server_default=sa.text("5")),
        sa.Column("status", sa.String(50), nullable=False, server_default="open"),
        sa.Column("candidate_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("question_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("suppressed_question_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("open_question_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("answered_question_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("deferred_question_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("not_available_question_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("not_applicable_question_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("summary_json", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "source_table_id",
            "generator_version",
            "input_fingerprint",
            "run_number",
            name="uq_clarification_run_table_version_fingerprint_number",
        ),
    )
    for column in (
        "data_quality_run_id",
        "source_table_id",
        "source_file_id",
        "import_session_id",
        "project_id",
        "input_fingerprint",
        "audience",
        "status",
    ):
        op.create_index(f"ix_clarification_run_{column}", "clarification_run", [column])

    op.create_table(
        "clarification_question",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("clarification_run_id", sa.String(255), nullable=False),
        sa.Column("question_key", sa.String(255), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("priority_score", sa.Integer(), nullable=False),
        sa.Column("priority", sa.String(50), nullable=False),
        sa.Column("category", sa.String(50), nullable=False),
        sa.Column("audience", sa.String(50), nullable=False),
        sa.Column("question_text", sa.Text(), nullable=False),
        sa.Column("why_needed", sa.Text(), nullable=False),
        sa.Column("answer_type", sa.String(50), nullable=False),
        sa.Column("options_json", sa.Text(), nullable=True),
        sa.Column("issue_codes_json", sa.Text(), nullable=False),
        sa.Column("evidence_json", sa.Text(), nullable=False),
        sa.Column("impact_json", sa.Text(), nullable=False),
        sa.Column("status", sa.String(50), nullable=False, server_default="open"),
        sa.Column("latest_response_id", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "clarification_run_id",
            "question_key",
            name="uq_clarification_question_run_key",
        ),
    )
    for column in (
        "clarification_run_id",
        "question_key",
        "priority",
        "category",
        "audience",
        "status",
        "latest_response_id",
    ):
        op.create_index(
            f"ix_clarification_question_{column}",
            "clarification_question",
            [column],
        )

    op.create_table(
        "clarification_response",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("clarification_question_id", sa.String(255), nullable=False),
        sa.Column("response_number", sa.Integer(), nullable=False),
        sa.Column("resolution", sa.String(50), nullable=False),
        sa.Column("answer_json", sa.Text(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("responded_by_user_id", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "clarification_question_id",
            "response_number",
            name="uq_clarification_response_question_number",
        ),
    )
    for column in ("clarification_question_id", "resolution"):
        op.create_index(
            f"ix_clarification_response_{column}",
            "clarification_response",
            [column],
        )


def downgrade() -> None:
    for column in reversed(("clarification_question_id", "resolution")):
        op.drop_index(
            f"ix_clarification_response_{column}",
            table_name="clarification_response",
        )
    op.drop_table("clarification_response")

    for column in reversed(
        (
            "clarification_run_id",
            "question_key",
            "priority",
            "category",
            "audience",
            "status",
            "latest_response_id",
        )
    ):
        op.drop_index(
            f"ix_clarification_question_{column}",
            table_name="clarification_question",
        )
    op.drop_table("clarification_question")

    for column in reversed(
        (
            "data_quality_run_id",
            "source_table_id",
            "source_file_id",
            "import_session_id",
            "project_id",
            "input_fingerprint",
            "audience",
            "status",
        )
    ):
        op.drop_index(f"ix_clarification_run_{column}", table_name="clarification_run")
    op.drop_table("clarification_run")
