from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from sqlalchemy import func

from src.modules.clients.models import Client
from src.modules.client_one_page_reports.models import (
    ClientOnePageReportRun,
    ClientOnePageReportStatus,
)
from src.modules.client_one_page_reports.rendering import (
    REPORT_VERSION,
    build_report_bundle,
    compose_report_evidence,
    validate_report_bundle,
)
from src.modules.client_one_page_reports.schemas import (
    ClientOnePageArtifactResponse,
    ClientOnePageReportResponse,
)
from src.modules.data_quality.models import DataQualityIssue, DataQualityRun, DataQualityRunStatus
from src.modules.import_sessions.models import ImportSourceFile, SourceTable
from src.modules.prediction_readiness.models import (
    PredictionCapabilityReadiness,
    PredictionReadinessRun,
    PredictionReadinessRunStatus,
)
from src.modules.projects.models import Project
from src.modules.quantitative_surveys.models import QuantitativeStudy
from src.modules.quantitative_surveys.service import study_results
from src.shared.config.settings import get_settings
from src.shared.db.repository import db_session, json_dumps, json_loads
from src.shared.errors import AppError
from src.shared.security.hardening import ensure_within_root

GENERATOR_NAME = "provisional-client-one-page-generator"
GENERATOR_VERSION = REPORT_VERSION


def generate_client_one_page_report(
    data_quality_run_id: str,
    *,
    prediction_readiness_run_id: str | None = None,
    quantitative_study_id: str | None = None,
    locale: str = "ru",
    force: bool = False,
    created_by_user_id: str | None = None,
) -> ClientOnePageReportResponse:
    if locale not in {"ru", "en"}:
        raise AppError("unsupported_report_locale", "Report locale must be 'ru' or 'en'", 400)

    context = _load_context(
        data_quality_run_id,
        prediction_readiness_run_id=prediction_readiness_run_id,
        quantitative_study_id=quantitative_study_id,
    )
    survey = (
        study_results(quantitative_study_id).model_dump(mode="json")
        if quantitative_study_id
        else None
    )
    fingerprint = _fingerprint(context, locale=locale, survey=survey)

    with db_session() as db:
        existing = (
            db.query(ClientOnePageReportRun)
            .filter(
                ClientOnePageReportRun.data_quality_run_id == context["data_quality"]["id"],
                ClientOnePageReportRun.generator_version == GENERATOR_VERSION,
                ClientOnePageReportRun.input_fingerprint == fingerprint,
                ClientOnePageReportRun.status == ClientOnePageReportStatus.completed,
            )
            .order_by(
                ClientOnePageReportRun.run_number.desc(),
                ClientOnePageReportRun.created_at.desc(),
            )
            .first()
        )
        if existing is not None and not force and _stored_report_valid(existing):
            return _response(existing)
        run_number = (
            db.query(func.max(ClientOnePageReportRun.run_number))
            .filter(ClientOnePageReportRun.data_quality_run_id == context["data_quality"]["id"])
            .scalar()
            or 0
        ) + 1

    report_id = str(uuid4())
    evidence = compose_report_evidence(
        context,
        locale=locale,
        survey=survey,
        generated_at=datetime.now(timezone.utc).isoformat(),
    )
    evidence.update(
        {
            "report_run_id": report_id,
            "run_number": run_number,
            "input_fingerprint": fingerprint,
        }
    )

    settings = get_settings()
    project_slug = _slug(context["project"].get("name") or context["project"]["id"])[:36]
    directory = Path(settings.storage_root) / "client_one_page_reports" / project_slug / report_id
    manifest = build_report_bundle(evidence, directory, basename=f"client_one_page_{locale}")
    errors = validate_report_bundle(directory)
    if errors:
        raise AppError(
            "client_one_page_report_invalid",
            "Generated one-page report failed validation: " + "; ".join(errors),
            500,
        )

    artifacts = [
        {**item, "storage_path": str(directory / item["filename"])}
        for item in manifest["artifacts"]
    ]
    manifest_path = directory / manifest["manifest"]["filename"]
    summary = {
        "verdict": evidence["verdict"]["code"],
        "data_quality_status": evidence["data_quality"]["overall_status"],
        "prediction_readiness_status": evidence["prediction_readiness"]["overall_status"],
        "capability_count": len(evidence["capabilities"]),
        "limitation_count": len(evidence["limitations"]),
        "next_action_count": len(evidence["next_actions"]),
        "survey_evidence_type": evidence["survey"]["evidence_type"],
        "artifact_types": [item["artifact_type"] for item in artifacts],
        "claim_boundary": evidence["claim_boundary"],
    }

    with db_session() as db:
        model = ClientOnePageReportRun(
            id=report_id,
            data_quality_run_id=context["data_quality"]["id"],
            prediction_readiness_run_id=context["prediction_readiness"]["id"],
            quantitative_study_id=quantitative_study_id,
            source_table_id=context["source"]["source_table_id"],
            source_file_id=context["source"]["source_file_id"],
            import_session_id=context["source"]["import_session_id"],
            project_id=context["project"]["id"],
            client_id=context["client"].get("id"),
            run_number=run_number,
            generator_name=GENERATOR_NAME,
            generator_version=GENERATOR_VERSION,
            input_fingerprint=fingerprint,
            status=ClientOnePageReportStatus.completed,
            locale=locale,
            verdict=evidence["verdict"]["code"],
            title=evidence["verdict"]["title"],
            bundle_storage_path=str(directory),
            artifacts_json=json_dumps(artifacts) or "[]",
            manifest_filename=manifest_path.name,
            manifest_storage_path=str(manifest_path),
            manifest_sha256=manifest["manifest"]["sha256"],
            manifest_size_bytes=manifest["manifest"]["size_bytes"],
            slide_count=1,
            summary_json=json_dumps(summary),
            created_by_user_id=created_by_user_id,
        )
        db.add(model)
        db.flush()
        db.refresh(model)
        return _response(model)


