from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from typing import Any

from sqlalchemy import func

from src.modules.data_quality.models import (
    DataQualityCategory,
    DataQualityIssue,
    DataQualityOverallStatus,
    DataQualityRun,
    DataQualityRunStatus,
    DataQualitySeverity,
)
from src.modules.data_quality.schemas import (
    DataQualityIssuePageResponse,
    DataQualityIssueResponse,
    DataQualityResultResponse,
    DataQualityRunResponse,
)
from src.modules.import_sessions.models import (
    ImportSourceFile,
    SourceColumn,
    SourceInspection,
    SourceTable,
)
from src.modules.import_sessions.service import verify_import_session
from src.modules.mapping_engine.models import ColumnMapping, ColumnMappingStatus
from src.modules.normalized_data.models import (
    CreativeRecord,
    NormalizationRun,
    NormalizationRunStatus,
    NormalizedFieldValue,
    NormalizedSourceRow,
    PerformanceObservation,
    Placement,
)
from src.modules.normalized_data.service import NORMALIZER_VERSION
from src.shared.db.repository import db_session, json_dumps, json_loads
from src.shared.errors import AppError

ENGINE_NAME = "deterministic-data-quality-engine"
ENGINE_VERSION = "1.1.0"

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


def generate_data_quality_report(
    import_session_id: str,
    source_file_id: str,
    source_table_id: str,
    *,
    force: bool = False,
    created_by_user_id: str | None = None,
) -> DataQualityResultResponse:
    integrity = verify_import_session(import_session_id)

    with db_session() as db:
        source_file, table, inspection = _load_table_context(
            db, import_session_id, source_file_id, source_table_id
        )
        source_files = (
            db.query(ImportSourceFile)
            .filter(ImportSourceFile.import_session_id == import_session_id)
            .order_by(ImportSourceFile.created_at.asc(), ImportSourceFile.id.asc())
            .all()
        )
        columns = (
            db.query(SourceColumn)
            .filter(SourceColumn.source_table_id == table.id)
            .order_by(SourceColumn.position.asc(), SourceColumn.id.asc())
            .all()
        )
        mappings = (
            db.query(ColumnMapping)
            .filter(ColumnMapping.source_table_id == table.id)
            .order_by(ColumnMapping.source_column_id.asc())
            .all()
        )
        current_mapping_fingerprint = _current_confirmed_mapping_fingerprint(
            columns, mappings
        )
        latest_completed_normalization = (
            db.query(NormalizationRun)
            .filter(
                NormalizationRun.source_table_id == table.id,
                NormalizationRun.status == NormalizationRunStatus.completed,
            )
            .order_by(NormalizationRun.run_number.desc(), NormalizationRun.created_at.desc())
            .first()
        )
        normalization = (
            db.query(NormalizationRun)
            .filter(
                NormalizationRun.source_table_id == table.id,
                NormalizationRun.status == NormalizationRunStatus.completed,
                NormalizationRun.normalizer_version == NORMALIZER_VERSION,
                NormalizationRun.mapping_fingerprint == current_mapping_fingerprint,
            )
            .order_by(NormalizationRun.run_number.desc(), NormalizationRun.created_at.desc())
            .first()
        )

        fingerprint = _input_fingerprint(
            source_files=source_files,
            source_file=source_file,
            table=table,
            inspection=inspection,
            columns=columns,
            mappings=mappings,
            normalization=normalization,
            current_mapping_fingerprint=current_mapping_fingerprint,
            latest_completed_normalization=latest_completed_normalization,
        )
        existing = (
            db.query(DataQualityRun)
            .filter(
                DataQualityRun.source_table_id == table.id,
                DataQualityRun.engine_version == ENGINE_VERSION,
                DataQualityRun.input_fingerprint == fingerprint,
                DataQualityRun.status == DataQualityRunStatus.completed,
            )
            .order_by(DataQualityRun.run_number.desc(), DataQualityRun.created_at.desc())
            .first()
        )
        if existing is not None and not force:
            return _result_response(db, existing)

        issues: list[dict[str, Any]] = []
        _assess_file_integrity(issues, integrity, source_files)
        _assess_schema(issues, table, inspection, columns)

        mapping_counts, confirmed_targets = _assess_mapping(
            issues, table, columns, mappings
        )
        normalization_counts: dict[str, int] = {
            "normalized_row_count": 0,
            "partial_row_count": 0,
            "skipped_row_count": 0,
            "failed_row_count": 0,
            "creative_record_count": 0,
            "linked_creative_count": 0,
            "unlinked_creative_count": 0,
            "ambiguous_creative_count": 0,
            "performance_observation_count": 0,
        }
        readiness = {
            "file_integrity_ok": bool(integrity.ok),
            "inspection_available": True,
            "confirmed_mapping_available": bool(mapping_counts["confirmed_mapping_count"]),
            "normalization_available": normalization is not None,
            "normalization_matches_current_mapping": normalization is not None,
            "creative_references_present": False,
            "creative_assets_linked": False,
            "media_context_present": False,
            "performance_metrics_present": False,
            "paired_click_impression_rows_present": False,
        }
        if normalization is None:
            if latest_completed_normalization is not None:
                _append_issue(
                    issues,
                    category=DataQualityCategory.prediction_readiness,
                    code="normalization_stale_for_current_mapping",
                    severity=DataQualitySeverity.blocking,
                    message=(
                        "A completed normalization exists, but it was produced from a different "
                        "mapping contract and cannot be used for this Data Quality run."
                    ),
                    remediation_hint="Run normalization again after confirming the current mappings.",
                    scope_type="source_table",
                    scope_id=table.id,
                    source_file_id=source_file.id,
                    source_table_id=table.id,
                    details={
                        "current_mapping_fingerprint": current_mapping_fingerprint,
                        "latest_completed_normalization_run_id": latest_completed_normalization.id,
                        "latest_completed_mapping_fingerprint": (
                            latest_completed_normalization.mapping_fingerprint
                        ),
                        "required_normalizer_version": NORMALIZER_VERSION,
                        "latest_completed_normalizer_version": (
                            latest_completed_normalization.normalizer_version
                        ),
                    },
                )
            else:
                _append_issue(
                    issues,
                    category=DataQualityCategory.prediction_readiness,
                    code="normalization_not_available",
                    severity=DataQualitySeverity.blocking,
                    message="No completed normalization run is available for this source table.",
                    remediation_hint="Confirm the intended column mappings and run normalization.",
                    scope_type="source_table",
                    scope_id=table.id,
                    source_file_id=source_file.id,
                    source_table_id=table.id,
                )
        else:
            normalization_counts, readiness_update = _assess_normalization(
                db,
                issues,
                normalization,
                confirmed_targets,
            )
            readiness.update(readiness_update)

        _assess_preliminary_readiness(
            issues,
            table=table,
            confirmed_targets=confirmed_targets,
            readiness=readiness,
            normalization=normalization,
        )

        severity_counts = Counter(item["severity"] for item in issues)
        category_counts: dict[str, dict[str, int]] = {}
        for category in DataQualityCategory:
            items = [item for item in issues if item["category"] == category]
            category_counts[str(category)] = {
                "info": sum(item["severity"] == DataQualitySeverity.info for item in items),
                "warning": sum(item["severity"] == DataQualitySeverity.warning for item in items),
                "blocking": sum(
                    item["severity"] == DataQualitySeverity.blocking for item in items
                ),
                "total": len(items),
                "affected": sum(item["affected_count"] for item in items),
            }

        if severity_counts[DataQualitySeverity.blocking]:
            overall_status = DataQualityOverallStatus.blocked
        elif severity_counts[DataQualitySeverity.warning]:
            overall_status = DataQualityOverallStatus.review_required
        else:
            overall_status = DataQualityOverallStatus.passed

        source_table_count = _active_source_table_count(db, import_session_id)
        summary = {
            "assessment_scope": "preliminary_data_quality",
            "prediction_decision": "not_evaluated_in_cta_pre_006",
            "coverage": {
                "source_files": len(source_files),
                "source_tables": source_table_count,
                "source_rows": table.data_row_count,
                "source_columns": len(columns),
                "confirmed_targets": sorted(confirmed_targets),
            },
            "readiness_indicators": readiness,
            "lineage": {
                "current_mapping_fingerprint": current_mapping_fingerprint,
                "selected_normalization_run_id": normalization.id if normalization else None,
                "selected_normalization_mapping_fingerprint": (
                    normalization.mapping_fingerprint if normalization else None
                ),
                "latest_completed_normalization_run_id": (
                    latest_completed_normalization.id
                    if latest_completed_normalization
                    else None
                ),
                "latest_completed_mapping_fingerprint": (
                    latest_completed_normalization.mapping_fingerprint
                    if latest_completed_normalization
                    else None
                ),
                "normalizer_version_required": NORMALIZER_VERSION,
            },
            "notes": [
                "Missing optional fields do not reject otherwise usable rows.",
                "Metric checks compare supplied values but do not calculate or predict CTR.",
                "Final prediction availability is determined by CTA-PRE-008, not this report.",
            ],
        }

        run_number = (
            db.query(func.max(DataQualityRun.run_number))
            .filter(DataQualityRun.source_table_id == table.id)
            .scalar()
            or 0
        ) + 1
        run = DataQualityRun(
            source_table_id=table.id,
            source_file_id=source_file.id,
            import_session_id=import_session_id,
            project_id=inspection.project_id,
            normalization_run_id=normalization.id if normalization else None,
            run_number=run_number,
            engine_name=ENGINE_NAME,
            engine_version=ENGINE_VERSION,
            input_fingerprint=fingerprint,
            status=DataQualityRunStatus.completed,
            overall_status=overall_status,
            source_file_count=len(source_files),
            source_table_count=source_table_count,
            source_row_count=table.data_row_count,
            source_column_count=len(columns),
            **mapping_counts,
            **normalization_counts,
            info_issue_count=severity_counts[DataQualitySeverity.info],
            warning_issue_count=severity_counts[DataQualitySeverity.warning],
            blocking_issue_count=severity_counts[DataQualitySeverity.blocking],
            total_issue_count=len(issues),
            category_counts_json=json_dumps(category_counts),
            summary_json=json_dumps(summary),
            created_by_user_id=created_by_user_id,
        )
        db.add(run)
        db.flush()

        for item in issues:
            db.add(
                DataQualityIssue(
                    data_quality_run_id=run.id,
                    category=item["category"],
                    code=item["code"],
                    severity=item["severity"],
                    scope_type=item["scope_type"],
                    scope_id=item.get("scope_id"),
                    source_file_id=item.get("source_file_id"),
                    source_table_id=item.get("source_table_id"),
                    source_row_id=item.get("source_row_id"),
                    source_column_id=item.get("source_column_id"),
                    affected_count=item["affected_count"],
                    message=item["message"],
                    remediation_hint=item.get("remediation_hint"),
                    details_json=json_dumps(item.get("details", {})),
                )
            )
        db.flush()
        db.refresh(run)
        return _result_response(db, run)


