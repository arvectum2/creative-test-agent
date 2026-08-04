"""Normalization-level data-quality assessment rules."""

from __future__ import annotations

import json
from collections import defaultdict

from src.modules.data_quality.issue_builder import append_issue
from src.modules.data_quality.models import DataQualityCategory, DataQualitySeverity
from src.modules.normalized_data.models import (
    CreativeRecord,
    NormalizedFieldValue,
    NormalizedSourceRow,
    PerformanceObservation,
    Placement,
)
from src.shared.db.repository import json_loads

_KEY_COVERAGE_FIELDS = {
    "creative_reference",
    "platform",
    "placement_type",
    "format",
    "date",
    "impressions",
    "clicks",
}
_METRIC_FIELDS = {"impressions", "clicks", "ctr"}

def assess_normalization(db, issues, normalization, confirmed_targets):
    rows = (
        db.query(NormalizedSourceRow)
        .filter(NormalizedSourceRow.normalization_run_id == normalization.id)
        .order_by(NormalizedSourceRow.source_row_number.asc(), NormalizedSourceRow.id.asc())
        .all()
    )
    field_values = (
        db.query(NormalizedFieldValue)
        .filter(NormalizedFieldValue.normalization_run_id == normalization.id)
        .all()
    )
    creatives = (
        db.query(CreativeRecord)
        .filter(CreativeRecord.normalization_run_id == normalization.id)
        .all()
    )
    placements = (
        db.query(Placement)
        .filter(Placement.normalization_run_id == normalization.id)
        .all()
    )
    observations = (
        db.query(PerformanceObservation)
        .filter(PerformanceObservation.normalization_run_id == normalization.id)
        .all()
    )

    if normalization.partial_row_count:
        append_issue(
            issues,
            category=DataQualityCategory.missing_values,
            code="partial_normalized_rows",
            severity=DataQualitySeverity.warning,
            message="Some source rows were only partially normalized.",
            affected_count=normalization.partial_row_count,
            remediation_hint="Review the row issues and clarify only the fields that affect the next analysis step.",
            scope_type="normalization_run",
            scope_id=normalization.id,
            source_file_id=normalization.source_file_id,
            source_table_id=normalization.source_table_id,
        )
    if normalization.skipped_row_count:
        append_issue(
            issues,
            category=DataQualityCategory.mapping,
            code="skipped_normalized_rows",
            severity=DataQualitySeverity.warning,
            message="Some source rows contained no non-empty confirmed mapped values.",
            affected_count=normalization.skipped_row_count,
            scope_type="normalization_run",
            scope_id=normalization.id,
            source_file_id=normalization.source_file_id,
            source_table_id=normalization.source_table_id,
        )
    if normalization.failed_row_count:
        append_issue(
            issues,
            category=DataQualityCategory.schema_detection,
            code="failed_normalized_rows",
            severity=DataQualitySeverity.blocking,
            message="Some source rows failed normalization completely.",
            affected_count=normalization.failed_row_count,
            scope_type="normalization_run",
            scope_id=normalization.id,
            source_file_id=normalization.source_file_id,
            source_table_id=normalization.source_table_id,
        )
    if rows and normalization.normalized_row_count + normalization.partial_row_count == 0:
        append_issue(
            issues,
            category=DataQualityCategory.prediction_readiness,
            code="no_usable_normalized_rows",
            severity=DataQualitySeverity.blocking,
            message="The normalization run contains no usable normalized or partial rows.",
            scope_type="normalization_run",
            scope_id=normalization.id,
            source_file_id=normalization.source_file_id,
            source_table_id=normalization.source_table_id,
        )

    _assess_row_issues(issues, normalization, rows)
    _assess_missing_values(issues, normalization, rows, field_values, confirmed_targets)
    _assess_duplicates(issues, normalization, rows, observations, placements)
    ambiguous_count = _assess_creative_linking(issues, normalization, rows, creatives)
    paired_metric_rows = _assess_metrics(issues, normalization, observations)

    linked_count = sum(item.creative_asset_id is not None for item in creatives)
    unlinked_count = len(creatives) - linked_count
    media_context_present = any(
        item.platform_id or item.placement_type or item.format or item.audience_segment_id
        for item in placements
    )
    metrics_present = any(
        item.impressions is not None or item.clicks is not None or item.ctr is not None
        for item in observations
    )
    return (
        {
            "normalized_row_count": normalization.normalized_row_count,
            "partial_row_count": normalization.partial_row_count,
            "skipped_row_count": normalization.skipped_row_count,
            "failed_row_count": normalization.failed_row_count,
            "creative_record_count": len(creatives),
            "linked_creative_count": linked_count,
            "unlinked_creative_count": unlinked_count,
            "ambiguous_creative_count": ambiguous_count,
            "performance_observation_count": len(observations),
        },
        {
            "creative_references_present": bool(creatives),
            "creative_assets_linked": bool(linked_count),
            "media_context_present": media_context_present,
            "performance_metrics_present": metrics_present,
            "paired_click_impression_rows_present": bool(paired_metric_rows),
        },
    )


