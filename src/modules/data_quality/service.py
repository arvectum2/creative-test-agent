from __future__ import annotations

import hashlib
import json
from collections import Counter
from typing import Any

from sqlalchemy import func

from src.modules.data_quality.assessments import (
    append_issue,
    assess_file_integrity,
    assess_mapping,
    assess_normalization,
    assess_preliminary_readiness,
    assess_schema,
)
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
    NormalizationRun,
    NormalizationRunStatus,
)
from src.modules.normalized_data.service import NORMALIZER_VERSION
from src.shared.db.repository import db_session, json_dumps, json_loads
from src.shared.errors import AppError

ENGINE_NAME = "deterministic-data-quality-engine"
ENGINE_VERSION = "1.1.0"


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
        assess_file_integrity(issues, integrity, source_files)
        assess_schema(issues, table, inspection, columns)

        mapping_counts, confirmed_targets = assess_mapping(
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
                append_issue(
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
                append_issue(
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
            normalization_counts, readiness_update = assess_normalization(
                db,
                issues,
                normalization,
                confirmed_targets,
            )
            readiness.update(readiness_update)

        assess_preliminary_readiness(
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
