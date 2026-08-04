from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func

from src.modules.data_quality.models import DataQualityRun
from src.modules.import_sessions.models import ImportSession, ImportSourceFile
from src.modules.pilot_intake.models import PilotCase, PilotCaseDecision
from src.modules.pilot_intake.schemas import (
    CreatePilotDecisionRequest,
    PilotCaseDecisionResponse,
    PilotCaseResponse,
    PilotDataQualityRunEvidence,
    PilotDataQualitySnapshot,
    PilotIntakeDataQualitySummary,
    PilotMetricEvidence,
    PilotSourceFileEvidence,
    RegisterPilotCaseRequest,
)
from src.modules.projects.models import Project
from src.shared.db.repository import db_session
from src.shared.errors import AppError

_SCHEMA_VERSION = "cta-pilot-prep-001/v1"
_WRITER_ROLES = {"admin", "manager", "analyst"}
_STATE_KEYS = ("included", "excluded", "deferred", "needs_clarification")
_DQ_KEYS = ("passed", "review_required", "blocked", "unavailable")
_LINKAGE_KEYS = ("exact", "probable", "uncertain", "one_to_many", "missing", "rejected")


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _json_object(value: str) -> dict[str, Any]:
    loaded = json.loads(value)
    return loaded if isinstance(loaded, dict) else {}


def _json_list(value: str) -> list[Any]:
    loaded = json.loads(value)
    return loaded if isinstance(loaded, list) else []


def _require_writer(user: dict | None) -> None:
    if (user or {}).get("role") not in _WRITER_ROLES:
        raise AppError("write_permission_required", "Write permission required", 403)


def _ensure_project(db, project_id: str) -> Project:
    project = db.query(Project).filter(Project.id == project_id).first()
    if project is None:
        raise AppError("project_not_found", "Project not found", 404)
    return project


def _get_case_row(db, project_id: str, case_id: str) -> PilotCase:
    row = (
        db.query(PilotCase)
        .filter(PilotCase.project_id == project_id, PilotCase.id == case_id)
        .first()
    )
    if row is None:
        raise AppError("pilot_case_not_found", "Pilot case not found", 404)
    return row


def _latest_dq_runs(rows: list[DataQualityRun]) -> list[DataQualityRun]:
    latest: dict[str, DataQualityRun] = {}
    for row in sorted(
        rows,
        key=lambda item: (
            item.source_table_id,
            item.created_at.isoformat() if item.created_at else "",
            item.id,
        ),
        reverse=True,
    ):
        latest.setdefault(row.source_table_id, row)
    return sorted(latest.values(), key=lambda item: (item.source_table_id, item.id))


def _load_source_evidence(
    db,
    project_id: str,
    body: RegisterPilotCaseRequest,
) -> tuple[ImportSession, list[ImportSourceFile], list[DataQualityRun]]:
    import_session = (
        db.query(ImportSession)
        .filter(
            ImportSession.id == body.import_session_id,
            ImportSession.project_id == project_id,
        )
        .first()
    )
    if import_session is None:
        raise AppError("import_session_not_found", "Import session not found", 404)
    if import_session.status != "completed":
        raise AppError(
            "import_session_not_completed",
            "Controlled-pilot cases require a completed immutable import session",
            409,
        )

    files = (
        db.query(ImportSourceFile)
        .filter(
            ImportSourceFile.import_session_id == import_session.id,
            ImportSourceFile.project_id == project_id,
        )
        .order_by(ImportSourceFile.original_filename.asc(), ImportSourceFile.id.asc())
        .all()
    )
    if not files:
        raise AppError(
            "import_source_files_missing",
            "Controlled-pilot cases require at least one immutable source hash",
            409,
        )

    query = db.query(DataQualityRun).filter(
        DataQualityRun.project_id == project_id,
        DataQualityRun.import_session_id == import_session.id,
        DataQualityRun.status == "completed",
    )
    if body.data_quality_run_ids:
        requested_ids = sorted(set(body.data_quality_run_ids))
        rows = query.filter(DataQualityRun.id.in_(requested_ids)).all()
        if {row.id for row in rows} != set(requested_ids):
            raise AppError(
                "data_quality_evidence_not_found",
                "Data quality evidence not found for project import session",
                404,
            )
        dq_runs = sorted(rows, key=lambda item: (item.source_table_id, item.id))
    else:
        dq_runs = _latest_dq_runs(query.all())
    return import_session, files, dq_runs