def _assess_row_issues(issues, normalization, rows):
    grouped: dict[tuple[str, str], list[NormalizedSourceRow]] = defaultdict(list)
    examples: dict[tuple[str, str], dict] = {}
    for row in rows:
        row_issues = json_loads(row.issues_json)
        if not isinstance(row_issues, list):
            continue
        for item in row_issues:
            if not isinstance(item, dict):
                continue
            code = str(item.get("code") or "normalization_row_issue")
            if code in {
                "value_parse_failed",
                "creative_asset_not_linked",
                "creative_reference_ambiguous",
            }:
                continue
            severity = str(item.get("severity") or "warning")
            grouped[(code, severity)].append(row)
            examples.setdefault((code, severity), item)

    for (code, source_severity), affected_rows in grouped.items():
        category = (
            DataQualityCategory.mapping
            if code == "multiple_values_for_target"
            else DataQualityCategory.schema_detection
        )
        severity = (
            DataQualitySeverity.info
            if source_severity == "info"
            else DataQualitySeverity.warning
        )
        example = examples[(code, source_severity)]
        append_issue(
            issues,
            category=category,
            code=code,
            severity=severity,
            message=str(example.get("message") or "Normalization reported a row-level issue."),
            affected_count=len(affected_rows),
            scope_type="normalization_run",
            scope_id=normalization.id,
            source_file_id=normalization.source_file_id,
            source_table_id=normalization.source_table_id,
            details={
                "sample_source_row_numbers": [
                    row.source_row_number for row in affected_rows[:20]
                ],
                "sample_context": example.get("context", {}),
            },
        )


def _assess_missing_values(issues, normalization, rows, field_values, confirmed_targets):
    by_field: dict[str, list[NormalizedFieldValue]] = defaultdict(list)
    for item in field_values:
        by_field[item.field_name].append(item)
    total = len(rows)
    for field in sorted(confirmed_targets):
        values = by_field.get(field, [])
        present_rows = {item.source_row_id for item in values}
        valid_rows = {
            item.source_row_id
            for item in values
            if item.normalized_value_json is not None
        }
        missing_count = max(total - len(present_rows), 0)
        invalid_count = len(present_rows - valid_rows)
        if missing_count:
            severity = (
                DataQualitySeverity.warning
                if field in _KEY_COVERAGE_FIELDS
                else DataQualitySeverity.info
            )
            append_issue(
                issues,
                category=DataQualityCategory.missing_values,
                code=f"missing_{field}",
                severity=severity,
                message=f"Some normalized source rows have no source value for '{field}'.",
                affected_count=missing_count,
                scope_type="normalization_run",
                scope_id=normalization.id,
                source_file_id=normalization.source_file_id,
                source_table_id=normalization.source_table_id,
                details={
                    "field": field,
                    "total_rows": total,
                    "missing_ratio": round(missing_count / total, 6) if total else 0.0,
                },
            )
        if invalid_count:
            append_issue(
                issues,
                category=(
                    DataQualityCategory.metric_consistency
                    if field in _METRIC_FIELDS
                    else DataQualityCategory.missing_values
                ),
                code=f"invalid_{field}",
                severity=DataQualitySeverity.warning,
                message=f"Some source values for '{field}' could not be normalized.",
                affected_count=invalid_count,
                remediation_hint="Review the preserved raw values and confirm the source format.",
                scope_type="normalization_run",
                scope_id=normalization.id,
                source_file_id=normalization.source_file_id,
                source_table_id=normalization.source_table_id,
                details={"field": field, "total_rows": total},
            )


