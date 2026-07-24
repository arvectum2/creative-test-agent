"""add_mapping_engine

Revision ID: f6a0b1c2d3e4
Revises: e5f6a0b1c2d3
Create Date: 2026-07-24 16:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f6a0b1c2d3e4"
down_revision: Union[str, None] = "e5f6a0b1c2d3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "mapping_profile",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("project_id", sa.String(255), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("source_label", sa.String(255), nullable=True),
        sa.Column("file_format", sa.String(32), nullable=True),
        sa.Column("sheet_name_pattern", sa.String(255), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("status", sa.String(50), nullable=False, server_default="active"),
        sa.Column("created_from_table_id", sa.String(255), nullable=False),
        sa.Column("created_by_user_id", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_mapping_profile_project_id", "mapping_profile", ["project_id"])
    op.create_index("ix_mapping_profile_status", "mapping_profile", ["status"])

    op.create_table(
        "mapping_profile_rule",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("mapping_profile_id", sa.String(255), nullable=False),
        sa.Column("source_key", sa.String(255), nullable=False),
        sa.Column("source_header", sa.Text(), nullable=True),
        sa.Column("source_inferred_type", sa.String(50), nullable=True),
        sa.Column("target_field", sa.String(100), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False, server_default=sa.text("1.0")),
        sa.Column("created_from_column_id", sa.String(255), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "mapping_profile_id",
            "source_key",
            name="uq_mapping_profile_rule_profile_source_key",
        ),
    )
    op.create_index(
        "ix_mapping_profile_rule_mapping_profile_id",
        "mapping_profile_rule",
        ["mapping_profile_id"],
    )
    op.create_index(
        "ix_mapping_profile_rule_target_field",
        "mapping_profile_rule",
        ["target_field"],
    )

    op.create_table(
        "mapping_run",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("source_table_id", sa.String(255), nullable=False),
        sa.Column("source_file_id", sa.String(255), nullable=False),
        sa.Column("import_session_id", sa.String(255), nullable=False),
        sa.Column("project_id", sa.String(255), nullable=False),
        sa.Column("run_number", sa.Integer(), nullable=False),
        sa.Column("engine_name", sa.String(100), nullable=False),
        sa.Column("engine_version", sa.String(50), nullable=False),
        sa.Column("mapping_profile_id", sa.String(255), nullable=True),
        sa.Column("status", sa.String(50), nullable=False, server_default="completed"),
        sa.Column("suggestion_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("warnings_json", sa.Text(), nullable=True),
        sa.Column("error_code", sa.String(100), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_mapping_run_source_table_id", "mapping_run", ["source_table_id"])
    op.create_index("ix_mapping_run_source_file_id", "mapping_run", ["source_file_id"])
    op.create_index("ix_mapping_run_import_session_id", "mapping_run", ["import_session_id"])
    op.create_index("ix_mapping_run_project_id", "mapping_run", ["project_id"])
    op.create_index("ix_mapping_run_mapping_profile_id", "mapping_run", ["mapping_profile_id"])
    op.create_index("ix_mapping_run_status", "mapping_run", ["status"])

    op.create_table(
        "mapping_suggestion",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("mapping_run_id", sa.String(255), nullable=False),
        sa.Column("source_table_id", sa.String(255), nullable=False),
        sa.Column("source_column_id", sa.String(255), nullable=False),
        sa.Column("target_field", sa.String(100), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("method", sa.String(50), nullable=False),
        sa.Column("explanation_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "mapping_run_id",
            "source_column_id",
            "target_field",
            name="uq_mapping_suggestion_run_column_target",
        ),
    )
    op.create_index(
        "ix_mapping_suggestion_mapping_run_id", "mapping_suggestion", ["mapping_run_id"]
    )
    op.create_index(
        "ix_mapping_suggestion_source_table_id", "mapping_suggestion", ["source_table_id"]
    )
    op.create_index(
        "ix_mapping_suggestion_source_column_id", "mapping_suggestion", ["source_column_id"]
    )
    op.create_index(
        "ix_mapping_suggestion_target_field", "mapping_suggestion", ["target_field"]
    )

    op.create_table(
        "column_mapping",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("source_table_id", sa.String(255), nullable=False),
        sa.Column("source_column_id", sa.String(255), nullable=False),
        sa.Column("target_field", sa.String(100), nullable=True),
        sa.Column("status", sa.String(50), nullable=False, server_default="unmapped"),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("decision_source", sa.String(50), nullable=False, server_default="engine"),
        sa.Column("selected_suggestion_id", sa.String(255), nullable=True),
        sa.Column("mapping_profile_id", sa.String(255), nullable=True),
        sa.Column("rationale_json", sa.Text(), nullable=True),
        sa.Column("decided_by_user_id", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_column_id", name="uq_column_mapping_source_column"),
    )
    op.create_index("ix_column_mapping_source_table_id", "column_mapping", ["source_table_id"])
    op.create_index("ix_column_mapping_source_column_id", "column_mapping", ["source_column_id"])
    op.create_index("ix_column_mapping_target_field", "column_mapping", ["target_field"])
    op.create_index("ix_column_mapping_status", "column_mapping", ["status"])
    op.create_index("ix_column_mapping_mapping_profile_id", "column_mapping", ["mapping_profile_id"])


def downgrade() -> None:
    op.drop_index("ix_column_mapping_mapping_profile_id", table_name="column_mapping")
    op.drop_index("ix_column_mapping_status", table_name="column_mapping")
    op.drop_index("ix_column_mapping_target_field", table_name="column_mapping")
    op.drop_index("ix_column_mapping_source_column_id", table_name="column_mapping")
    op.drop_index("ix_column_mapping_source_table_id", table_name="column_mapping")
    op.drop_table("column_mapping")

    op.drop_index("ix_mapping_suggestion_target_field", table_name="mapping_suggestion")
    op.drop_index("ix_mapping_suggestion_source_column_id", table_name="mapping_suggestion")
    op.drop_index("ix_mapping_suggestion_source_table_id", table_name="mapping_suggestion")
    op.drop_index("ix_mapping_suggestion_mapping_run_id", table_name="mapping_suggestion")
    op.drop_table("mapping_suggestion")

    op.drop_index("ix_mapping_run_status", table_name="mapping_run")
    op.drop_index("ix_mapping_run_mapping_profile_id", table_name="mapping_run")
    op.drop_index("ix_mapping_run_project_id", table_name="mapping_run")
    op.drop_index("ix_mapping_run_import_session_id", table_name="mapping_run")
    op.drop_index("ix_mapping_run_source_file_id", table_name="mapping_run")
    op.drop_index("ix_mapping_run_source_table_id", table_name="mapping_run")
    op.drop_table("mapping_run")

    op.drop_index("ix_mapping_profile_rule_target_field", table_name="mapping_profile_rule")
    op.drop_index(
        "ix_mapping_profile_rule_mapping_profile_id", table_name="mapping_profile_rule"
    )
    op.drop_table("mapping_profile_rule")

    op.drop_index("ix_mapping_profile_status", table_name="mapping_profile")
    op.drop_index("ix_mapping_profile_project_id", table_name="mapping_profile")
    op.drop_table("mapping_profile")