def _dq_snapshot(rows: list[DataQualityRun]) -> dict[str, Any]:
    if not rows:
        return {
            "overall_status": "unavailable",
            "run_count": 0,
            "confirmed_mapping_count": 0,
            "suggested_mapping_count": 0,
            "rejected_mapping_count": 0,
            "unmapped_mapping_count": 0,
            "warning_issue_count": 0,
            "blocking_issue_count": 0,
            "total_issue_count": 0,
            "runs": [],
        }
    rank = {"passed": 0, "review_required": 1, "blocked": 2}
    overall = max((row.overall_status for row in rows), key=lambda value: rank.get(value, 2))
    runs = [
        {
            "run_id": row.id,
            "source_table_id": row.source_table_id,
            "input_fingerprint": row.input_fingerprint,
            "overall_status": row.overall_status,
            "confirmed_mapping_count": row.confirmed_mapping_count,
            "suggested_mapping_count": row.suggested_mapping_count,
            "rejected_mapping_count": row.rejected_mapping_count,
            "unmapped_mapping_count": row.unmapped_mapping_count,
            "warning_issue_count": row.warning_issue_count,
            "blocking_issue_count": row.blocking_issue_count,
            "total_issue_count": row.total_issue_count,
        }
        for row in rows
    ]
    return {
        "overall_status": overall,
        "run_count": len(rows),
        "confirmed_mapping_count": sum(row.confirmed_mapping_count for row in rows),
        "suggested_mapping_count": sum(row.suggested_mapping_count for row in rows),
        "rejected_mapping_count": sum(row.rejected_mapping_count for row in rows),
        "unmapped_mapping_count": sum(row.unmapped_mapping_count for row in rows),
        "warning_issue_count": sum(row.warning_issue_count for row in rows),
        "blocking_issue_count": sum(row.blocking_issue_count for row in rows),
        "total_issue_count": sum(row.total_issue_count for row in rows),
        "runs": runs,
    }


def _effective_linkage(body: RegisterPilotCaseRequest) -> str:
    requested = body.requested_linkage_confidence or body.source_linkage_confidence
    if requested == "exact" and body.source_linkage_confidence != "exact":
        raise AppError(
            "linkage_promotion_forbidden",
            "Non-exact linkage evidence cannot be promoted to exact",
            409,
        )
    return requested


def _case_payload(
    project_id: str,
    body: RegisterPilotCaseRequest,
    files: list[ImportSourceFile],
    dq_snapshot: dict[str, Any],
    linkage_confidence: str,
) -> dict[str, Any]:
    source_files = [
        {
            "source_file_id": row.id,
            "original_filename": row.original_filename,
            "file_size_bytes": row.file_size_bytes,
            "sha256": row.sha256,
        }
        for row in files
    ]
    metrics = body.metrics.model_dump(mode="json")
    asset_references = sorted(set(body.asset_references))
    return {
        "schema_version": _SCHEMA_VERSION,
        "project_id": project_id,
        "case_key": body.case_key,
        "import_session_id": body.import_session_id,
        "source_files": source_files,
        "provenance": body.provenance,
        "source_linkage_confidence": body.source_linkage_confidence,
        "linkage_confidence": linkage_confidence,
        "asset_references": asset_references,
        "metrics": metrics,
        "data_quality": dq_snapshot,
        "counts_reconstructed_from_rates": False,
    }