def get_client_one_page_report(report_id: str) -> ClientOnePageReportResponse | None:
    with db_session() as db:
        model = db.query(ClientOnePageReportRun).filter(ClientOnePageReportRun.id == report_id).first()
        return _response(model) if model else None


def get_latest_client_one_page_report(data_quality_run_id: str) -> ClientOnePageReportResponse | None:
    with db_session() as db:
        if db.query(DataQualityRun.id).filter(DataQualityRun.id == data_quality_run_id).first() is None:
            raise AppError("data_quality_run_not_found", "Data-quality run not found", 404)
        model = (
            db.query(ClientOnePageReportRun)
            .filter(ClientOnePageReportRun.data_quality_run_id == data_quality_run_id)
            .order_by(
                ClientOnePageReportRun.run_number.desc(),
                ClientOnePageReportRun.created_at.desc(),
            )
            .first()
        )
        return _response(model) if model else None


def _load_context(
    data_quality_run_id: str,
    *,
    prediction_readiness_run_id: str | None,
    quantitative_study_id: str | None,
) -> dict:
    with db_session() as db:
        quality = db.query(DataQualityRun).filter(DataQualityRun.id == data_quality_run_id).first()
        if quality is None:
            raise AppError("data_quality_run_not_found", "Data-quality run not found", 404)
        if quality.status != DataQualityRunStatus.completed:
            raise AppError(
                "data_quality_run_not_completed",
                "Client report requires a completed data-quality run",
                409,
            )

        readiness_query = db.query(PredictionReadinessRun).filter(
            PredictionReadinessRun.data_quality_run_id == quality.id,
            PredictionReadinessRun.project_id == quality.project_id,
            PredictionReadinessRun.status == PredictionReadinessRunStatus.completed,
        )
        if prediction_readiness_run_id:
            readiness = readiness_query.filter(
                PredictionReadinessRun.id == prediction_readiness_run_id
            ).first()
            if readiness is None:
                raise AppError(
                    "prediction_readiness_context_mismatch",
                    "Prediction-readiness run does not belong to the selected data-quality run",
                    409,
                )
        else:
            readiness = readiness_query.order_by(
                PredictionReadinessRun.run_number.desc(),
                PredictionReadinessRun.created_at.desc(),
            ).first()
        if readiness is None:
            raise AppError(
                "prediction_readiness_required",
                "Client report requires a completed prediction-readiness run",
                409,
            )

        project = db.query(Project).filter(Project.id == quality.project_id).first()
        if project is None:
            raise AppError("project_not_found", "Project not found", 404)
        client = db.query(Client).filter(Client.id == project.client_id).first()
        source_file = db.query(ImportSourceFile).filter(
            ImportSourceFile.id == quality.source_file_id
        ).first()
        source_table = db.query(SourceTable).filter(SourceTable.id == quality.source_table_id).first()
        if source_file is None or source_table is None:
            raise AppError(
                "report_source_context_missing",
                "Source file or table required for provenance is missing",
                409,
            )
        _verify_source_file(source_file)

        study = None
        if quantitative_study_id:
            study = db.query(QuantitativeStudy).filter(
                QuantitativeStudy.id == quantitative_study_id,
                QuantitativeStudy.project_id == quality.project_id,
            ).first()
            if study is None:
                raise AppError(
                    "quantitative_study_context_mismatch",
                    "Quantitative study does not belong to the selected project",
                    409,
                )

        issues = db.query(DataQualityIssue).filter(
            DataQualityIssue.data_quality_run_id == quality.id
        ).all()
        capabilities = db.query(PredictionCapabilityReadiness).filter(
            PredictionCapabilityReadiness.prediction_readiness_run_id == readiness.id
        ).all()

        return {
            "client": {
                "id": client.id if client else project.client_id,
                "name": client.name if client else "Client",
                "industry": client.industry if client else None,
            },
            "project": {
                "id": project.id,
                "name": project.name,
                "description": project.description,
            },
            "source": {
                "source_file_id": source_file.id,
                "source_table_id": source_table.id,
                "import_session_id": quality.import_session_id,
                "filename": source_file.original_filename,
                "mime_type": source_file.declared_mime_type,
                "size_bytes": source_file.file_size_bytes,
                "sha256": source_file.sha256,
                "sheet_name": source_table.sheet_name,
            },
            "data_quality": {
                key: getattr(quality, key)
                for key in (
                    "id",
                    "input_fingerprint",
                    "overall_status",
                    "source_file_count",
                    "source_table_count",
                    "source_row_count",
                    "source_column_count",
                    "confirmed_mapping_count",
                    "normalized_row_count",
                    "partial_row_count",
                    "skipped_row_count",
                    "failed_row_count",
                    "creative_record_count",
                    "linked_creative_count",
                    "unlinked_creative_count",
                    "ambiguous_creative_count",
                    "performance_observation_count",
                    "info_issue_count",
                    "warning_issue_count",
                    "blocking_issue_count",
                    "total_issue_count",
                )
            },
            "prediction_readiness": {
                key: getattr(readiness, key)
                for key in (
                    "id",
                    "input_fingerprint",
                    "overall_status",
                    "capability_count",
                    "ready_count",
                    "degraded_count",
                    "unavailable_count",
                    "not_applicable_count",
                    "unresolved_client_question_count",
                    "unresolved_analyst_question_count",
                )
            },
            "issues": [
                {
                    "id": item.id,
                    "category": item.category,
                    "code": item.code,
                    "severity": item.severity,
                    "affected_count": item.affected_count,
                    "message": item.message,
                    "remediation_hint": item.remediation_hint,
                    "scope_type": item.scope_type,
                    "scope_id": item.scope_id,
                }
                for item in issues
            ],
            "capabilities": [
                {
                    "id": item.id,
                    "capability_key": item.capability_key,
                    "title": item.title,
                    "status": item.status,
                    "mode": item.mode,
                    "evidence_strength": item.evidence_strength,
                    "user_message": item.user_message,
                    "reasons": _safe_list(json_loads(item.reasons_json)),
                    "missing_inputs": _safe_list(json_loads(item.missing_inputs_json)),
                    "degraded_inputs": _safe_list(json_loads(item.degraded_inputs_json)),
                    "allowed_operations": _safe_list(json_loads(item.allowed_operations_json)),
                    "prohibited_operations": _safe_list(json_loads(item.prohibited_operations_json)),
                }
                for item in capabilities
            ],
            "study": (
                {
                    "id": study.id,
                    "status": study.status,
                    "response_count": study.response_count,
                    "target_response_count": study.target_response_count,
                }
                if study
                else None
            ),
            "provenance": {
                "data_quality_run_id": quality.id,
                "data_quality_input_fingerprint": quality.input_fingerprint,
                "normalization_run_id": quality.normalization_run_id,
                "prediction_readiness_run_id": readiness.id,
                "prediction_readiness_input_fingerprint": readiness.input_fingerprint,
                "quantitative_study_id": study.id if study else None,
                "source_file_id": source_file.id,
                "source_file_sha256": source_file.sha256,
                "source_table_id": source_table.id,
                "import_session_id": quality.import_session_id,
            },
        }


