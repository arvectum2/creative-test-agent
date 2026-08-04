from __future__ import annotations

import statistics
from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any


from src.modules.audit_log.service import write_audit_event
from src.modules.calibration_dashboard.metric_builder import build_metrics
from src.modules.calibration_dashboard.models import (
    CalibrationCaseEvidence,
    CalibrationWorkflowMeasurement,
)
from src.modules.calibration_dashboard.schemas import (
    CalibrationCaseResponse,
    CalibrationCaseRow,
    CalibrationDashboardResponse,
    CalibrationMetric,
    CreateWorkflowMeasurementRequest,
    EvidenceFilter,
    UpsertCalibrationCaseRequest,
    WorkflowMeasurementResponse,
)
from src.modules.campaign_evidence.service import get_campaign_evidence_workspace
from src.modules.finding_reviews.service import (
    list_project_adjudications,
    list_project_disagreements,
    list_project_reviews,
    list_reviewable_findings,
)
from src.shared.db.repository import db_session
from src.shared.errors import AppError

SCHEMA_VERSION = "calibration-quality-dashboard/1.0"
DEFINITIONS_VERSION = "cta-cal-003-metrics/1.0"
EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)
CLAIM_BOUNDARY = {
    "validated_model_accuracy_claimed": False,
    "causal_interpretation_allowed": False,
    "numeric_uplift_prediction_generated": False,
    "automatic_threshold_tuning_performed": False,
    "automatic_model_selection_performed": False,
    "missing_evidence_inferred": False,
    "real_and_synthetic_evidence_merged": False,
}