def _assess_duplicates(issues, normalization, rows, observations, placements):
    payload_groups: dict[str, list[NormalizedSourceRow]] = defaultdict(list)
    for row in rows:
        payload = json_loads(row.source_payload_json)
        canonical = json.dumps(
            payload if isinstance(payload, dict) else {},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        payload_groups[canonical].append(row)
    duplicate_payloads = [items for items in payload_groups.values() if len(items) > 1]
    if duplicate_payloads:
        append_issue(
            issues,
            category=DataQualityCategory.duplicates,
            code="duplicate_source_rows",
            severity=DataQualitySeverity.warning,
            message="The source table contains exact duplicate row payloads.",
            affected_count=sum(len(items) - 1 for items in duplicate_payloads),
            remediation_hint="Confirm whether duplicate rows are intentional before aggregation or modelling.",
            scope_type="normalization_run",
            scope_id=normalization.id,
            source_file_id=normalization.source_file_id,
            source_table_id=normalization.source_table_id,
            details={
                "groups": [
                    [row.source_row_number for row in items[:20]]
                    for items in duplicate_payloads[:20]
                ]
            },
        )

    placement_by_id = {item.id: item for item in placements}
    observation_groups: dict[tuple, list[PerformanceObservation]] = defaultdict(list)
    for observation in observations:
        placement = placement_by_id.get(observation.placement_id)
        key = (
            placement.campaign_id if placement else None,
            placement.creative_record_id if placement else None,
            placement.platform_id if placement else None,
            placement.audience_segment_id if placement else None,
            placement.placement_type if placement else None,
            placement.format if placement else None,
            observation.observation_date,
            observation.impressions,
            observation.clicks,
            observation.ctr,
        )
        observation_groups[key].append(observation)
    duplicate_observations = [items for items in observation_groups.values() if len(items) > 1]
    if duplicate_observations:
        append_issue(
            issues,
            category=DataQualityCategory.duplicates,
            code="duplicate_performance_observations",
            severity=DataQualitySeverity.warning,
            message="Several performance observations have identical normalized context and metrics.",
            affected_count=sum(len(items) - 1 for items in duplicate_observations),
            remediation_hint="Exclude accidental repeats before calculating campaign totals.",
            scope_type="normalization_run",
            scope_id=normalization.id,
            source_file_id=normalization.source_file_id,
            source_table_id=normalization.source_table_id,
            details={
                "sample_source_row_ids": [
                    [item.source_row_id for item in group[:20]]
                    for group in duplicate_observations[:20]
                ]
            },
        )


def _assess_creative_linking(issues, normalization, rows, creatives):
    linked = [item for item in creatives if item.creative_asset_id]
    unlinked = [item for item in creatives if not item.creative_asset_id]
    ambiguous_references: set[str] = set()
    for row in rows:
        row_issues = json_loads(row.issues_json)
        if not isinstance(row_issues, list):
            continue
        for item in row_issues:
            if isinstance(item, dict) and item.get("code") == "creative_reference_ambiguous":
                context = item.get("context", {})
                ambiguous_references.add(str(context.get("creative_reference") or row.id))

    if unlinked:
        append_issue(
            issues,
            category=DataQualityCategory.creative_linking,
            code="creative_assets_unlinked",
            severity=DataQualitySeverity.warning,
            message="Some normalized creative references are not linked to uploaded creative assets.",
            affected_count=len(unlinked),
            remediation_hint="Upload or identify only the creatives needed for the next test batch.",
            scope_type="normalization_run",
            scope_id=normalization.id,
            source_file_id=normalization.source_file_id,
            source_table_id=normalization.source_table_id,
            details={
                "sample_references": [item.display_reference for item in unlinked[:20]],
                "linked_count": len(linked),
            },
        )
    if ambiguous_references:
        append_issue(
            issues,
            category=DataQualityCategory.creative_linking,
            code="creative_references_ambiguous",
            severity=DataQualitySeverity.warning,
            message="Some creative references match several uploaded assets and were not linked automatically.",
            affected_count=len(ambiguous_references),
            remediation_hint="Select the intended asset manually for the ambiguous references.",
            scope_type="normalization_run",
            scope_id=normalization.id,
            source_file_id=normalization.source_file_id,
            source_table_id=normalization.source_table_id,
            details={"sample_references": sorted(ambiguous_references)[:20]},
        )
    return len(ambiguous_references)


def _assess_metrics(issues, normalization, observations):
    negative_impressions = [item for item in observations if item.impressions is not None and item.impressions < 0]
    negative_clicks = [item for item in observations if item.clicks is not None and item.clicks < 0]
    negative_ctr = [item for item in observations if item.ctr is not None and item.ctr < 0]
    zero_impression_clicks = [
        item
        for item in observations
        if item.impressions == 0 and item.clicks is not None and item.clicks > 0
    ]
    clicks_above_impressions = [
        item
        for item in observations
        if item.impressions is not None
        and item.impressions > 0
        and item.clicks is not None
        and item.clicks > item.impressions
    ]
    scale_suspected: list[PerformanceObservation] = []
    ctr_mismatch: list[PerformanceObservation] = []
    ctr_above_one: list[PerformanceObservation] = []
    paired = []

    for item in observations:
        if item.impressions is not None and item.impressions > 0 and item.clicks is not None:
            paired.append(item)
        if item.ctr is None:
            continue
        if item.ctr > 1:
            ctr_above_one.append(item)
        if item.impressions is None or item.impressions <= 0 or item.clicks is None:
            continue
        derived = item.clicks / item.impressions
        tolerance = max(0.0005, abs(derived) * 0.15)
        if item.ctr > 1 and abs(item.ctr / 100.0 - derived) <= tolerance:
            scale_suspected.append(item)
        elif abs(item.ctr - derived) > tolerance:
            ctr_mismatch.append(item)

    _metric_issue(
        issues,
        normalization,
        negative_impressions,
        code="negative_impressions",
        severity=DataQualitySeverity.blocking,
        message="Impression counts cannot be negative.",
    )
    _metric_issue(
        issues,
        normalization,
        negative_clicks,
        code="negative_clicks",
        severity=DataQualitySeverity.blocking,
        message="Click counts cannot be negative.",
    )
    _metric_issue(
        issues,
        normalization,
        negative_ctr,
        code="negative_ctr",
        severity=DataQualitySeverity.blocking,
        message="Supplied CTR values cannot be negative.",
    )
    _metric_issue(
        issues,
        normalization,
        zero_impression_clicks,
        code="clicks_with_zero_impressions",
        severity=DataQualitySeverity.blocking,
        message="Positive clicks are present while impressions are zero.",
    )
    _metric_issue(
        issues,
        normalization,
        clicks_above_impressions,
        code="clicks_above_impressions",
        severity=DataQualitySeverity.warning,
        message="Clicks exceed impressions in some rows; confirm the source metric definitions.",
    )
    _metric_issue(
        issues,
        normalization,
        scale_suspected,
        code="ctr_percent_scale_suspected",
        severity=DataQualitySeverity.warning,
        message="Supplied CTR appears to use percentage units while other CTR values use ratios.",
    )
    mismatch_without_scale = [item for item in ctr_mismatch if item not in scale_suspected]
    _metric_issue(
        issues,
        normalization,
        mismatch_without_scale,
        code="ctr_click_impression_mismatch",
        severity=DataQualitySeverity.warning,
        message="Supplied CTR materially differs from clicks divided by impressions.",
    )
    above_one_without_scale = [item for item in ctr_above_one if item not in scale_suspected]
    _metric_issue(
        issues,
        normalization,
        above_one_without_scale,
        code="ctr_above_one",
        severity=DataQualitySeverity.warning,
        message="Some supplied CTR values exceed 1.0; confirm whether they are ratios or percentages.",
    )
    return paired


def _metric_issue(issues, normalization, observations, *, code, severity, message):
    if not observations:
        return
    append_issue(
        issues,
        category=DataQualityCategory.metric_consistency,
        code=code,
        severity=severity,
        message=message,
        affected_count=len(observations),
        remediation_hint="Check the original export definitions and preserve the corrected source as a new import.",
        scope_type="normalization_run",
        scope_id=normalization.id,
        source_file_id=normalization.source_file_id,
        source_table_id=normalization.source_table_id,
        details={"sample_source_row_ids": [item.source_row_id for item in observations[:20]]},
    )