def register_case(
    project_id: str,
    body: RegisterPilotCaseRequest,
    *,
    user: dict | None,
) -> PilotCaseResponse:
    _require_writer(user)
    with db_session() as db:
        _ensure_project(db, project_id)
        existing = (
            db.query(PilotCase)
            .filter(PilotCase.project_id == project_id, PilotCase.case_key == body.case_key)
            .first()
        )
        if existing is not None:
            raise AppError("pilot_case_exists", "Pilot case already exists", 409)

        _, files, dq_runs = _load_source_evidence(db, project_id, body)
        linkage_confidence = _effective_linkage(body)
        snapshot = _dq_snapshot(dq_runs)
        canonical_payload = _case_payload(
            project_id,
            body,
            files,
            snapshot,
            linkage_confidence,
        )
        package_sha256 = hashlib.sha256(
            _canonical_json(canonical_payload).encode("utf-8")
        ).hexdigest()
        now = datetime.now(timezone.utc)
        actor_id = (user or {}).get("user_id")
        row = PilotCase(
            project_id=project_id,
            case_key=body.case_key,
            import_session_id=body.import_session_id,
            state=body.initial_state,
            source_package_sha256=package_sha256,
            source_files_json=_canonical_json(canonical_payload["source_files"]),
            provenance_json=_canonical_json(body.provenance),
            source_linkage_confidence=body.source_linkage_confidence,
            linkage_confidence=linkage_confidence,
            asset_references_json=_canonical_json(canonical_payload["asset_references"]),
            asset_count=len(canonical_payload["asset_references"]),
            reported_impressions=body.metrics.impressions,
            reported_clicks=body.metrics.clicks,
            reported_rate=body.metrics.rate,
            data_quality_snapshot_json=_canonical_json(snapshot),
            data_quality_run_count=snapshot["run_count"],
            overall_data_quality_status=snapshot["overall_status"],
            warning_issue_count=snapshot["warning_issue_count"],
            blocking_issue_count=snapshot["blocking_issue_count"],
            created_by_user_id=actor_id,
            updated_by_user_id=actor_id,
            created_at=now,
            updated_at=now,
        )
        db.add(row)
        db.flush()
        decision = PilotCaseDecision(
            project_id=project_id,
            pilot_case_id=row.id,
            case_key=row.case_key,
            sequence=1,
            from_state=None,
            to_state=row.state,
            reason=body.decision_reason,
            decided_by_user_id=actor_id,
            created_at=now,
        )
        db.add(decision)
        db.flush()
        db.refresh(row)
        return _case_response(row)


def list_cases(project_id: str) -> list[PilotCaseResponse]:
    with db_session() as db:
        _ensure_project(db, project_id)
        rows = (
            db.query(PilotCase)
            .filter(PilotCase.project_id == project_id)
            .order_by(PilotCase.case_key.asc(), PilotCase.id.asc())
            .all()
        )
        return [_case_response(row) for row in rows]


def get_case(project_id: str, case_id: str) -> PilotCaseResponse:
    with db_session() as db:
        _ensure_project(db, project_id)
        return _case_response(_get_case_row(db, project_id, case_id))


def create_decision(
    project_id: str,
    case_id: str,
    body: CreatePilotDecisionRequest,
    *,
    user: dict | None,
) -> PilotCaseDecisionResponse:
    _require_writer(user)
    with db_session() as db:
        _ensure_project(db, project_id)
        row = _get_case_row(db, project_id, case_id)
        next_sequence = (
            db.query(func.max(PilotCaseDecision.sequence))
            .filter(
                PilotCaseDecision.project_id == project_id,
                PilotCaseDecision.pilot_case_id == row.id,
            )
            .scalar()
            or 0
        ) + 1
        actor_id = (user or {}).get("user_id")
        now = datetime.now(timezone.utc)
        decision = PilotCaseDecision(
            project_id=project_id,
            pilot_case_id=row.id,
            case_key=row.case_key,
            sequence=next_sequence,
            from_state=row.state,
            to_state=body.state,
            reason=body.reason,
            decided_by_user_id=actor_id,
            created_at=now,
        )
        db.add(decision)
        row._decision_append_authorized = True
        row.state = body.state
        row.updated_by_user_id = actor_id
        row.updated_at = now
        db.flush()
        db.refresh(decision)
        return _decision_response(decision)


