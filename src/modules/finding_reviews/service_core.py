from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from src.modules.campaign_evidence.service import get_campaign_evidence_workspace
from src.modules.client_report_v2.evidence import compose_report_evidence
from src.modules.finding_reviews.models import FindingAdjudication, FindingReview
from src.modules.finding_reviews.schemas import (
    FindingAdjudicationResponse,
    FindingReviewResponse,
    ReviewDisagreementResponse,
    ReviewableFindingDetailResponse,
    ReviewableFindingResponse,
)
from src.shared.db.repository import db_session, json_loads
from src.shared.errors import AppError

ADJUDICATION_POLICY_ID = "independent-review-adjudication/1.0"
MATERIAL_DIMENSION_SPREAD = 2


def _workspace_dict(project_id: str) -> dict[str, Any]:
    workspace = get_campaign_evidence_workspace(project_id)
    if hasattr(workspace, "model_dump"):
        return workspace.model_dump(mode="json")
    if isinstance(workspace, dict):
        return dict(workspace)
    raise AppError("campaign_evidence_invalid", "Campaign evidence workspace is invalid", 409)


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _sha256_json(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _reviewable_findings(project_id: str) -> list[dict[str, Any]]:
    workspace = _workspace_dict(project_id)
    evidence = compose_report_evidence(
        workspace,
        locale="ru",
        generated_at="1970-01-01T00:00:00+00:00",
    )
    case_by_campaign = {
        str(item.get("campaign_id")): str(item.get("case_id") or item.get("campaign_id"))
        for item in workspace.get("campaigns") or []
    }
    findings: list[dict[str, Any]] = []
    for item in (evidence.get("agent_diagnostics") or {}).get("findings") or []:
        snapshot = dict(item)
        snapshot["project_id"] = project_id
        snapshot["case_id"] = case_by_campaign.get(
            str(item.get("campaign_id")), str(item.get("campaign_id") or "")
        )
        findings.append(snapshot)
    return findings


def _find_system_finding(project_id: str, finding_id: str) -> dict[str, Any]:
    for item in _reviewable_findings(project_id):
        if item.get("finding_id") == finding_id:
            return item
    raise AppError("finding_not_found", "Finding not found in this project", 404)


def _subject_token(value: str) -> str:
    token = re.sub(r"[^A-Za-z0-9_.:@-]+", "-", value.strip()).strip("-")
    if not token:
        raise AppError("reviewer_identity_invalid", "Reviewer identity is invalid", 422)
    return token[:220]


def _resolve_subject(
    user: dict[str, Any],
    *,
    requested_id: str | None,
    requested_display_name: str | None,
) -> tuple[str, str, str]:
    user_id = str(user.get("user_id") or "").strip()
    if user_id and user_id != "system":
        return (
            f"user:{_subject_token(user_id)}",
            "authenticated_user",
            str(user.get("display_name") or user_id)[:255],
        )
    raw_id = requested_id or "local-system"
    subject_id = raw_id if raw_id.startswith("declared:") else f"declared:{_subject_token(raw_id)}"
    display_name = str(requested_display_name or user.get("display_name") or raw_id).strip()
    if not display_name:
        raise AppError("reviewer_name_required", "Reviewer display name is required", 422)
    return subject_id[:255], "declared_expert", display_name[:255]


def _all_reviews(project_id: str, finding_id: str | None = None) -> list[FindingReview]:
    with db_session() as db:
        query = db.query(FindingReview).filter(FindingReview.project_id == project_id)
        if finding_id:
            query = query.filter(FindingReview.finding_id == finding_id)
        rows = query.order_by(
            FindingReview.finding_id.asc(),
            FindingReview.revision_number.asc(),
            FindingReview.created_at.asc(),
        ).all()
        for row in rows:
            db.expunge(row)
        return rows


def _all_adjudications(project_id: str, finding_id: str | None = None) -> list[FindingAdjudication]:
    with db_session() as db:
        query = db.query(FindingAdjudication).filter(FindingAdjudication.project_id == project_id)
        if finding_id:
            query = query.filter(FindingAdjudication.finding_id == finding_id)
        rows = query.order_by(
            FindingAdjudication.finding_id.asc(),
            FindingAdjudication.adjudication_round.asc(),
            FindingAdjudication.created_at.asc(),
        ).all()
        for row in rows:
            db.expunge(row)
        return rows


def _latest_review_rows(project_id: str, finding_id: str | None = None) -> dict[tuple[str, str], FindingReview]:
    latest: dict[tuple[str, str], FindingReview] = {}
    for row in _all_reviews(project_id, finding_id):
        key = (row.finding_id, row.reviewer_subject_id)
        current = latest.get(key)
        if current is None or (
            row.reviewer_revision_number,
            row.revision_number,
        ) >= (
            current.reviewer_revision_number,
            current.revision_number,
        ):
            latest[key] = row
    return latest


def _review_counts(project_id: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in _all_reviews(project_id):
        counts[row.finding_id] = counts.get(row.finding_id, 0) + 1
    return counts


def _to_response(row: FindingReview) -> FindingReviewResponse:
    return FindingReviewResponse(
        id=row.id,
        project_id=row.project_id,
        campaign_id=row.campaign_id,
        case_id=row.case_id,
        creative_record_id=row.creative_record_id,
        creative_asset_id=row.creative_asset_id,
        test_run_id=row.test_run_id,
        finding_id=row.finding_id,
        source_kind=row.source_kind,
        system_finding_snapshot=json_loads(row.system_finding_snapshot_json)
        if row.system_finding_snapshot_json
        else None,
        system_finding_snapshot_sha256=row.system_finding_snapshot_sha256,
        human_finding_snapshot=json_loads(row.human_finding_snapshot_json)
        if row.human_finding_snapshot_json
        else None,
        human_finding_snapshot_sha256=row.human_finding_snapshot_sha256,
        reviewer_user_id=row.reviewer_user_id,
        reviewer_subject_id=row.reviewer_subject_id,
        reviewer_subject_kind=row.reviewer_subject_kind,
        reviewer_display_name=row.reviewer_display_name,
        reviewer_role=row.reviewer_role,
        decision=row.decision,
        correctness=row.correctness,
        relevance=row.relevance,
        actionability=row.actionability,
        traceability=row.traceability,
        severity_correctness=row.severity_correctness,
        reviewer_confidence=row.reviewer_confidence,
        rationale=row.rationale,
        comment=row.comment,
        revision_number=row.revision_number,
        reviewer_revision_number=row.reviewer_revision_number,
        supersedes_review_id=row.supersedes_review_id,
        created_by_user_id=row.created_by_user_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _to_adjudication_response(row: FindingAdjudication) -> FindingAdjudicationResponse:
    return FindingAdjudicationResponse(
        id=row.id,
        project_id=row.project_id,
        campaign_id=row.campaign_id,
        case_id=row.case_id,
        creative_record_id=row.creative_record_id,
        creative_asset_id=row.creative_asset_id,
        test_run_id=row.test_run_id,
        finding_id=row.finding_id,
        source_kind=row.source_kind,
        policy_id=row.policy_id,
        basis_review_ids=list(json_loads(row.basis_review_ids_json) or []),
        basis_fingerprint_sha256=row.basis_fingerprint_sha256,
        adjudicator_user_id=row.adjudicator_user_id,
        adjudicator_subject_id=row.adjudicator_subject_id,
        adjudicator_subject_kind=row.adjudicator_subject_kind,
        adjudicator_display_name=row.adjudicator_display_name,
        adjudicator_role=row.adjudicator_role,
        decision=row.decision,
        correctness=row.correctness,
        relevance=row.relevance,
        actionability=row.actionability,
        traceability=row.traceability,
        severity_correctness=row.severity_correctness,
        adjudicator_confidence=row.adjudicator_confidence,
        rationale=row.rationale,
        comment=row.comment,
        adjudication_round=row.adjudication_round,
        supersedes_adjudication_id=row.supersedes_adjudication_id,
        created_by_user_id=row.created_by_user_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _basis_payload(rows: list[FindingReview]) -> list[dict[str, Any]]:
    return [
        {
            "review_id": row.id,
            "reviewer_subject_id": row.reviewer_subject_id,
            "reviewer_revision_number": row.reviewer_revision_number,
            "finding_snapshot_sha256": row.system_finding_snapshot_sha256
            or row.human_finding_snapshot_sha256,
            "decision": row.decision,
            "correctness": row.correctness,
            "relevance": row.relevance,
            "actionability": row.actionability,
            "traceability": row.traceability,
            "severity_correctness": row.severity_correctness,
            "reviewer_confidence": row.reviewer_confidence,
        }
        for row in sorted(rows, key=lambda item: (item.reviewer_subject_id, item.id))
    ]


def _basis_fingerprint(rows: list[FindingReview]) -> str:
    return _sha256_json(
        {
            "policy_id": ADJUDICATION_POLICY_ID,
            "latest_reviews": _basis_payload(rows),
        }
    )


def get_finding_disagreement(project_id: str, finding_id: str) -> ReviewDisagreementResponse:
    _find_system_finding(project_id, finding_id)
    latest_rows = [
        row for (row_finding_id, _), row in _latest_review_rows(project_id, finding_id).items()
        if row_finding_id == finding_id and row.source_kind == "system"
    ]
    latest_rows.sort(key=lambda item: (item.reviewer_subject_id, item.id))
    latest_reviews = [_to_response(row) for row in latest_rows]
    basis_review_ids = [row.id for row in latest_rows]
    basis_fingerprint = _basis_fingerprint(latest_rows)

    decision_values = sorted({row.decision for row in latest_rows})
    severity_values = sorted({row.severity_correctness for row in latest_rows})
    dimension_spreads: dict[str, int] = {}
    reasons: list[str] = []
    for field in ("correctness", "relevance", "actionability", "traceability"):
        values = [int(getattr(row, field)) for row in latest_rows]
        spread = max(values) - min(values) if values else 0
        dimension_spreads[field] = spread
        if spread >= MATERIAL_DIMENSION_SPREAD:
            reasons.append(f"{field}_spread:{spread}")
    if len(decision_values) > 1:
        reasons.insert(0, "decision_mismatch")
    if len(severity_values) > 1:
        reasons.append("severity_correctness_mismatch")

    adjudications = _all_adjudications(project_id, finding_id)
    latest_adjudication = _to_adjudication_response(adjudications[-1]) if adjudications else None
    adjudication_current = bool(
        latest_adjudication
        and latest_adjudication.basis_fingerprint_sha256 == basis_fingerprint
        and latest_adjudication.basis_review_ids == basis_review_ids
    )

    if len(latest_rows) < 2:
        status = "insufficient_reviews"
    elif reasons:
        if adjudication_current:
            status = "adjudicated"
        elif latest_adjudication:
            status = "stale_adjudication"
        else:
            status = "disagreement"
    else:
        status = "agreement"

    return ReviewDisagreementResponse(
        project_id=project_id,
        finding_id=finding_id,
        reviewer_count=len(latest_rows),
        latest_reviews=latest_reviews,
        status=status,
        disagreement_reasons=reasons,
        decision_values=decision_values,
        dimension_spreads=dimension_spreads,
        severity_values=severity_values,
        basis_review_ids=basis_review_ids,
        basis_fingerprint_sha256=basis_fingerprint,
        latest_adjudication=latest_adjudication,
        adjudication_current=adjudication_current,
    )


def list_project_disagreements(project_id: str) -> list[ReviewDisagreementResponse]:
    _workspace_dict(project_id)
    return [
        get_finding_disagreement(project_id, str(item.get("finding_id")))
        for item in _reviewable_findings(project_id)
    ]


def list_reviewable_findings(
    project_id: str,
    *,
    campaign_id: str | None = None,
) -> list[ReviewableFindingResponse]:
    latest_by_reviewer = _latest_review_rows(project_id)
    counts = _review_counts(project_id)
    result: list[ReviewableFindingResponse] = []
    for snapshot in _reviewable_findings(project_id):
        if campaign_id and snapshot.get("campaign_id") != campaign_id and snapshot.get("case_id") != campaign_id:
            continue
        finding_id = str(snapshot.get("finding_id"))
        digest = _sha256_json(snapshot)
        latest_rows = [
            row for (row_finding_id, _), row in latest_by_reviewer.items()
            if row_finding_id == finding_id
        ]
        latest_rows.sort(key=lambda item: item.revision_number)
        latest_responses = [_to_response(row) for row in latest_rows]
        latest_response = latest_responses[-1] if latest_responses else None
        result.append(
            ReviewableFindingResponse(
                finding_id=finding_id,
                project_id=project_id,
                campaign_id=str(snapshot.get("campaign_id")),
                case_id=str(snapshot.get("case_id")),
                creative_record_id=str(snapshot.get("creative_record_id")),
                creative_asset_id=snapshot.get("creative_asset_id"),
                test_run_id=snapshot.get("test_run_id"),
                criterion=str(snapshot.get("criterion") or "finding"),
                text=str(snapshot.get("text") or ""),
                score=snapshot.get("score"),
                confidence=snapshot.get("confidence"),
                snapshot_sha256=digest,
                system_finding_snapshot=snapshot,
                latest_review=latest_response,
                latest_reviews=latest_responses,
                review_count=counts.get(finding_id, 0),
                reviewer_count=len(latest_responses),
                current_snapshot_matches_latest_review=all(
                    row.system_finding_snapshot_sha256 == digest for row in latest_rows
                ),
                disagreement=get_finding_disagreement(project_id, finding_id),
            )
        )
    return result


def get_reviewable_finding(project_id: str, finding_id: str) -> ReviewableFindingDetailResponse:
    finding = _find_system_finding(project_id, finding_id)
    digest = _sha256_json(finding)
    history_rows = _all_reviews(project_id, finding_id)
    history = [_to_response(item) for item in history_rows]
    latest_rows = [
        row for (row_finding_id, _), row in _latest_review_rows(project_id, finding_id).items()
        if row_finding_id == finding_id
    ]
    latest_rows.sort(key=lambda item: item.revision_number)
    latest_responses = [_to_response(item) for item in latest_rows]
    adjudication_history = [
        _to_adjudication_response(item) for item in _all_adjudications(project_id, finding_id)
    ]
    return ReviewableFindingDetailResponse(
        finding_id=finding_id,
        project_id=project_id,
        campaign_id=str(finding.get("campaign_id")),
        case_id=str(finding.get("case_id")),
        creative_record_id=str(finding.get("creative_record_id")),
        creative_asset_id=finding.get("creative_asset_id"),
        test_run_id=finding.get("test_run_id"),
        criterion=str(finding.get("criterion") or "finding"),
        text=str(finding.get("text") or ""),
        score=finding.get("score"),
        confidence=finding.get("confidence"),
        snapshot_sha256=digest,
        system_finding_snapshot=finding,
        latest_review=latest_responses[-1] if latest_responses else None,
        latest_reviews=latest_responses,
        review_count=len(history),
        reviewer_count=len(latest_responses),
        current_snapshot_matches_latest_review=all(
            row.system_finding_snapshot_sha256 == digest for row in latest_rows
        ),
        disagreement=get_finding_disagreement(project_id, finding_id),
        review_history=history,
        adjudication_history=adjudication_history,
    )
