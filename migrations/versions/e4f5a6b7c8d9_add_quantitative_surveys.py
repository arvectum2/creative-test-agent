"""add_quantitative_surveys

Revision ID: e4f5a6b7c8d9
Revises: d3e4f5a6b7c8
Create Date: 2026-07-24 19:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "e4f5a6b7c8d9"
down_revision: Union[str, None] = "d3e4f5a6b7c8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "quantitative_questionnaire",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("project_id", sa.String(255), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(50), nullable=False, server_default="draft"),
        sa.Column("locale", sa.String(20), nullable=False, server_default="en"),
        sa.Column("randomize_questions", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("metadata_json", sa.Text(), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_user_id", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "name", "version", name="uq_quant_questionnaire_project_name_version"),
    )
    for column in ("project_id", "name", "status"):
        op.create_index(f"ix_quantitative_questionnaire_{column}", "quantitative_questionnaire", [column])

    op.create_table(
        "quantitative_question",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("questionnaire_id", sa.String(255), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(100), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("question_type", sa.String(50), nullable=False),
        sa.Column("metric_key", sa.String(100), nullable=False),
        sa.Column("required", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("scale_min", sa.Float(), nullable=True),
        sa.Column("scale_max", sa.Float(), nullable=True),
        sa.Column("low_label", sa.String(255), nullable=True),
        sa.Column("high_label", sa.String(255), nullable=True),
        sa.Column("options_json", sa.Text(), nullable=True),
        sa.Column("reverse_scored", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("questionnaire_id", "code", name="uq_quant_questionnaire_question_code"),
        sa.UniqueConstraint("questionnaire_id", "position", name="uq_quant_questionnaire_question_position"),
    )
    for column in ("questionnaire_id", "code", "question_type", "metric_key"):
        op.create_index(f"ix_quantitative_question_{column}", "quantitative_question", [column])

    op.create_table(
        "quantitative_study",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("project_id", sa.String(255), nullable=False),
        sa.Column("questionnaire_id", sa.String(255), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("status", sa.String(50), nullable=False, server_default="draft"),
        sa.Column("target_response_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("response_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("creative_asset_ids_json", sa.Text(), nullable=False),
        sa.Column("randomize_creatives", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("seed", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("metadata_json", sa.Text(), nullable=True),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_user_id", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("project_id", "questionnaire_id", "status"):
        op.create_index(f"ix_quantitative_study_{column}", "quantitative_study", [column])

    op.create_table(
        "quantitative_response",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("study_id", sa.String(255), nullable=False),
        sa.Column("respondent_hash", sa.String(64), nullable=False),
        sa.Column("creative_asset_id", sa.String(255), nullable=False),
        sa.Column("source", sa.String(50), nullable=False),
        sa.Column("generation_provenance_json", sa.Text(), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("study_id", "respondent_hash", name="uq_quant_response_study_respondent"),
    )
    for column in ("study_id", "respondent_hash", "creative_asset_id", "source"):
        op.create_index(f"ix_quantitative_response_{column}", "quantitative_response", [column])

    op.create_table(
        "quantitative_answer",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("response_id", sa.String(255), nullable=False),
        sa.Column("question_id", sa.String(255), nullable=False),
        sa.Column("numeric_value", sa.Float(), nullable=True),
        sa.Column("boolean_value", sa.Boolean(), nullable=True),
        sa.Column("selected_values_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("response_id", "question_id", name="uq_quant_answer_response_question"),
    )
    for column in ("response_id", "question_id"):
        op.create_index(f"ix_quantitative_answer_{column}", "quantitative_answer", [column])


def downgrade() -> None:
    for column in reversed(("response_id", "question_id")):
        op.drop_index(f"ix_quantitative_answer_{column}", table_name="quantitative_answer")
    op.drop_table("quantitative_answer")
    for column in reversed(("study_id", "respondent_hash", "creative_asset_id", "source")):
        op.drop_index(f"ix_quantitative_response_{column}", table_name="quantitative_response")
    op.drop_table("quantitative_response")
    for column in reversed(("project_id", "questionnaire_id", "status")):
        op.drop_index(f"ix_quantitative_study_{column}", table_name="quantitative_study")
    op.drop_table("quantitative_study")
    for column in reversed(("questionnaire_id", "code", "question_type", "metric_key")):
        op.drop_index(f"ix_quantitative_question_{column}", table_name="quantitative_question")
    op.drop_table("quantitative_question")
    for column in reversed(("project_id", "name", "status")):
        op.drop_index(f"ix_quantitative_questionnaire_{column}", table_name="quantitative_questionnaire")
    op.drop_table("quantitative_questionnaire")