def get_latest_data_quality_report(
    import_session_id: str,
    source_file_id: str,
    source_table_id: str,
) -> DataQualityResultResponse | None:
    with db_session() as db:
        _source_file, table, _inspection = _load_table_context(
            db, import_session_id, source_file_id, source_table_id
        )
        run = (
            db.query(DataQualityRun)
            .filter(DataQualityRun.source_table_id == table.id)
            .order_by(DataQualityRun.run_number.desc(), DataQualityRun.created_at.desc())
            .first()
        )
        return _result_response(db, run) if run else None


def get_data_quality_report(run_id: str) -> DataQualityResultResponse | None:
    with db_session() as db:
        run = db.query(DataQualityRun).filter(DataQualityRun.id == run_id).first()
        return _result_response(db, run) if run else None


def list_data_quality_issues(
    run_id: str,
    *,
    category: str | None = None,
    severity: str | None = None,
    offset: int = 0,
    limit: int = 100,
) -> DataQualityIssuePageResponse:
    with db_session() as db:
        run = db.query(DataQualityRun).filter(DataQualityRun.id == run_id).first()
        if run is None:
            raise AppError("data_quality_run_not_found", "Data-quality run not found", 404)
        query = db.query(DataQualityIssue).filter(DataQualityIssue.data_quality_run_id == run.id)
        if category:
            if category not in {str(item) for item in DataQualityCategory}:
                raise AppError("invalid_data_quality_category", "Unknown data-quality category", 400)
            query = query.filter(DataQualityIssue.category == category)
        if severity:
            if severity not in {str(item) for item in DataQualitySeverity}:
                raise AppError("invalid_data_quality_severity", "Unknown data-quality severity", 400)
            query = query.filter(DataQualityIssue.severity == severity)
        total = query.count()
        items = (
            query.order_by(
                DataQualityIssue.severity.desc(),
                DataQualityIssue.category.asc(),
                DataQualityIssue.code.asc(),
                DataQualityIssue.id.asc(),
            )
            .offset(offset)
            .limit(limit)
            .all()
        )
        return DataQualityIssuePageResponse(
            data_quality_run_id=run.id,
            offset=offset,
            limit=limit,
            total=total,
            issues=[_issue_response(item) for item in items],
        )