def _verify_source_file(source_file: ImportSourceFile) -> None:
    try:
        path = ensure_within_root(source_file.storage_path, get_settings().storage_root)
    except ValueError as exc:
        raise AppError(
            "source_file_path_escape",
            "Immutable source path is outside the configured storage root",
            409,
        ) from exc
    if not path.is_file():
        raise AppError("source_file_missing", "Immutable source file is missing", 409)
    if _sha256_file(path) != source_file.sha256:
        raise AppError(
            "source_file_integrity_failed",
            "Immutable source file failed SHA-256 verification",
            409,
        )


def _fingerprint(context: dict, *, locale: str, survey: dict | None) -> str:
    payload = {
        "generator_version": GENERATOR_VERSION,
        "locale": locale,
        "client": context["client"],
        "project": context["project"],
        "source": context["source"],
        "data_quality": context["data_quality"],
        "prediction_readiness": context["prediction_readiness"],
        "issues": sorted(context["issues"], key=lambda item: item["id"]),
        "capabilities": sorted(
            context["capabilities"], key=lambda item: item["capability_key"]
        ),
        "study": context["study"],
        "survey_evidence": survey,
        "provenance": context["provenance"],
    }
    return hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _stored_report_valid(model: ClientOnePageReportRun) -> bool:
    try:
        manifest_path = ensure_within_root(
            model.manifest_storage_path, get_settings().storage_root
        )
        bundle_path = ensure_within_root(
            model.bundle_storage_path, get_settings().storage_root
        )
    except ValueError:
        return False
    if not manifest_path.is_file() or _sha256_file(manifest_path) != model.manifest_sha256:
        return False
    if validate_report_bundle(bundle_path):
        return False
    for item in _artifact_dicts(model):
        try:
            path = ensure_within_root(
                item.get("storage_path", ""), get_settings().storage_root
            )
        except ValueError:
            return False
        if not path.is_file() or _sha256_file(path) != item.get("sha256"):
            return False
    return True


