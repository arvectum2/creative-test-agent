"""Preliminary prediction-readiness assessment rules."""

from __future__ import annotations

from src.modules.data_quality.issue_builder import append_issue
from src.modules.data_quality.models import DataQualityCategory, DataQualitySeverity

_MEDIA_CONTEXT_FIELDS = {"platform", "placement_type", "format", "audience"}

def assess_preliminary_readiness(issues, *, table, confirmed_targets, readiness, normalization):
    if "creative_reference" not in confirmed_targets:
        append_issue(
            issues,
            category=DataQualityCategory.prediction_readiness,
            code="creative_reference_not_mapped",
            severity=DataQualitySeverity.warning,
            message="No confirmed creative-reference field is available for row-to-banner association.",
            scope_type="source_table",
            scope_id=table.id,
            source_file_id=table.source_file_id,
            source_table_id=table.id,
        )
    elif normalization is not None and not readiness["creative_references_present"]:
        append_issue(
            issues,
            category=DataQualityCategory.prediction_readiness,
            code="creative_references_not_present",
            severity=DataQualitySeverity.warning,
            message="The creative-reference column is mapped, but no normalized creative references are present.",
            scope_type="normalization_run",
            scope_id=normalization.id,
            source_file_id=normalization.source_file_id,
            source_table_id=normalization.source_table_id,
        )

    if not (_MEDIA_CONTEXT_FIELDS & confirmed_targets):
        append_issue(
            issues,
            category=DataQualityCategory.prediction_readiness,
            code="media_context_not_mapped",
            severity=DataQualitySeverity.warning,
            message="No platform, placement, format or audience field is confirmed.",
            scope_type="source_table",
            scope_id=table.id,
            source_file_id=table.source_file_id,
            source_table_id=table.id,
        )
    elif normalization is not None and not readiness["media_context_present"]:
        append_issue(
            issues,
            category=DataQualityCategory.prediction_readiness,
            code="media_context_not_present",
            severity=DataQualitySeverity.warning,
            message="Media-context columns are mapped, but the normalized rows contain no media context.",
            scope_type="normalization_run",
            scope_id=normalization.id,
            source_file_id=normalization.source_file_id,
            source_table_id=normalization.source_table_id,
        )

    if not ({"impressions", "clicks"} <= confirmed_targets):
        append_issue(
            issues,
            category=DataQualityCategory.prediction_readiness,
            code="click_impression_pair_not_mapped",
            severity=DataQualitySeverity.warning,
            message="Both impressions and clicks are not yet confirmed as source fields.",
            scope_type="source_table",
            scope_id=table.id,
            source_file_id=table.source_file_id,
            source_table_id=table.id,
        )
    elif normalization is not None and not readiness["paired_click_impression_rows_present"]:
        append_issue(
            issues,
            category=DataQualityCategory.prediction_readiness,
            code="click_impression_pairs_not_present",
            severity=DataQualitySeverity.warning,
            message="No normalized row contains a usable clicks-and-impressions pair.",
            scope_type="normalization_run",
            scope_id=normalization.id,
            source_file_id=normalization.source_file_id,
            source_table_id=normalization.source_table_id,
        )