def list_decisions(project_id: str, case_id: str) -> list[PilotCaseDecisionResponse]:
    with db_session() as db:
        _ensure_project(db, project_id)
        row = _get_case_row(db, project_id, case_id)
        decisions = (
            db.query(PilotCaseDecision)
            .filter(
                PilotCaseDecision.project_id == project_id,
                PilotCaseDecision.pilot_case_id == row.id,
            )
            .order_by(PilotCaseDecision.sequence.asc(), PilotCaseDecision.id.asc())
            .all()
        )
        return [_decision_response(item) for item in decisions]


def compose_data_quality_summary(project_id: str) -> PilotIntakeDataQualitySummary:
    cases = list_cases(project_id)
    state_counts = {key: 0 for key in _STATE_KEYS}
    dq_counts = {key: 0 for key in _DQ_KEYS}
    linkage_counts = {key: 0 for key in _LINKAGE_KEYS}
    source_linkage_counts = {key: 0 for key in _LINKAGE_KEYS}
    source_hashes: set[str] = set()

    exact_counts_case_count = 0
    partial_counts_case_count = 0
    rate_only_case_count = 0
    no_metric_case_count = 0
    multi_asset_case_count = 0
    impressions_total = 0
    clicks_total = 0
    confirmed_mapping_count = 0
    suggested_mapping_count = 0
    rejected_mapping_count = 0
    unmapped_mapping_count = 0
    warning_issue_count = 0
    blocking_issue_count = 0
    promotion_count = 0

    for case in cases:
        state_counts[case.state] += 1
        dq_counts[case.data_quality.overall_status] += 1
        linkage_counts[case.linkage_confidence] += 1
        source_linkage_counts[case.source_linkage_confidence] += 1
        source_hashes.update(item.sha256 for item in case.source_files)
        confirmed_mapping_count += sum(
            item.confirmed_mapping_count for item in case.data_quality.runs
        )
        suggested_mapping_count += sum(
            item.suggested_mapping_count for item in case.data_quality.runs
        )
        rejected_mapping_count += sum(
            item.rejected_mapping_count for item in case.data_quality.runs
        )
        unmapped_mapping_count += sum(
            item.unmapped_mapping_count for item in case.data_quality.runs
        )
        warning_issue_count += case.data_quality.warning_issue_count
        blocking_issue_count += case.data_quality.blocking_issue_count
        if case.asset_count > 1:
            multi_asset_case_count += 1
        if (
            case.source_linkage_confidence != "exact"
            and case.linkage_confidence == "exact"
        ):
            promotion_count += 1

        impressions = case.metrics.impressions
        clicks = case.metrics.clicks
        rate = case.metrics.rate
        if impressions is not None and clicks is not None:
            exact_counts_case_count += 1
        elif impressions is not None or clicks is not None:
            partial_counts_case_count += 1
        elif rate is not None:
            rate_only_case_count += 1
        else:
            no_metric_case_count += 1
        if impressions is not None:
            impressions_total += impressions
        if clicks is not None:
            clicks_total += clicks

    return PilotIntakeDataQualitySummary(
        schema_version=_SCHEMA_VERSION,
        project_id=project_id,
        total_cases=len(cases),
        state_counts=state_counts,
        data_quality_status_counts=dq_counts,
        linkage_confidence_counts=linkage_counts,
        source_linkage_confidence_counts=source_linkage_counts,
        source_file_count=sum(len(case.source_files) for case in cases),
        unique_source_hash_count=len(source_hashes),
        exact_counts_case_count=exact_counts_case_count,
        partial_counts_case_count=partial_counts_case_count,
        rate_only_case_count=rate_only_case_count,
        no_metric_case_count=no_metric_case_count,
        multi_asset_case_count=multi_asset_case_count,
        reported_impressions_total=impressions_total,
        reported_clicks_total=clicks_total,
        confirmed_mapping_count=confirmed_mapping_count,
        suggested_mapping_count=suggested_mapping_count,
        rejected_mapping_count=rejected_mapping_count,
        unmapped_mapping_count=unmapped_mapping_count,
        warning_issue_count=warning_issue_count,
        blocking_issue_count=blocking_issue_count,
        non_exact_to_exact_promotion_count=promotion_count,
        counts_reconstructed_from_rates=False,
        claim_boundary={
            "client_data_required": False,
            "real_controlled_pilot_completed": False,
            "cta_pilot_002_completed": False,
            "probable_or_uncertain_promoted_to_exact": False,
            "counts_reconstructed_from_rounded_rates": False,
            "causal_interpretation_claimed": False,
            "numeric_uplift_prediction_claimed": False,
        },
    )