def _case_response(row: CalibrationCaseEvidence) -> CalibrationCaseResponse:
    return CalibrationCaseResponse(
        id=row.id,
        project_id=row.project_id,
        case_id=row.case_id,
        evidence_class=row.evidence_class,
        inclusion_status=row.inclusion_status,
        source_reference=row.source_reference,
        notes=row.notes,
        updated_by_user_id=row.updated_by_user_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _measurement_response(row: CalibrationWorkflowMeasurement) -> WorkflowMeasurementResponse:
    return WorkflowMeasurementResponse(
        id=row.id,
        project_id=row.project_id,
        case_id=row.case_id,
        stage=row.stage,
        status=row.status,
        wall_clock_seconds=row.wall_clock_seconds,
        operator_touch_seconds=row.operator_touch_seconds,
        manual_action_count=row.manual_action_count,
        report_version=row.report_version,
        notes=row.notes,
        created_by_user_id=row.created_by_user_id,
        created_at=row.created_at,
    )


def list_case_evidence(project_id: str) -> list[CalibrationCaseResponse]:
    with db_session() as db:
        rows = (
            db.query(CalibrationCaseEvidence)
            .filter(CalibrationCaseEvidence.project_id == project_id)
            .order_by(CalibrationCaseEvidence.case_id.asc())
            .all()
        )
        return [_case_response(row) for row in rows]


def upsert_case_evidence(
    project_id: str,
    case_id: str,
    body: UpsertCalibrationCaseRequest,
    *,
    user: dict[str, Any],
) -> CalibrationCaseResponse:
    case_id = case_id.strip()
    if not case_id:
        raise AppError("calibration_case_id_required", "Case ID is required", 422)
    with db_session() as db:
        row = (
            db.query(CalibrationCaseEvidence)
            .filter(
                CalibrationCaseEvidence.project_id == project_id,
                CalibrationCaseEvidence.case_id == case_id,
            )
            .one_or_none()
        )
        now = datetime.now(timezone.utc)
        if row is None:
            row = CalibrationCaseEvidence(
                project_id=project_id,
                case_id=case_id,
                evidence_class=body.evidence_class,
                inclusion_status=body.inclusion_status,
                source_reference=body.source_reference,
                notes=body.notes,
                updated_by_user_id=user.get("user_id"),
                created_at=now,
                updated_at=now,
            )
            db.add(row)
            event_type = "calibration_case_created"
        else:
            row.evidence_class = body.evidence_class
            row.inclusion_status = body.inclusion_status
            row.source_reference = body.source_reference
            row.notes = body.notes
            row.updated_by_user_id = user.get("user_id")
            row.updated_at = now
            event_type = "calibration_case_updated"
        db.flush()
        db.refresh(row)
        response = _case_response(row)
    write_audit_event(
        event_type,
        "calibration_case_evidence",
        response.id,
        {
            "project_id": project_id,
            "case_id": case_id,
            "evidence_class": body.evidence_class,
            "inclusion_status": body.inclusion_status,
        },
    )
    return response


def create_workflow_measurement(
    project_id: str,
    body: CreateWorkflowMeasurementRequest,
    *,
    user: dict[str, Any],
) -> WorkflowMeasurementResponse:
    known_cases = {item.case_id for item in list_case_evidence(project_id)}
    if body.case_id not in known_cases:
        raise AppError(
            "calibration_case_not_classified",
            "Classify the case before recording workflow measurements",
            409,
        )
    with db_session() as db:
        row = CalibrationWorkflowMeasurement(
            project_id=project_id,
            case_id=body.case_id,
            stage=body.stage,
            status=body.status,
            wall_clock_seconds=body.wall_clock_seconds,
            operator_touch_seconds=body.operator_touch_seconds,
            manual_action_count=body.manual_action_count,
            report_version=body.report_version,
            notes=body.notes,
            created_by_user_id=user.get("user_id"),
        )
        db.add(row)
        db.flush()
        db.refresh(row)
        response = _measurement_response(row)
    write_audit_event(
        "calibration_workflow_measurement_created",
        "calibration_workflow_measurement",
        response.id,
        {
            "project_id": project_id,
            "case_id": body.case_id,
            "stage": body.stage,
            "status": body.status,
            "wall_clock_seconds": body.wall_clock_seconds,
            "operator_touch_seconds": body.operator_touch_seconds,
            "manual_action_count": body.manual_action_count,
        },
    )
    return response


def list_workflow_measurements(project_id: str) -> list[WorkflowMeasurementResponse]:
    with db_session() as db:
        rows = (
            db.query(CalibrationWorkflowMeasurement)
            .filter(CalibrationWorkflowMeasurement.project_id == project_id)
            .order_by(
                CalibrationWorkflowMeasurement.created_at.asc(),
                CalibrationWorkflowMeasurement.id.asc(),
            )
            .all()
        )
        return [_measurement_response(row) for row in rows]


def _workspace(project_id: str) -> dict[str, Any]:
    try:
        value = get_campaign_evidence_workspace(project_id)
    except AppError:
        return {
            "project_id": project_id,
            "source_fingerprint": None,
            "normalization_run_id": None,
            "campaigns": [],
        }
    return value.model_dump(mode="json") if hasattr(value, "model_dump") else dict(value)


def _median(values: list[float | int]) -> float | None:
    return float(statistics.median(values)) if values else None


def _ratio(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 6) if denominator else None


def _metric(
    *,
    key: str,
    label: str,
    domain: str,
    unit: str,
    value: float | int | None,
    numerator: float | int | None,
    denominator: float | int | None,
    definition: str,
    interpretation: str,
    limitations: list[str],
    coverage: float | None = None,
) -> CalibrationMetric:
    if value is None:
        status = "not_measured"
    elif coverage is not None and coverage < 1:
        status = "partial"
    else:
        status = "available"
    return CalibrationMetric(
        key=key,
        label=label,
        domain=domain,
        unit=unit,
        value=value,
        numerator=numerator,
        denominator=denominator,
        coverage=coverage,
        evidence_status=status,
        definition=definition,
        interpretation=interpretation,
        limitations=limitations,
    )


def compose_dashboard(
    project_id: str,
    *,
    evidence_filter: EvidenceFilter = "all",
) -> CalibrationDashboardResponse:
    workspace = _workspace(project_id)
    campaigns = workspace.get("campaigns") or []
    campaign_by_case = {
        str(campaign.get("case_id") or campaign.get("campaign_id")): campaign
        for campaign in campaigns
    }
    campaign_id_by_case = {
        str(campaign.get("case_id") or campaign.get("campaign_id")): str(
            campaign.get("campaign_id") or ""
        )
        for campaign in campaigns
    }

    classifications = {item.case_id: item for item in list_case_evidence(project_id)}
    reviews = list_project_reviews(project_id)
    adjudications = list_project_adjudications(project_id)
    reviewable_findings = list_reviewable_findings(project_id) if campaigns else []
    disagreements = list_project_disagreements(project_id) if campaigns else []
    workflow = list_workflow_measurements(project_id)

    all_case_ids = set(campaign_by_case) | set(classifications)
    all_case_ids |= {
        str(item.case_id or item.campaign_id or "")
        for item in reviews
        if item.case_id or item.campaign_id
    }
    all_case_ids |= {
        str(item.case_id or item.campaign_id or "")
        for item in reviewable_findings
        if item.case_id or item.campaign_id
    }
    all_case_ids |= {item.case_id for item in workflow}
    all_case_ids.discard("")

    def case_class(case_id: str) -> str:
        return (
            classifications[case_id].evidence_class
            if case_id in classifications
            else "unclassified"
        )

    def inclusion(case_id: str) -> str:
        return (
            classifications[case_id].inclusion_status
            if case_id in classifications
            else "included"
        )

    selected_cases = {
        case_id
        for case_id in all_case_ids
        if inclusion(case_id) == "included"
        and (evidence_filter == "all" or case_class(case_id) == evidence_filter)
    }

    review_case = {
        item.finding_id: str(item.case_id or item.campaign_id or "")
        for item in reviewable_findings
    }
    selected_disagreements = [
        item
        for item in disagreements
        if review_case.get(item.finding_id, "") in selected_cases
    ]

    resolved: list[dict[str, Any]] = []
    review_status_counts: Counter[str] = Counter()
    for state in selected_disagreements:
        review_status_counts[state.status] += 1
        assessment: dict[str, Any] | None = None
        if state.status == "adjudicated" and state.latest_adjudication:
            item = state.latest_adjudication
            assessment = {
                "finding_id": state.finding_id,
                "case_id": review_case.get(state.finding_id, ""),
                "decision": item.decision,
                "correctness": item.correctness,
                "actionability": item.actionability,
                "traceability": item.traceability,
            }
        elif state.status == "agreement" and state.latest_reviews:
            assessment = {
                "finding_id": state.finding_id,
                "case_id": review_case.get(state.finding_id, ""),
                "decision": state.latest_reviews[0].decision,
                "correctness": _median([item.correctness for item in state.latest_reviews]),
                "actionability": _median([item.actionability for item in state.latest_reviews]),
                "traceability": _median([item.traceability for item in state.latest_reviews]),
            }
        if assessment:
            resolved.append(assessment)

    resolved_count = len(resolved)
    yes_correct = sum(float(item["correctness"]) >= 4 for item in resolved)
    no_correct = sum(float(item["correctness"]) <= 2 for item in resolved)
    correctness_assessed = yes_correct + no_correct
    actionable = sum(float(item["actionability"]) >= 4 for item in resolved)
    traceable = sum(float(item["traceability"]) >= 4 for item in resolved)
    harmful = sum(item["decision"] == "harmful_false_positive" for item in resolved)

    latest_human: dict[str, Any] = {}
    for item in reviews:
        case_id = str(item.case_id or item.campaign_id or "")
        if item.source_kind != "human" or case_id not in selected_cases:
            continue
        current = latest_human.get(item.finding_id)
        if current is None or item.revision_number > current.revision_number:
            latest_human[item.finding_id] = item

    independent = [item for item in selected_disagreements if item.reviewer_count >= 2]
    material_disagreement = [
        item
        for item in independent
        if item.status in {"disagreement", "stale_adjudication", "adjudicated"}
        or bool(item.disagreement_reasons)
    ]

    completed_workflow = [
        item
        for item in workflow
        if item.case_id in selected_cases and item.status == "completed"
    ]
    workflow_status_counts = Counter(
        item.status for item in workflow if item.case_id in selected_cases
    )
    workflow_by_case: dict[str, dict[str, float | int]] = defaultdict(
        lambda: {"touch": 0.0, "actions": 0, "count": 0}
    )
    for item in completed_workflow:
        workflow_by_case[item.case_id]["touch"] += item.operator_touch_seconds
        workflow_by_case[item.case_id]["actions"] += item.manual_action_count
        workflow_by_case[item.case_id]["count"] += 1
    measured_cases = set(workflow_by_case)
    touch_minutes = [float(value["touch"]) / 60 for value in workflow_by_case.values()]
    actions_per_case = [int(value["actions"]) for value in workflow_by_case.values()]
    workflow_coverage = _ratio(len(measured_cases), len(selected_cases))

    outcome_cases = {
        case_id
        for case_id in selected_cases
        if (campaign_by_case.get(case_id) or {}).get("outcomes")
    }
    outcome_coverage = _ratio(len(outcome_cases), len(selected_cases))
    review_coverage = _ratio(resolved_count, len(selected_disagreements))

    metrics = build_metrics(
        yes_correct=yes_correct,
        correctness_assessed=correctness_assessed,
        review_coverage=review_coverage,
        actionable=actionable,
        resolved_count=resolved_count,
        traceable=traceable,
        latest_human=latest_human,
        selected_cases=selected_cases,
        harmful=harmful,
        material_disagreement=material_disagreement,
        independent=independent,
        selected_disagreements=selected_disagreements,
        touch_minutes=touch_minutes,
        measured_cases=measured_cases,
        actions_per_case=actions_per_case,
        workflow_coverage=workflow_coverage,
        outcome_coverage=outcome_coverage,
        outcome_cases=outcome_cases,
    )

    system_by_case = Counter(review_case.values())
    resolved_by_case = Counter(item["case_id"] for item in resolved)
    human_by_case = Counter(
        str(item.case_id or item.campaign_id or "") for item in latest_human.values()
    )
    case_rows: list[CalibrationCaseRow] = []
    for case_id in sorted(selected_cases):
        measured = workflow_by_case.get(case_id)
        outcome_count = len((campaign_by_case.get(case_id) or {}).get("outcomes") or [])
        total_findings = system_by_case.get(case_id, 0)
        case_rows.append(
            CalibrationCaseRow(
                case_id=case_id,
                campaign_id=campaign_id_by_case.get(case_id) or None,
                evidence_class=case_class(case_id),
                inclusion_status=inclusion(case_id),
                system_finding_count=total_findings,
                resolved_finding_count=resolved_by_case.get(case_id, 0),
                unresolved_finding_count=max(
                    0, total_findings - resolved_by_case.get(case_id, 0)
                ),
                human_added_finding_count=human_by_case.get(case_id, 0),
                outcome_observation_count=outcome_count,
                workflow_measurement_count=int(measured["count"]) if measured else 0,
                operator_touch_seconds=float(measured["touch"]) if measured else None,
                manual_action_count=int(measured["actions"]) if measured else None,
            )
        )

    split: dict[str, dict[str, int]] = {}
    for evidence_class in ("real_client", "synthetic", "unclassified"):
        ids = {
            case_id
            for case_id in all_case_ids
            if case_class(case_id) == evidence_class and inclusion(case_id) == "included"
        }
        split[evidence_class] = {
            "case_count": len(ids),
            "system_finding_count": sum(system_by_case.get(case_id, 0) for case_id in ids),
            "outcome_case_count": sum(
                bool((campaign_by_case.get(case_id) or {}).get("outcomes"))
                for case_id in ids
            ),
            "workflow_measured_case_count": sum(
                case_id in workflow_by_case for case_id in ids
            ),
        }

    timestamps = [item.created_at for item in reviews]
    timestamps += [item.created_at for item in adjudications]
    timestamps += [item.created_at for item in workflow]
    timestamps += [item.updated_at for item in classifications.values()]
    generated_at = max(timestamps, default=EPOCH)

    return CalibrationDashboardResponse(
        schema_version=SCHEMA_VERSION,
        generated_at=generated_at,
        project_id=project_id,
        evidence_filter=evidence_filter,
        metrics=metrics,
        cases=case_rows,
        evidence_split=split,
        review_status_counts=dict(sorted(review_status_counts.items())),
        workflow_status_counts=dict(sorted(workflow_status_counts.items())),
        claim_boundary=dict(CLAIM_BOUNDARY),
        definitions_version=DEFINITIONS_VERSION,
        source_fingerprints={
            "campaign_evidence": workspace.get("source_fingerprint"),
            "normalization_run_id": workspace.get("normalization_run_id"),
        },
        limitations=[
            "All metrics are descriptive calibration/workflow evidence and are not validated model accuracy.",
            "Real, synthetic and unclassified evidence are never silently pooled in a filtered view.",
            "Rates with unresolved or missing evidence expose reduced coverage rather than inferred values.",
        ],
    )

def dashboard_json_bytes(
    project_id: str,
    *,
    evidence_filter: EvidenceFilter = "all",
) -> bytes:
    from src.modules.calibration_dashboard.exports import dashboard_json_bytes as render

    return render(project_id, evidence_filter=evidence_filter)


def dashboard_xlsx_bytes(
    project_id: str,
    *,
    evidence_filter: EvidenceFilter = "all",
) -> bytes:
    from src.modules.calibration_dashboard.exports import dashboard_xlsx_bytes as render

    return render(project_id, evidence_filter=evidence_filter)


def export_manifest(
    project_id: str,
    *,
    evidence_filter: EvidenceFilter = "all",
) -> dict[str, Any]:
    from src.modules.calibration_dashboard.exports import export_manifest as build

    return build(project_id, evidence_filter=evidence_filter)

