"""Deterministic data-quality assessment rules.

Persistence and run orchestration live in ``service.py``; this module contains
the pure issue-building policy and the database reads needed by individual
assessment stages.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from typing import Any

from src.modules.data_quality.models import (
    DataQualityCategory,
    DataQualitySeverity,
)
from src.modules.import_sessions.models import ImportSourceFile
from src.modules.mapping_engine.models import ColumnMappingStatus
from src.modules.normalized_data.models import (
    CreativeRecord,
    NormalizedFieldValue,
    NormalizedSourceRow,
    PerformanceObservation,
    Placement,
)
from src.shared.db.repository import json_loads
from src.modules.data_quality.issue_builder import append_issue
from src.modules.data_quality.normalization_assessments import assess_normalization
from src.modules.data_quality.readiness_assessments import assess_preliminary_readiness

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
_MEDIA_CONTEXT_FIELDS = {"platform", "placement_type", "format", "audience"}

_SCHEMA_WARNING_SEVERITY = {
    "empty_table": DataQualitySeverity.blocking,
    "row_limit_reached": DataQualitySeverity.blocking,
    "header_not_detected": DataQualitySeverity.warning,
    "low_header_confidence": DataQualitySeverity.warning,
    "duplicate_headers": DataQualitySeverity.warning,
    "cell_values_truncated": DataQualitySeverity.warning,
    "blank_row_stop_reached": DataQualitySeverity.warning,
    "encoding_fallback": DataQualitySeverity.warning,
    "empty_columns": DataQualitySeverity.info,
}

def assess_file_integrity(issues, integrity, source_files):
    if integrity.ok:
        append_issue(
            issues,
            category=DataQualityCategory.file_integrity,
            code="source_files_verified",
            severity=DataQualitySeverity.info,
            message="All immutable source files in the import session passed existence and checksum verification.",
            affected_count=integrity.checked_files,
            details={"checked_files": integrity.checked_files},
        )
    if integrity.missing_files:
        append_issue(
            issues,
            category=DataQualityCategory.file_integrity,
            code="source_files_missing",
            severity=DataQualitySeverity.blocking,
            message="One or more immutable source files are missing from local storage.",
            affected_count=len(integrity.missing_files),
            remediation_hint="Restore the original files from the approved local backup before analysis.",
            details={"file_ids": integrity.missing_files},
        )
    if integrity.corrupted_files:
        append_issue(
            issues,
            category=DataQualityCategory.file_integrity,
            code="source_files_corrupted",
            severity=DataQualitySeverity.blocking,
            message="One or more immutable source files no longer match their recorded SHA-256 checksum.",
            affected_count=len(integrity.corrupted_files),
            remediation_hint="Quarantine the changed files and restore the verified originals.",
            details={"file_ids": integrity.corrupted_files},
        )

    hashes: dict[str, list[ImportSourceFile]] = defaultdict(list)
    for item in source_files:
        hashes[item.sha256].append(item)
    duplicate_groups = [items for items in hashes.values() if len(items) > 1]
    if duplicate_groups:
        append_issue(
            issues,
            category=DataQualityCategory.duplicates,
            code="duplicate_source_files",
            severity=DataQualitySeverity.warning,
            message="The import session contains repeated files with identical SHA-256 content.",
            affected_count=sum(len(items) - 1 for items in duplicate_groups),
            remediation_hint="Confirm whether repeated deliveries should be excluded from aggregate analysis.",
            details={
                "groups": [
                    {
                        "sha256": items[0].sha256,
                        "file_ids": [item.id for item in items],
                        "filenames": [item.original_filename for item in items],
                    }
                    for items in duplicate_groups[:20]
                ]
            },
        )


def assess_schema(issues, table, inspection, columns):
    table_warnings = json_loads(table.warnings_json)
    if not isinstance(table_warnings, list):
        table_warnings = []
    inspection_warnings = json_loads(inspection.warnings_json)
    if not isinstance(inspection_warnings, list):
        inspection_warnings = []

    seen: set[tuple[str, str]] = set()
    for warning in [*inspection_warnings, *table_warnings]:
        if not isinstance(warning, dict):
            continue
        code = str(warning.get("code") or "source_schema_warning")
        key = (code, json.dumps(warning.get("context", {}), ensure_ascii=False, sort_keys=True))
        if key in seen:
            continue
        seen.add(key)
        severity = _SCHEMA_WARNING_SEVERITY.get(code, DataQualitySeverity.warning)
        append_issue(
            issues,
            category=DataQualityCategory.schema_detection,
            code=code,
            severity=severity,
            message=str(warning.get("message") or "The source inspector reported a schema warning."),
            scope_type="source_table",
            scope_id=table.id,
            source_file_id=table.source_file_id,
            source_table_id=table.id,
            details={"context": warning.get("context", {})},
        )

    if table.data_row_count == 0:
        append_issue(
            issues,
            category=DataQualityCategory.schema_detection,
            code="no_source_data_rows",
            severity=DataQualitySeverity.blocking,
            message="The inspected source table contains no data rows.",
            scope_type="source_table",
            scope_id=table.id,
            source_file_id=table.source_file_id,
            source_table_id=table.id,
        )
    if not columns:
        append_issue(
            issues,
            category=DataQualityCategory.schema_detection,
            code="no_source_columns",
            severity=DataQualitySeverity.blocking,
            message="The inspected source table contains no materialized columns.",
            scope_type="source_table",
            scope_id=table.id,
            source_file_id=table.source_file_id,
            source_table_id=table.id,
        )
    if table.truncated and not any(item["code"] == "row_limit_reached" for item in issues):
        append_issue(
            issues,
            category=DataQualityCategory.schema_detection,
            code="source_table_truncated",
            severity=DataQualitySeverity.blocking,
            message="Only part of the source table was materialized because an inspection limit was reached.",
            remediation_hint="Increase the local inspection limit and inspect the immutable original again.",
            scope_type="source_table",
            scope_id=table.id,
            source_file_id=table.source_file_id,
            source_table_id=table.id,
        )


def assess_mapping(issues, table, columns, mappings):
    mapping_by_column = {item.source_column_id: item for item in mappings}
    counts = Counter()
    confirmed_targets: list[str] = []
    confirmed_by_target: dict[str, list[str]] = defaultdict(list)
    for column in columns:
        mapping = mapping_by_column.get(column.id)
        status = mapping.status if mapping is not None else ColumnMappingStatus.unmapped
        counts[status] += 1
        if mapping is not None and status == ColumnMappingStatus.confirmed and mapping.target_field:
            confirmed_targets.append(mapping.target_field)
            confirmed_by_target[mapping.target_field].append(column.id)

    confirmed_count = counts[ColumnMappingStatus.confirmed]
    suggested_count = counts[ColumnMappingStatus.suggested]
    rejected_count = counts[ColumnMappingStatus.rejected]
    unmapped_count = counts[ColumnMappingStatus.unmapped]

    if confirmed_count == 0:
        append_issue(
            issues,
            category=DataQualityCategory.mapping,
            code="no_confirmed_mappings",
            severity=DataQualitySeverity.blocking,
            message="No source columns have analyst-confirmed mappings.",
            remediation_hint="Review the mapping suggestions and confirm only the intended fields.",
            scope_type="source_table",
            scope_id=table.id,
            source_file_id=table.source_file_id,
            source_table_id=table.id,
        )
    if suggested_count:
        append_issue(
            issues,
            category=DataQualityCategory.mapping,
            code="mapping_confirmation_required",
            severity=DataQualitySeverity.warning,
            message="Some source columns still have unconfirmed mapping suggestions.",
            affected_count=suggested_count,
            remediation_hint="Confirm, override or reject the proposed mappings before using those columns.",
            scope_type="source_table",
            scope_id=table.id,
            source_file_id=table.source_file_id,
            source_table_id=table.id,
        )
    if unmapped_count:
        append_issue(
            issues,
            category=DataQualityCategory.mapping,
            code="unmapped_source_columns",
            severity=DataQualitySeverity.info,
            message="Some source columns remain unmapped and are preserved as custom fields.",
            affected_count=unmapped_count,
            scope_type="source_table",
            scope_id=table.id,
            source_file_id=table.source_file_id,
            source_table_id=table.id,
        )
    if rejected_count:
        append_issue(
            issues,
            category=DataQualityCategory.mapping,
            code="rejected_source_columns",
            severity=DataQualitySeverity.info,
            message="Some source columns were explicitly rejected by an analyst and remain available in the raw payload.",
            affected_count=rejected_count,
            scope_type="source_table",
            scope_id=table.id,
            source_file_id=table.source_file_id,
            source_table_id=table.id,
        )

    duplicate_targets = {
        target: column_ids
        for target, column_ids in confirmed_by_target.items()
        if len(column_ids) > 1
    }
    if duplicate_targets:
        append_issue(
            issues,
            category=DataQualityCategory.mapping,
            code="duplicate_confirmed_targets",
            severity=DataQualitySeverity.warning,
            message="Several confirmed columns map to the same internal target field.",
            affected_count=sum(len(items) - 1 for items in duplicate_targets.values()),
            remediation_hint="Confirm that the leftmost non-empty value is the intended precedence rule.",
            scope_type="source_table",
            scope_id=table.id,
            source_file_id=table.source_file_id,
            source_table_id=table.id,
            details={"target_fields": duplicate_targets},
        )

    return (
        {
            "confirmed_mapping_count": confirmed_count,
            "suggested_mapping_count": suggested_count,
            "rejected_mapping_count": rejected_count,
            "unmapped_mapping_count": unmapped_count,
        },
        set(confirmed_targets),
    )
