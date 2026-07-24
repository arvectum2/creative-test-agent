from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from sqlalchemy import func

from src.modules.clarifications.models import (
    ClarificationQuestion,
    ClarificationResponse,
    ClarificationRun,
)
from src.modules.data_quality.models import DataQualityIssue, DataQualityRun, DataQualityRunStatus
from src.modules.data_review_reports.models import DataReviewReportRun, DataReviewReportStatus
from src.modules.data_review_reports.schemas import DataReviewReportResponse
from src.modules.import_sessions.models import (
    ImportSourceFile,
    SourceColumn,
    SourceInspection,
    SourceTable,
)
from src.modules.mapping_engine.models import ColumnMapping
from src.modules.normalized_data.models import NormalizedSourceRow
from src.modules.prediction_readiness.models import (
    PredictionCapabilityReadiness,
    PredictionReadinessRun,
)
from src.modules.quantitative_surveys.models import QuantitativeStudy
from src.modules.quantitative_surveys.service import study_results
from src.shared.config.settings import get_settings
from src.shared.db.repository import db_session, json_dumps, json_loads
from src.shared.errors import AppError
from src.shared.xlsx.simple_writer import Cell, SheetSpec, write_xlsx

GENERATOR_NAME = "local-data-review-xlsx-generator"
GENERATOR_VERSION = "1.0.0"
NORMALIZED_ROW_EXPORT_LIMIT = 500