def _artifact_dicts(model: ClientOnePageReportRun) -> list[dict]:
    value = json_loads(model.artifacts_json)
    return value if isinstance(value, list) else []


def _response(model: ClientOnePageReportRun) -> ClientOnePageReportResponse:
    artifacts = [
        ClientOnePageArtifactResponse(
            artifact_type=item["artifact_type"],
            filename=item["filename"],
            media_type=item["media_type"],
            sha256=item["sha256"],
            size_bytes=int(item["size_bytes"]),
        )
        for item in _artifact_dicts(model)
    ]
    summary = json_loads(model.summary_json)
    return ClientOnePageReportResponse(
        id=model.id,
        data_quality_run_id=model.data_quality_run_id,
        prediction_readiness_run_id=model.prediction_readiness_run_id,
        quantitative_study_id=model.quantitative_study_id,
        source_table_id=model.source_table_id,
        source_file_id=model.source_file_id,
        import_session_id=model.import_session_id,
        project_id=model.project_id,
        client_id=model.client_id,
        run_number=model.run_number,
        generator_name=model.generator_name,
        generator_version=model.generator_version,
        input_fingerprint=model.input_fingerprint,
        status=model.status,
        locale=model.locale,
        verdict=model.verdict,
        title=model.title,
        slide_count=model.slide_count,
        artifacts=artifacts,
        manifest_filename=model.manifest_filename,
        manifest_sha256=model.manifest_sha256,
        manifest_size_bytes=model.manifest_size_bytes,
        summary=summary if isinstance(summary, dict) else {},
        created_by_user_id=model.created_by_user_id,
        created_at=model.created_at,
    )


def _safe_list(value) -> list:
    if isinstance(value, list):
        return value
    if value in (None, {}, ""):
        return []
    return [value]


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _slug(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_-]+", "-", value or "report").strip("-")
    return cleaned or "report"