def export_payload(project_id: str) -> dict[str, Any]:
    cases = list_cases(project_id)
    decisions: list[PilotCaseDecisionResponse] = []
    for case in cases:
        decisions.extend(list_decisions(project_id, case.id))
    decisions.sort(key=lambda item: (item.case_key, item.sequence, item.id))
    return {
        "schema_version": _SCHEMA_VERSION,
        "project_id": project_id,
        "cases": [case.model_dump(mode="json") for case in cases],
        "decision_history": [item.model_dump(mode="json") for item in decisions],
        "data_quality_summary": compose_data_quality_summary(project_id).model_dump(
            mode="json"
        ),
    }


def export_json_bytes(project_id: str) -> bytes:
    return (_canonical_json(export_payload(project_id)) + "\n").encode("utf-8")


def _case_response(row: PilotCase) -> PilotCaseResponse:
    snapshot = _json_object(row.data_quality_snapshot_json)
    return PilotCaseResponse(
        id=row.id,
        project_id=row.project_id,
        case_key=row.case_key,
        import_session_id=row.import_session_id,
        state=row.state,
        source_package_sha256=row.source_package_sha256,
        source_files=[
            PilotSourceFileEvidence.model_validate(item)
            for item in _json_list(row.source_files_json)
        ],
        provenance=_json_object(row.provenance_json),
        source_linkage_confidence=row.source_linkage_confidence,
        linkage_confidence=row.linkage_confidence,
        asset_references=[str(item) for item in _json_list(row.asset_references_json)],
        asset_count=row.asset_count,
        metrics=PilotMetricEvidence(
            impressions=row.reported_impressions,
            clicks=row.reported_clicks,
            rate=row.reported_rate,
        ),
        data_quality=PilotDataQualitySnapshot(
            overall_status=snapshot.get("overall_status", "unavailable"),
            run_count=int(snapshot.get("run_count", 0)),
            confirmed_mapping_count=int(snapshot.get("confirmed_mapping_count", 0)),
            suggested_mapping_count=int(snapshot.get("suggested_mapping_count", 0)),
            rejected_mapping_count=int(snapshot.get("rejected_mapping_count", 0)),
            unmapped_mapping_count=int(snapshot.get("unmapped_mapping_count", 0)),
            warning_issue_count=int(snapshot.get("warning_issue_count", 0)),
            blocking_issue_count=int(snapshot.get("blocking_issue_count", 0)),
            total_issue_count=int(snapshot.get("total_issue_count", 0)),
            runs=[
                PilotDataQualityRunEvidence.model_validate(item)
                for item in snapshot.get("runs", [])
            ],
        ),
        created_by_user_id=row.created_by_user_id,
        updated_by_user_id=row.updated_by_user_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _decision_response(row: PilotCaseDecision) -> PilotCaseDecisionResponse:
    return PilotCaseDecisionResponse(
        id=row.id,
        project_id=row.project_id,
        pilot_case_id=row.pilot_case_id,
        case_key=row.case_key,
        sequence=row.sequence,
        from_state=row.from_state,
        to_state=row.to_state,
        reason=row.reason,
        decided_by_user_id=row.decided_by_user_id,
        created_at=row.created_at,
    )
