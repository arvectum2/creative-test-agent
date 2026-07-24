"""add_normalized_domain

Revision ID: a0b1c2d3e4f5
Revises: f6a0b1c2d3e4
Create Date: 2026-07-24 16:15:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a0b1c2d3e4f5"
down_revision: Union[str, None] = "f6a0b1c2d3e4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "normalization_run",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("source_table_id", sa.String(255), nullable=False),
        sa.Column("source_file_id", sa.String(255), nullable=False),
        sa.Column("import_session_id", sa.String(255), nullable=False),
        sa.Column("project_id", sa.String(255), nullable=False),
        sa.Column("run_number", sa.Integer(), nullable=False),
        sa.Column("normalizer_name", sa.String(100), nullable=False),
        sa.Column("normalizer_version", sa.String(50), nullable=False),
        sa.Column("mapping_fingerprint", sa.String(64), nullable=False),
        sa.Column("mapping_snapshot_json", sa.Text(), nullable=False),
        sa.Column("status", sa.String(50), nullable=False, server_default="completed"),
        sa.Column("source_row_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("normalized_row_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("partial_row_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("skipped_row_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("failed_row_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("campaign_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("creative_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("platform_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("audience_segment_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("placement_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "performance_observation_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("warning_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("warnings_json", sa.Text(), nullable=True),
        sa.Column("error_code", sa.String(100), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "source_table_id",
            "normalizer_version",
            "mapping_fingerprint",
            "run_number",
            name="uq_normalization_run_table_version_fingerprint_number",
        ),
    )
    for column in (
        "source_table_id",
        "source_file_id",
        "import_session_id",
        "project_id",
        "mapping_fingerprint",
        "status",
    ):
        op.create_index(f"ix_normalization_run_{column}", "normalization_run", [column])

    op.create_table(
        "normalized_campaign",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("normalization_run_id", sa.String(255), nullable=False),
        sa.Column("project_id", sa.String(255), nullable=False),
        sa.Column("reference_key", sa.String(512), nullable=True),
        sa.Column("brand", sa.String(512), nullable=True),
        sa.Column("product", sa.String(512), nullable=True),
        sa.Column("metadata_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "normalization_run_id",
            "reference_key",
            name="uq_normalized_campaign_run_reference",
        ),
    )
    for column in ("normalization_run_id", "project_id", "reference_key"):
        op.create_index(f"ix_normalized_campaign_{column}", "normalized_campaign", [column])

    op.create_table(
        "normalized_creative_record",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("normalization_run_id", sa.String(255), nullable=False),
        sa.Column("project_id", sa.String(255), nullable=False),
        sa.Column("reference_key", sa.String(512), nullable=False),
        sa.Column("display_reference", sa.String(512), nullable=True),
        sa.Column("creative_asset_id", sa.String(255), nullable=True),
        sa.Column("metadata_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "normalization_run_id",
            "reference_key",
            name="uq_normalized_creative_run_reference",
        ),
    )
    for column in ("normalization_run_id", "project_id", "reference_key", "creative_asset_id"):
        op.create_index(
            f"ix_normalized_creative_record_{column}", "normalized_creative_record", [column]
        )

    op.create_table(
        "normalized_platform",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("normalization_run_id", sa.String(255), nullable=False),
        sa.Column("project_id", sa.String(255), nullable=False),
        sa.Column("canonical_key", sa.String(512), nullable=False),
        sa.Column("name", sa.String(512), nullable=False),
        sa.Column("metadata_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "normalization_run_id",
            "canonical_key",
            name="uq_normalized_platform_run_key",
        ),
    )
    for column in ("normalization_run_id", "project_id", "canonical_key"):
        op.create_index(f"ix_normalized_platform_{column}", "normalized_platform", [column])

    op.create_table(
        "normalized_audience_segment",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("normalization_run_id", sa.String(255), nullable=False),
        sa.Column("project_id", sa.String(255), nullable=False),
        sa.Column("canonical_key", sa.String(512), nullable=False),
        sa.Column("name", sa.String(512), nullable=False),
        sa.Column("metadata_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "normalization_run_id",
            "canonical_key",
            name="uq_normalized_audience_run_key",
        ),
    )
    for column in ("normalization_run_id", "project_id", "canonical_key"):
        op.create_index(
            f"ix_normalized_audience_segment_{column}",
            "normalized_audience_segment",
            [column],
        )

    op.create_table(
        "normalized_placement",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("normalization_run_id", sa.String(255), nullable=False),
        sa.Column("project_id", sa.String(255), nullable=False),
        sa.Column("source_row_id", sa.String(255), nullable=False),
        sa.Column("campaign_id", sa.String(255), nullable=True),
        sa.Column("creative_record_id", sa.String(255), nullable=True),
        sa.Column("platform_id", sa.String(255), nullable=True),
        sa.Column("audience_segment_id", sa.String(255), nullable=True),
        sa.Column("placement_type", sa.String(512), nullable=True),
        sa.Column("format", sa.String(512), nullable=True),
        sa.Column("metadata_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "normalization_run_id",
            "source_row_id",
            name="uq_normalized_placement_run_source_row",
        ),
    )
    for column in (
        "normalization_run_id",
        "project_id",
        "source_row_id",
        "campaign_id",
        "creative_record_id",
        "platform_id",
        "audience_segment_id",
    ):
        op.create_index(f"ix_normalized_placement_{column}", "normalized_placement", [column])

    op.create_table(
        "normalized_performance_observation",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("normalization_run_id", sa.String(255), nullable=False),
        sa.Column("project_id", sa.String(255), nullable=False),
        sa.Column("source_row_id", sa.String(255), nullable=False),
        sa.Column("placement_id", sa.String(255), nullable=True),
        sa.Column("observation_date", sa.Date(), nullable=True),
        sa.Column("impressions", sa.BigInteger(), nullable=True),
        sa.Column("clicks", sa.BigInteger(), nullable=True),
        sa.Column("ctr", sa.Float(), nullable=True),
        sa.Column("metadata_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "normalization_run_id",
            "source_row_id",
            name="uq_normalized_performance_run_source_row",
        ),
    )
    for column in (
        "normalization_run_id",
        "project_id",
        "source_row_id",
        "placement_id",
        "observation_date",
    ):
        op.create_index(
            f"ix_normalized_performance_observation_{column}",
            "normalized_performance_observation",
            [column],
        )

    op.create_table(
        "normalized_source_row",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("normalization_run_id", sa.String(255), nullable=False),
        sa.Column("project_id", sa.String(255), nullable=False),
        sa.Column("source_file_id", sa.String(255), nullable=False),
        sa.Column("source_table_id", sa.String(255), nullable=False),
        sa.Column("source_row_id", sa.String(255), nullable=False),
        sa.Column("source_row_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(50), nullable=False, server_default="normalized"),
        sa.Column("issue_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("issues_json", sa.Text(), nullable=True),
        sa.Column("source_payload_json", sa.Text(), nullable=False),
        sa.Column("custom_fields_json", sa.Text(), nullable=False),
        sa.Column("campaign_id", sa.String(255), nullable=True),
        sa.Column("creative_record_id", sa.String(255), nullable=True),
        sa.Column("platform_id", sa.String(255), nullable=True),
        sa.Column("audience_segment_id", sa.String(255), nullable=True),
        sa.Column("placement_id", sa.String(255), nullable=True),
        sa.Column("performance_observation_id", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "normalization_run_id",
            "source_row_id",
            name="uq_normalized_source_row_run_source_row",
        ),
    )
    for column in (
        "normalization_run_id",
        "project_id",
        "source_file_id",
        "source_table_id",
        "source_row_id",
        "status",
        "campaign_id",
        "creative_record_id",
        "platform_id",
        "audience_segment_id",
        "placement_id",
        "performance_observation_id",
    ):
        op.create_index(f"ix_normalized_source_row_{column}", "normalized_source_row", [column])

    op.create_table(
        "normalized_field_value",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("normalization_run_id", sa.String(255), nullable=False),
        sa.Column("project_id", sa.String(255), nullable=False),
        sa.Column("normalized_source_row_id", sa.String(255), nullable=False),
        sa.Column("entity_type", sa.String(100), nullable=False),
        sa.Column("entity_id", sa.String(255), nullable=False),
        sa.Column("field_name", sa.String(100), nullable=False),
        sa.Column("source_file_id", sa.String(255), nullable=False),
        sa.Column("source_table_id", sa.String(255), nullable=False),
        sa.Column("source_row_id", sa.String(255), nullable=False),
        sa.Column("source_row_number", sa.Integer(), nullable=False),
        sa.Column("source_column_id", sa.String(255), nullable=False),
        sa.Column("source_column_name", sa.String(512), nullable=False),
        sa.Column("column_mapping_id", sa.String(255), nullable=False),
        sa.Column("mapping_profile_id", sa.String(255), nullable=True),
        sa.Column("normalization_version", sa.String(50), nullable=False),
        sa.Column("raw_value_json", sa.Text(), nullable=False),
        sa.Column("normalized_value_json", sa.Text(), nullable=True),
        sa.Column("transformation", sa.String(100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "normalization_run_id",
            "source_row_id",
            "field_name",
            name="uq_normalized_field_run_row_field",
        ),
    )
    for column in (
        "normalization_run_id",
        "project_id",
        "normalized_source_row_id",
        "entity_type",
        "entity_id",
        "field_name",
        "source_file_id",
        "source_table_id",
        "source_row_id",
        "source_column_id",
        "column_mapping_id",
        "mapping_profile_id",
    ):
        op.create_index(
            f"ix_normalized_field_value_{column}", "normalized_field_value", [column]
        )


def downgrade() -> None:
    for column in (
        "mapping_profile_id",
        "column_mapping_id",
        "source_column_id",
        "source_row_id",
        "source_table_id",
        "source_file_id",
        "field_name",
        "entity_id",
        "entity_type",
        "normalized_source_row_id",
        "project_id",
        "normalization_run_id",
    ):
        op.drop_index(f"ix_normalized_field_value_{column}", table_name="normalized_field_value")
    op.drop_table("normalized_field_value")

    for column in (
        "performance_observation_id",
        "placement_id",
        "audience_segment_id",
        "platform_id",
        "creative_record_id",
        "campaign_id",
        "status",
        "source_row_id",
        "source_table_id",
        "source_file_id",
        "project_id",
        "normalization_run_id",
    ):
        op.drop_index(f"ix_normalized_source_row_{column}", table_name="normalized_source_row")
    op.drop_table("normalized_source_row")

    for column in (
        "observation_date",
        "placement_id",
        "source_row_id",
        "project_id",
        "normalization_run_id",
    ):
        op.drop_index(
            f"ix_normalized_performance_observation_{column}",
            table_name="normalized_performance_observation",
        )
    op.drop_table("normalized_performance_observation")

    for column in (
        "audience_segment_id",
        "platform_id",
        "creative_record_id",
        "campaign_id",
        "source_row_id",
        "project_id",
        "normalization_run_id",
    ):
        op.drop_index(f"ix_normalized_placement_{column}", table_name="normalized_placement")
    op.drop_table("normalized_placement")

    for column in ("canonical_key", "project_id", "normalization_run_id"):
        op.drop_index(
            f"ix_normalized_audience_segment_{column}",
            table_name="normalized_audience_segment",
        )
    op.drop_table("normalized_audience_segment")

    for column in ("canonical_key", "project_id", "normalization_run_id"):
        op.drop_index(f"ix_normalized_platform_{column}", table_name="normalized_platform")
    op.drop_table("normalized_platform")

    for column in ("creative_asset_id", "reference_key", "project_id", "normalization_run_id"):
        op.drop_index(
            f"ix_normalized_creative_record_{column}", table_name="normalized_creative_record"
        )
    op.drop_table("normalized_creative_record")

    for column in ("reference_key", "project_id", "normalization_run_id"):
        op.drop_index(f"ix_normalized_campaign_{column}", table_name="normalized_campaign")
    op.drop_table("normalized_campaign")

    for column in (
        "status",
        "mapping_fingerprint",
        "project_id",
        "import_session_id",
        "source_file_id",
        "source_table_id",
    ):
        op.drop_index(f"ix_normalization_run_{column}", table_name="normalization_run")
    op.drop_table("normalization_run")