def generate_data_review_report(
    data_quality_run_id: str,
    *,
    prediction_readiness_run_id: str | None = None,
    quantitative_study_id: str | None = None,
    force: bool = False,
    created_by_user_id: str | None = None,
) -> DataReviewReportResponse:
    with db_session() as db:
        quality = db.query(DataQualityRun).filter(DataQualityRun.id == data_quality_run_id).first()
        if quality is None:
            raise AppError("data_quality_run_not_found", "Data-quality run not found", 404)
        if quality.status != DataQualityRunStatus.completed:
            raise AppError("data_quality_run_not_completed", "Report requires a completed data-quality run", 409)

        readiness = _resolve_readiness(db, quality, prediction_readiness_run_id)
        study = _resolve_study(db, quality.project_id, quantitative_study_id)
        fingerprint_payload = {
            "generator_version": GENERATOR_VERSION,
            "data_quality_run_id": quality.id,
            "data_quality_input_fingerprint": quality.input_fingerprint,
            "data_quality_issue_count": quality.total_issue_count,
            "prediction_readiness": (
                {
                    "id": readiness.id,
                    "input_fingerprint": readiness.input_fingerprint,
                    "overall_status": readiness.overall_status,
                }
                if readiness
                else None
            ),
            "quantitative_study": (
                {
                    "id": study.id,
                    "status": study.status,
                    "response_count": study.response_count,
                    "target_response_count": study.target_response_count,
                }
                if study
                else None
            ),
        }
        fingerprint = hashlib.sha256(
            json.dumps(fingerprint_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        existing = (
            db.query(DataReviewReportRun)
            .filter(
                DataReviewReportRun.data_quality_run_id == quality.id,
                DataReviewReportRun.generator_version == GENERATOR_VERSION,
                DataReviewReportRun.input_fingerprint == fingerprint,
                DataReviewReportRun.status == DataReviewReportStatus.completed,
            )
            .order_by(DataReviewReportRun.run_number.desc(), DataReviewReportRun.created_at.desc())
            .first()
        )
        if existing is not None and not force and _stored_report_valid(existing):
            return _response(existing)
        run_number = (
            db.query(func.max(DataReviewReportRun.run_number))
            .filter(DataReviewReportRun.data_quality_run_id == quality.id)
            .scalar()
            or 0
        ) + 1
        context = {
            "quality_id": quality.id,
            "readiness_id": readiness.id if readiness else None,
            "study_id": study.id if study else None,
            "project_id": quality.project_id,
            "source_table_id": quality.source_table_id,
            "source_file_id": quality.source_file_id,
            "import_session_id": quality.import_session_id,
            "fingerprint": fingerprint,
            "run_number": run_number,
        }

    report_id = str(uuid4())
    sheets, summary = _build_sheets(
        data_quality_run_id,
        prediction_readiness_run_id=context["readiness_id"],
        quantitative_study_id=context["study_id"],
    )
    settings = get_settings()
    directory = Path(settings.storage_root) / "data_review_reports"
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    project_slug = _slug(context["project_id"])[:24]
    filename = f"data_review_{project_slug}_{timestamp}_{report_id[:8]}.xlsx"
    path = directory / filename
    write_xlsx(
        path,
        sheets,
        title=f"Arvectum data review — {context['project_id']}",
    )
    sha256 = _sha256_file(path)
    size = path.stat().st_size

    with db_session() as db:
        model = DataReviewReportRun(
            id=report_id,
            data_quality_run_id=context["quality_id"],
            prediction_readiness_run_id=context["readiness_id"],
            quantitative_study_id=context["study_id"],
            source_table_id=context["source_table_id"],
            source_file_id=context["source_file_id"],
            import_session_id=context["import_session_id"],
            project_id=context["project_id"],
            run_number=context["run_number"],
            generator_name=GENERATOR_NAME,
            generator_version=GENERATOR_VERSION,
            input_fingerprint=context["fingerprint"],
            status=DataReviewReportStatus.completed,
            filename=filename,
            storage_path=str(path),
            sha256=sha256,
            file_size_bytes=size,
            sheet_count=len(sheets),
            summary_json=json_dumps(summary),
            created_by_user_id=created_by_user_id,
        )
        db.add(model)
        db.flush()
        db.refresh(model)
        return _response(model)


def get_data_review_report(report_id: str) -> DataReviewReportResponse | None:
    with db_session() as db:
        model = db.query(DataReviewReportRun).filter(DataReviewReportRun.id == report_id).first()
        return _response(model) if model else None


def get_latest_data_review_report(data_quality_run_id: str) -> DataReviewReportResponse | None:
    with db_session() as db:
        quality = db.query(DataQualityRun.id).filter(DataQualityRun.id == data_quality_run_id).first()
        if quality is None:
            raise AppError("data_quality_run_not_found", "Data-quality run not found", 404)
        model = (
            db.query(DataReviewReportRun)
            .filter(DataReviewReportRun.data_quality_run_id == data_quality_run_id)
            .order_by(DataReviewReportRun.run_number.desc(), DataReviewReportRun.created_at.desc())
            .first()
        )
        return _response(model) if model else None


def data_review_report_path(report_id: str) -> tuple[Path, str]:
    with db_session() as db:
        model = db.query(DataReviewReportRun).filter(DataReviewReportRun.id == report_id).first()
        if model is None:
            raise AppError("data_review_report_not_found", "Data-review report not found", 404)
        path = Path(model.storage_path)
        if not path.is_file():
            raise AppError("data_review_report_missing", "Stored data-review report is missing", 409)
        if _sha256_file(path) != model.sha256:
            raise AppError("data_review_report_corrupted", "Stored data-review report failed SHA-256 verification", 409)
        return path, model.filename


def _resolve_readiness(db, quality, requested_id):
    query = db.query(PredictionReadinessRun).filter(
        PredictionReadinessRun.data_quality_run_id == quality.id,
        PredictionReadinessRun.project_id == quality.project_id,
    )
    if requested_id:
        model = query.filter(PredictionReadinessRun.id == requested_id).first()
        if model is None:
            raise AppError("prediction_readiness_context_mismatch", "Prediction-readiness run does not belong to this data-quality run", 409)
        return model
    return query.order_by(PredictionReadinessRun.run_number.desc(), PredictionReadinessRun.created_at.desc()).first()


def _resolve_study(db, project_id, requested_id):
    query = db.query(QuantitativeStudy).filter(QuantitativeStudy.project_id == project_id)
    if requested_id:
        model = query.filter(QuantitativeStudy.id == requested_id).first()
        if model is None:
            raise AppError("quantitative_study_context_mismatch", "Quantitative study does not belong to this project", 409)
        return model
    return query.filter(QuantitativeStudy.response_count > 0).order_by(QuantitativeStudy.created_at.desc()).first()


def _build_sheets(data_quality_run_id: str, *, prediction_readiness_run_id: str | None, quantitative_study_id: str | None):
    survey = study_results(quantitative_study_id) if quantitative_study_id else None
    with db_session() as db:
        quality = db.query(DataQualityRun).filter(DataQualityRun.id == data_quality_run_id).first()
        issues = (
            db.query(DataQualityIssue)
            .filter(DataQualityIssue.data_quality_run_id == quality.id)
            .order_by(DataQualityIssue.severity.desc(), DataQualityIssue.category.asc(), DataQualityIssue.code.asc())
            .all()
        )
        source_files = (
            db.query(ImportSourceFile)
            .filter(ImportSourceFile.import_session_id == quality.import_session_id)
            .order_by(ImportSourceFile.created_at.asc(), ImportSourceFile.id.asc())
            .all()
        )
        inspections = (
            db.query(SourceInspection)
            .filter(SourceInspection.import_session_id == quality.import_session_id)
            .order_by(SourceInspection.created_at.asc(), SourceInspection.id.asc())
            .all()
        )
        inspection_ids = [item.id for item in inspections]
        tables = (
            db.query(SourceTable)
            .filter(SourceTable.inspection_id.in_(inspection_ids))
            .order_by(SourceTable.sheet_index.asc(), SourceTable.id.asc())
            .all()
            if inspection_ids
            else []
        )
        columns = (
            db.query(SourceColumn)
            .filter(SourceColumn.source_table_id == quality.source_table_id)
            .order_by(SourceColumn.position.asc(), SourceColumn.id.asc())
            .all()
        )
        mappings = {
            item.source_column_id: item
            for item in db.query(ColumnMapping)
            .filter(ColumnMapping.source_table_id == quality.source_table_id)
            .all()
        }
        clarification_runs = (
            db.query(ClarificationRun)
            .filter(ClarificationRun.source_table_id == quality.source_table_id)
            .order_by(ClarificationRun.run_number.asc(), ClarificationRun.created_at.asc())
            .all()
        )
        clarification_run_ids = [item.id for item in clarification_runs]
        questions = (
            db.query(ClarificationQuestion)
            .filter(ClarificationQuestion.clarification_run_id.in_(clarification_run_ids))
            .order_by(ClarificationQuestion.audience.asc(), ClarificationQuestion.rank.asc())
            .all()
            if clarification_run_ids
            else []
        )
        response_ids = [item.latest_response_id for item in questions if item.latest_response_id]
        responses = {
            item.id: item
            for item in db.query(ClarificationResponse)
            .filter(ClarificationResponse.id.in_(response_ids))
            .all()
        } if response_ids else {}
        readiness = (
            db.query(PredictionReadinessRun)
            .filter(PredictionReadinessRun.id == prediction_readiness_run_id)
            .first()
            if prediction_readiness_run_id
            else None
        )
        capabilities = (
            db.query(PredictionCapabilityReadiness)
            .filter(PredictionCapabilityReadiness.prediction_readiness_run_id == readiness.id)
            .order_by(PredictionCapabilityReadiness.created_at.asc())
            .all()
            if readiness
            else []
        )
        normalized_rows = (
            db.query(NormalizedSourceRow)
            .filter(NormalizedSourceRow.normalization_run_id == quality.normalization_run_id)
            .order_by(NormalizedSourceRow.source_row_number.asc(), NormalizedSourceRow.id.asc())
            .limit(NORMALIZED_ROW_EXPORT_LIMIT)
            .all()
            if quality.normalization_run_id
            else []
        )

        sheets = [
            _summary_sheet(quality, readiness, quantitative_study_id, len(normalized_rows)),
            _source_files_sheet(source_files),
            _tables_sheet(inspections, tables),
            _columns_sheet(columns, mappings),
            _issues_sheet(issues),
            _clarifications_sheet(clarification_runs, questions, responses),
            _readiness_sheet(readiness, capabilities),
            _normalized_rows_sheet(normalized_rows, quality.normalized_row_count + quality.partial_row_count + quality.skipped_row_count + quality.failed_row_count),
            _survey_sheet(survey),
            _provenance_sheet(quality, readiness, quantitative_study_id, source_files),
        ]
        summary = {
            "data_quality_status": quality.overall_status,
            "prediction_readiness_status": readiness.overall_status if readiness else None,
            "quantitative_study_id": quantitative_study_id,
            "source_file_count": len(source_files),
            "source_table_count": len(tables),
            "data_quality_issue_count": len(issues),
            "clarification_question_count": len(questions),
            "capability_count": len(capabilities),
            "normalized_rows_exported": len(normalized_rows),
            "normalized_row_export_limit": NORMALIZED_ROW_EXPORT_LIMIT,
            "sheet_names": [item.name for item in sheets],
        }
        return sheets, summary


def _summary_sheet(quality, readiness, study_id, normalized_exported):
    rows = [
        [Cell("ARVECTUM — DATA REVIEW REPORT", "title")],
        ["Generated at", datetime.now(timezone.utc).isoformat()],
        ["Project ID", quality.project_id],
        ["Import session ID", quality.import_session_id],
        ["Source file ID", quality.source_file_id],
        ["Source table ID", quality.source_table_id],
        ["Data-quality run", quality.id],
        ["Data-quality status", Cell(quality.overall_status, "blocking" if quality.overall_status == "blocked" else "warning" if quality.overall_status == "review_required" else "info")],
        ["Issues: blocking / warning / info", f"{quality.blocking_issue_count} / {quality.warning_issue_count} / {quality.info_issue_count}"],
        ["Prediction-readiness run", readiness.id if readiness else "Not available"],
        ["Prediction-readiness status", readiness.overall_status if readiness else "Not evaluated"],
        ["Quantitative study", study_id or "Not selected"],
        ["Normalized rows exported", normalized_exported],
        ["Important limitation", "This workbook reviews evidence and readiness. It does not fabricate CTR, model accuracy, respondent observations or causal lift."],
    ]
    return SheetSpec("Summary", rows, header_rows=0, column_widths=[34, 95], freeze_rows=1, auto_filter=False)


def _source_files_sheet(source_files):
    rows = [["File ID", "Original filename", "Content type", "Bytes", "SHA-256", "Duplicate of", "Integrity"]]
    for item in source_files:
        path = Path(item.storage_path)
        integrity = "missing"
        if path.is_file():
            integrity = "verified" if _sha256_file(path) == item.sha256 else "checksum mismatch"
        rows.append([item.id, item.original_filename, item.content_type, item.file_size_bytes, item.sha256, item.duplicate_of_file_id, integrity])
    styles = {index: "blocking" for index, row in enumerate(rows, start=1) if index > 1 and row[-1] != "verified"}
    return SheetSpec("Source Files", rows, row_styles=styles, column_widths=[38, 34, 22, 14, 66, 38, 20])


def _tables_sheet(inspections, tables):
    inspection_by_id = {item.id: item for item in inspections}
    rows = [["Inspection ID", "Parser", "Format", "Sheet", "Header row", "Header confidence", "Source rows", "Data rows", "Columns", "Truncated", "Warnings"]]
    for table in tables:
        inspection = inspection_by_id.get(table.inspection_id)
        rows.append([
            table.inspection_id,
            f"{inspection.parser_name} {inspection.parser_version}" if inspection else None,
            inspection.file_format if inspection else None,
            table.sheet_name,
            table.header_row_number,
            table.header_confidence,
            table.source_row_count,
            table.data_row_count,
            table.column_count,
            table.truncated,
            _json_text(json_loads(table.warnings_json)),
        ])
    styles = {index: "warning" for index, row in enumerate(rows, start=1) if index > 1 and row[9]}
    return SheetSpec("Tables", rows, row_styles=styles, column_widths=[38, 28, 14, 26, 12, 16, 12, 12, 10, 12, 70])


def _columns_sheet(columns, mappings):
    rows = [["Position", "Column ID", "Source header", "Normalized header", "Inferred type", "Non-empty", "Samples", "Mapping status", "Target field", "Confidence", "Decision source"]]
    for column in columns:
        mapping = mappings.get(column.id)
        rows.append([
            column.position,
            column.id,
            column.source_header,
            column.normalized_header,
            column.inferred_type,
            column.non_empty_count,
            _json_text(json_loads(column.sample_values_json)),
            mapping.status if mapping else "unmapped",
            mapping.target_field if mapping else None,
            mapping.confidence if mapping else None,
            mapping.decision_source if mapping else None,
        ])
    styles = {index: "warning" for index, row in enumerate(rows, start=1) if index > 1 and row[7] in {"suggested", "unmapped"}}
    return SheetSpec("Columns and Mapping", rows, row_styles=styles, column_widths=[10, 38, 30, 30, 16, 12, 50, 18, 24, 12, 18])


def _issues_sheet(issues):
    rows = [["Severity", "Category", "Code", "Affected", "Message", "Remediation", "Scope", "Source row", "Source column", "Details"]]
    styles = {}
    for item in issues:
        rows.append([
            item.severity,
            item.category,
            item.code,
            item.affected_count,
            item.message,
            item.remediation_hint,
            f"{item.scope_type}:{item.scope_id or ''}",
            item.source_row_id,
            item.source_column_id,
            _json_text(json_loads(item.details_json)),
        ])
        styles[len(rows)] = "blocking" if item.severity == "blocking" else "warning" if item.severity == "warning" else "info"
    return SheetSpec("Data Quality Issues", rows, row_styles=styles, column_widths=[12, 22, 34, 10, 70, 65, 36, 38, 38, 70])


def _clarifications_sheet(runs, questions, responses):
    run_by_id = {item.id: item for item in runs}
    rows = [["Audience", "Run", "Rank", "Priority", "Status", "Question key", "Question", "Why needed", "Answer type", "Latest resolution", "Latest answer", "Issue codes"]]
    styles = {}
    for question in questions:
        run = run_by_id.get(question.clarification_run_id)
        response = responses.get(question.latest_response_id)
        answer = json_loads(response.answer_json) if response else None
        rows.append([
            question.audience,
            run.run_number if run else None,
            question.rank,
            question.priority,
            question.status,
            question.question_key,
            question.question_text,
            question.why_needed,
            question.answer_type,
            response.resolution if response else None,
            _json_text(answer),
            _json_text(json_loads(question.issue_codes_json)),
        ])
        if question.status in {"open", "deferred"}:
            styles[len(rows)] = "warning"
    return SheetSpec("Clarifications", rows, row_styles=styles, column_widths=[12, 8, 8, 12, 16, 32, 75, 65, 18, 18, 50, 45])


def _readiness_sheet(readiness, capabilities):
    rows = [["Capability", "Status", "Mode", "Evidence strength", "User message", "Missing inputs", "Degraded inputs", "Allowed operations", "Prohibited operations"]]
    styles = {}
    for item in capabilities:
        rows.append([
            item.capability_key,
            item.status,
            item.mode,
            item.evidence_strength,
            item.user_message,
            _json_text(json_loads(item.missing_inputs_json)),
            _json_text(json_loads(item.degraded_inputs_json)),
            _json_text(json_loads(item.allowed_operations_json)),
            _json_text(json_loads(item.prohibited_operations_json)),
        ])
        styles[len(rows)] = "blocking" if item.status == "unavailable" else "warning" if item.status == "degraded" else "info"
    if not readiness:
        rows.append(["No prediction-readiness run selected"])
        styles[2] = "warning"
    return SheetSpec("Prediction Readiness", rows, row_styles=styles, column_widths=[30, 14, 34, 18, 85, 55, 55, 65, 70])


def _normalized_rows_sheet(rows, total_count):
    data = [["Source row", "Status", "Issue count", "Campaign ID", "Creative ID", "Platform ID", "Audience ID", "Placement ID", "Observation ID", "Issues", "Custom fields", "Source payload"]]
    styles = {}
    for item in rows:
        data.append([
            item.source_row_number,
            item.status,
            item.issue_count,
            item.campaign_id,
            item.creative_record_id,
            item.platform_id,
            item.audience_segment_id,
            item.placement_id,
            item.performance_observation_id,
            _json_text(json_loads(item.issues_json)),
            _json_text(json_loads(item.custom_fields_json)),
            _json_text(json_loads(item.source_payload_json)),
        ])
        if item.status in {"partial", "skipped", "failed"}:
            styles[len(data)] = "blocking" if item.status == "failed" else "warning"
    if total_count > len(rows):
        data.append([Cell(f"Export limited to {len(rows)} of {total_count} normalized rows", "warning")])
        styles[len(data)] = "warning"
    return SheetSpec("Normalized Rows", data, row_styles=styles, column_widths=[12, 14, 12, 38, 38, 38, 38, 38, 38, 65, 70, 80])


def _survey_sheet(survey):
    rows = [["Study ID", "Creative asset", "Question code", "Metric", "Type", "Responses", "Mean", "Min", "Max", "Distribution"]]
    if survey is None:
        rows.append(["No quantitative study selected"])
        return SheetSpec("Quantitative Survey", rows, row_styles={2: "muted"}, column_widths=[38, 38, 24, 24, 18, 12, 12, 12, 12, 50])
    for question in survey.question_results:
        for creative_id, result in question["by_creative"].items():
            rows.append([
                survey.study.id,
                creative_id,
                question["code"],
                question["metric_key"],
                question["question_type"],
                result.get("response_count", 0),
                result.get("mean"),
                result.get("min"),
                result.get("max"),
                _json_text(result.get("distribution")),
            ])
    rows.append([Cell("Interpretation", "warning"), " | ".join(survey.interpretation_notes)])
    return SheetSpec("Quantitative Survey", rows, row_styles={len(rows): "warning"}, column_widths=[38, 38, 24, 24, 18, 12, 12, 12, 12, 55])


def _provenance_sheet(quality, readiness, study_id, source_files):
    rows = [["Key", "Value"]]
    values = {
        "generator_name": GENERATOR_NAME,
        "generator_version": GENERATOR_VERSION,
        "data_quality_run_id": quality.id,
        "data_quality_input_fingerprint": quality.input_fingerprint,
        "normalization_run_id": quality.normalization_run_id,
        "prediction_readiness_run_id": readiness.id if readiness else None,
        "prediction_readiness_input_fingerprint": readiness.input_fingerprint if readiness else None,
        "quantitative_study_id": study_id,
        "source_table_id": quality.source_table_id,
        "source_file_id": quality.source_file_id,
        "import_session_id": quality.import_session_id,
        "project_id": quality.project_id,
        "source_file_hashes": {item.id: item.sha256 for item in source_files},
        "limitations": [
            "No fabricated CTR or model accuracy.",
            "Synthetic survey responses are not real-person observations.",
            "Brand-lift proxy is not observed campaign lift.",
            "Causal creative lift requires an explicit study design.",
        ],
    }
    for key, value in values.items():
        rows.append([key, _json_text(value)])
    return SheetSpec("Provenance", rows, column_widths=[42, 110], auto_filter=False)


def _stored_report_valid(model):
    path = Path(model.storage_path)
    return path.is_file() and path.stat().st_size == model.file_size_bytes and _sha256_file(path) == model.sha256


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_text(value):
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def _slug(value):
    return re.sub(r"[^A-Za-z0-9_-]+", "_", str(value)).strip("_") or "project"


def _response(model):
    summary = json_loads(model.summary_json)
    return DataReviewReportResponse(
        id=model.id,
        data_quality_run_id=model.data_quality_run_id,
        prediction_readiness_run_id=model.prediction_readiness_run_id,
        quantitative_study_id=model.quantitative_study_id,
        source_table_id=model.source_table_id,
        source_file_id=model.source_file_id,
        import_session_id=model.import_session_id,
        project_id=model.project_id,
        run_number=model.run_number,
        generator_name=model.generator_name,
        generator_version=model.generator_version,
        input_fingerprint=model.input_fingerprint,
        status=model.status,
        filename=model.filename,
        sha256=model.sha256,
        file_size_bytes=model.file_size_bytes,
        sheet_count=model.sheet_count,
        summary=summary if isinstance(summary, dict) else {},
        error_code=model.error_code,
        error_message=model.error_message,
        created_by_user_id=model.created_by_user_id,
        created_at=model.created_at,
    )