def _load_table_context(db, import_session_id: str, source_file_id: str, source_table_id: str):
    source_file = (
        db.query(ImportSourceFile)
        .filter(
            ImportSourceFile.id == source_file_id,
            ImportSourceFile.import_session_id == import_session_id,
        )
        .first()
    )
    if source_file is None:
        raise AppError("import_source_file_not_found", "Import source file not found", 404)
    table = (
        db.query(SourceTable)
        .filter(SourceTable.id == source_table_id, SourceTable.source_file_id == source_file_id)
        .first()
    )
    if table is None:
        raise AppError("source_table_not_found", "Source table not found", 404)
    inspection = (
        db.query(SourceInspection)
        .filter(
            SourceInspection.id == table.inspection_id,
            SourceInspection.source_file_id == source_file_id,
            SourceInspection.import_session_id == import_session_id,
            SourceInspection.status == "completed",
        )
        .first()
    )
    if inspection is None:
        raise AppError(
            "source_table_context_mismatch",
            "Source table does not belong to the requested completed inspection",
            404,
        )
    return source_file, table, inspection



def _current_confirmed_mapping_fingerprint(columns, mappings) -> str:
    column_by_id = {column.id: column for column in columns}
    confirmed = [
        mapping
        for mapping in mappings
        if mapping.status == ColumnMappingStatus.confirmed
        and mapping.target_field
        and mapping.source_column_id in column_by_id
    ]
    confirmed.sort(
        key=lambda mapping: (
            column_by_id[mapping.source_column_id].position,
            mapping.id,
        )
    )
    snapshot = []
    for mapping in confirmed:
        column = column_by_id[mapping.source_column_id]
        snapshot.append(
            {
                "column_mapping_id": mapping.id,
                "source_column_id": column.id,
                "position": column.position,
                "source_header": column.source_header,
                "normalized_header": column.normalized_header,
                "inferred_type": column.inferred_type,
                "target_field": mapping.target_field,
                "mapping_profile_id": mapping.mapping_profile_id,
                "decision_source": mapping.decision_source,
            }
        )
    encoded = json.dumps(
        snapshot,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _active_source_table_count(db, import_session_id: str) -> int:
    inspections = (
        db.query(SourceInspection)
        .filter(
            SourceInspection.import_session_id == import_session_id,
            SourceInspection.status == "completed",
        )
        .order_by(
            SourceInspection.source_file_id.asc(),
            SourceInspection.inspection_number.desc(),
            SourceInspection.created_at.desc(),
            SourceInspection.id.desc(),
        )
        .all()
    )
    latest_by_file = {}
    for inspection in inspections:
        latest_by_file.setdefault(inspection.source_file_id, inspection.id)
    if not latest_by_file:
        return 0
    return (
        db.query(func.count(SourceTable.id))
        .filter(SourceTable.inspection_id.in_(tuple(latest_by_file.values())))
        .scalar()
        or 0
    )

def _input_fingerprint(
    *,
    source_files,
    source_file,
    table,
    inspection,
    columns,
    mappings,
    normalization,
    current_mapping_fingerprint,
    latest_completed_normalization,
):
    mapping_by_column = {item.source_column_id: item for item in mappings}
    payload = {
        "engine_version": ENGINE_VERSION,
        "current_mapping_fingerprint": current_mapping_fingerprint,
        "latest_completed_normalization": (
            {
                "id": latest_completed_normalization.id,
                "normalizer_version": latest_completed_normalization.normalizer_version,
                "mapping_fingerprint": latest_completed_normalization.mapping_fingerprint,
                "status": latest_completed_normalization.status,
                "run_number": latest_completed_normalization.run_number,
            }
            if latest_completed_normalization
            else None
        ),
        "source_files": [
            {
                "id": item.id,
                "sha256": item.sha256,
                "size": item.file_size_bytes,
            }
            for item in source_files
        ],
        "selected_source_file": {
            "id": source_file.id,
            "sha256": source_file.sha256,
        },
        "inspection": {
            "id": inspection.id,
            "parser_name": inspection.parser_name,
            "parser_version": inspection.parser_version,
            "status": inspection.status,
        },
        "table": {
            "id": table.id,
            "header_row_number": table.header_row_number,
            "header_confidence": table.header_confidence,
            "source_row_count": table.source_row_count,
            "data_row_count": table.data_row_count,
            "column_count": table.column_count,
            "truncated": table.truncated,
            "warnings": json_loads(table.warnings_json),
        },
        "columns": [
            {
                "id": column.id,
                "position": column.position,
                "normalized_header": column.normalized_header,
                "inferred_type": column.inferred_type,
                "is_empty": column.is_empty,
                "mapping": _mapping_fingerprint_item(mapping_by_column.get(column.id)),
            }
            for column in columns
        ],
        "normalization": (
            {
                "normalizer_version": normalization.normalizer_version,
                "mapping_fingerprint": normalization.mapping_fingerprint,
                "status": normalization.status,
                "source_row_count": normalization.source_row_count,
                "normalized_row_count": normalization.normalized_row_count,
                "partial_row_count": normalization.partial_row_count,
                "skipped_row_count": normalization.skipped_row_count,
                "failed_row_count": normalization.failed_row_count,
            }
            if normalization
            else None
        ),
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _mapping_fingerprint_item(mapping):
    if mapping is None:
        return None
    return {
        "id": mapping.id,
        "status": mapping.status,
        "target_field": mapping.target_field,
        "decision_source": mapping.decision_source,
        "mapping_profile_id": mapping.mapping_profile_id,
    }


def _assess_file_integrity(issues, integrity, source_files):
    if integrity.ok:
        _append_issue(
            issues,
            category=DataQualityCategory.file_integrity,
            code="source_files_verified",
            severity=DataQualitySeverity.info,
            message="All immutable source files in the import session passed existence and checksum verification.",
            affected_count=integrity.checked_files,
            details={"checked_files": integrity.checked_files},
        )
    if integrity.missing_files:
        _append_issue(
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
        _append_issue(
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
        _append_issue(
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


def _assess_schema(issues, table, inspection, columns):
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
        _append_issue(
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
        _append_issue(
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
        _append_issue(
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
        _append_issue(
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


def _assess_mapping(issues, table, columns, mappings):
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
        _append_issue(
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
        _append_issue(
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
        _append_issue(
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
        _append_issue(
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
        _append_issue(
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


def _assess_normalization(db, issues, normalization, confirmed_targets):
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
        _append_issue(
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
        _append_issue(
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
        _append_issue(
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
        _append_issue(
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
        _append_issue(
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
            _append_issue(
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
            _append_issue(
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
        _append_issue(
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
        _append_issue(
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
        _append_issue(
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
        _append_issue(
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
    _append_issue(
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


def _assess_preliminary_readiness(issues, *, table, confirmed_targets, readiness, normalization):
    if "creative_reference" not in confirmed_targets:
        _append_issue(
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
        _append_issue(
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
        _append_issue(
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
        _append_issue(
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
        _append_issue(
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
        _append_issue(
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


def _append_issue(
    issues,
    *,
    category,
    code,
    severity,
    message,
    affected_count=1,
    remediation_hint=None,
    scope_type="run",
    scope_id=None,
    source_file_id=None,
    source_table_id=None,
    source_row_id=None,
    source_column_id=None,
    details=None,
):
    issues.append(
        {
            "category": str(category),
            "code": code,
            "severity": str(severity),
            "message": message,
            "affected_count": max(int(affected_count), 0),
            "remediation_hint": remediation_hint,
            "scope_type": scope_type,
            "scope_id": scope_id,
            "source_file_id": source_file_id,
            "source_table_id": source_table_id,
            "source_row_id": source_row_id,
            "source_column_id": source_column_id,
            "details": details or {},
        }
    )


def _result_response(db, run):
    issues = (
        db.query(DataQualityIssue)
        .filter(DataQualityIssue.data_quality_run_id == run.id)
        .order_by(
            DataQualityIssue.severity.desc(),
            DataQualityIssue.category.asc(),
            DataQualityIssue.code.asc(),
            DataQualityIssue.id.asc(),
        )
        .all()
    )
    return DataQualityResultResponse(
        run=_run_response(run),
        issues=[_issue_response(item) for item in issues],
    )


def _run_response(model):
    category_counts = json_loads(model.category_counts_json)
    summary = json_loads(model.summary_json)
    return DataQualityRunResponse(
        id=model.id,
        source_table_id=model.source_table_id,
        source_file_id=model.source_file_id,
        import_session_id=model.import_session_id,
        project_id=model.project_id,
        normalization_run_id=model.normalization_run_id,
        run_number=model.run_number,
        engine_name=model.engine_name,
        engine_version=model.engine_version,
        input_fingerprint=model.input_fingerprint,
        status=model.status,
        overall_status=model.overall_status,
        source_file_count=model.source_file_count,
        source_table_count=model.source_table_count,
        source_row_count=model.source_row_count,
        source_column_count=model.source_column_count,
        confirmed_mapping_count=model.confirmed_mapping_count,
        suggested_mapping_count=model.suggested_mapping_count,
        rejected_mapping_count=model.rejected_mapping_count,
        unmapped_mapping_count=model.unmapped_mapping_count,
        normalized_row_count=model.normalized_row_count,
        partial_row_count=model.partial_row_count,
        skipped_row_count=model.skipped_row_count,
        failed_row_count=model.failed_row_count,
        creative_record_count=model.creative_record_count,
        linked_creative_count=model.linked_creative_count,
        unlinked_creative_count=model.unlinked_creative_count,
        ambiguous_creative_count=model.ambiguous_creative_count,
        performance_observation_count=model.performance_observation_count,
        info_issue_count=model.info_issue_count,
        warning_issue_count=model.warning_issue_count,
        blocking_issue_count=model.blocking_issue_count,
        total_issue_count=model.total_issue_count,
        category_counts=category_counts if isinstance(category_counts, dict) else {},
        summary=summary if isinstance(summary, dict) else {},
        error_code=model.error_code,
        error_message=model.error_message,
        created_by_user_id=model.created_by_user_id,
        created_at=model.created_at,
    )


def _issue_response(model):
    details = json_loads(model.details_json)
    return DataQualityIssueResponse(
        id=model.id,
        data_quality_run_id=model.data_quality_run_id,
        category=model.category,
        code=model.code,
        severity=model.severity,
        scope_type=model.scope_type,
        scope_id=model.scope_id,
        source_file_id=model.source_file_id,
        source_table_id=model.source_table_id,
        source_row_id=model.source_row_id,
        source_column_id=model.source_column_id,
        affected_count=model.affected_count,
        message=model.message,
        remediation_hint=model.remediation_hint,
        details=details if isinstance(details, dict) else {},
        created_at=model.created_at,
    )
