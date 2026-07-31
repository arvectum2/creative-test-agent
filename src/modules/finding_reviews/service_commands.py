from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from src.modules.audit_log.service import write_audit_event
from src.modules.finding_reviews.models import FindingAdjudication, FindingReview
from src.modules.finding_reviews.schemas import (
    CreateFindingAdjudicationRequest,
    CreateFindingReviewRequest,
    CreateHumanFindingRequest,
    FindingAdjudicationResponse,
    FindingReviewResponse,
)
from src.modules.finding_reviews.service_core import (
    ADJUDICATION_POLICY_ID,
    _all_adjudications,
    _all_reviews,
    _find_system_finding,
    _latest_review_rows,
    _resolve_subject,
    _sha256_json,
    _to_adjudication_response,
    _to_response,
    _workspace_dict,
    get_finding_disagreement,
)
from src.shared.db.repository import db_session, json_dumps
from src.shared.errors import AppError


def create_system_review(
    project_id: str,
    finding_id: str,
    body: CreateFindingReviewRequest,
    *,
    user: dict[str, Any],
) -> FindingReviewResponse:
    snapshot = _find_system_finding(project_id, finding_id)
    digest = _sha256_json(snapshot)
    if body.expected_system_finding_sha256 != digest:
        raise AppError(
            "finding_snapshot_changed",
            "The system finding changed after the review page was opened; reload before saving",
            409,
        )
    subject_id, subject_kind, display_name = _resolve_subject(
        user,
        requested_id=body.reviewer_subject_id,
        requested_display_name=body.reviewer_display_name,
    )

    now = datetime.now(timezone.utc)
    with db_session() as db:
        latest_global = (
            db.query(FindingReview)
            .filter(
                FindingReview.project_id == project_id,
                FindingReview.finding_id == finding_id,
            )
            .order_by(FindingReview.revision_number.desc(), FindingReview.created_at.desc())
            .first()
        )
        latest_subject = (
            db.query(FindingReview)
            .filter(
                FindingReview.project_id == project_id,
                FindingReview.finding_id == finding_id,
                FindingReview.reviewer_subject_id == subject_id,
            )
            .order_by(
                FindingReview.reviewer_revision_number.desc(),
                FindingReview.revision_number.desc(),
            )
            .first()
        )
        row = FindingReview(
            project_id=project_id,
            campaign_id=snapshot.get("campaign_id"),
            case_id=snapshot.get("case_id"),
            creative_record_id=snapshot.get("creative_record_id"),
            creative_asset_id=snapshot.get("creative_asset_id"),
            test_run_id=snapshot.get("test_run_id"),
            finding_id=finding_id,
            source_kind="system",
            system_finding_snapshot_json=json_dumps(snapshot),
            system_finding_snapshot_sha256=digest,
            human_finding_snapshot_json=None,
            human_finding_snapshot_sha256=None,
            reviewer_user_id=user.get("user_id"),
            reviewer_subject_id=subject_id,
            reviewer_subject_kind=subject_kind,
            reviewer_display_name=display_name,
            reviewer_role=body.reviewer_role,
            decision=body.decision,
            correctness=body.correctness,
            relevance=body.relevance,
            actionability=body.actionability,
            traceability=body.traceability,
            severity_correctness=body.severity_correctness,
            reviewer_confidence=body.reviewer_confidence,
            rationale=body.rationale,
            comment=body.comment,
            revision_number=(latest_global.revision_number + 1) if latest_global else 1,
            reviewer_revision_number=(latest_subject.reviewer_revision_number + 1)
            if latest_subject
            else 1,
            supersedes_review_id=latest_subject.id if latest_subject else None,
            created_by_user_id=user.get("user_id"),
            created_at=now,
            updated_at=now,
        )
        db.add(row)
        db.flush()
        response = _to_response(row)

    write_audit_event(
        "finding_review_created",
        "finding_review",
        response.id,
        {
            "project_id": project_id,
            "finding_id": finding_id,
            "reviewer_subject_id": response.reviewer_subject_id,
            "decision": response.decision,
            "revision_number": response.revision_number,
            "reviewer_revision_number": response.reviewer_revision_number,
            "system_finding_snapshot_sha256": digest,
            "supersedes_review_id": response.supersedes_review_id,
        },
    )
    return response


def create_human_finding(
    project_id: str,
    body: CreateHumanFindingRequest,
    *,
    user: dict[str, Any],
) -> FindingReviewResponse:
    workspace = _workspace_dict(project_id)
    campaign = next(
        (
            item
            for item in workspace.get("campaigns") or []
            if item.get("campaign_id") == body.campaign_id or item.get("case_id") == body.campaign_id
        ),
        None,
    )
    if campaign is None:
        raise AppError("campaign_not_found", "Campaign not found in this project", 404)
    assets = campaign.get("assets") or []
    if body.creative_record_id and not any(
        item.get("creative_record_id") == body.creative_record_id for item in assets
    ):
        raise AppError("creative_record_not_found", "Creative record does not belong to this campaign", 404)
    if body.creative_asset_id and not any(
        item.get("creative_asset_id") == body.creative_asset_id for item in assets
    ):
        raise AppError("creative_asset_not_found", "Creative asset does not belong to this campaign", 404)

    subject_id, subject_kind, display_name = _resolve_subject(
        user,
        requested_id=body.reviewer_subject_id,
        requested_display_name=body.reviewer_display_name,
    )
    finding_id = f"human-finding:{uuid4()}"
    snapshot = {
        "finding_id": finding_id,
        "project_id": project_id,
        "campaign_id": campaign.get("campaign_id"),
        "case_id": campaign.get("case_id") or campaign.get("campaign_id"),
        "creative_record_id": body.creative_record_id,
        "creative_asset_id": body.creative_asset_id,
        "criterion": body.criterion,
        "title": body.title,
        "text": body.text,
        "proposed_severity": body.proposed_severity,
        "source_kind": "human",
        "system_finding_fabricated": False,
    }
    digest = _sha256_json(snapshot)
    now = datetime.now(timezone.utc)
    with db_session() as db:
        row = FindingReview(
            project_id=project_id,
            campaign_id=campaign.get("campaign_id"),
            case_id=campaign.get("case_id") or campaign.get("campaign_id"),
            creative_record_id=body.creative_record_id,
            creative_asset_id=body.creative_asset_id,
            test_run_id=None,
            finding_id=finding_id,
            source_kind="human",
            system_finding_snapshot_json=None,
            system_finding_snapshot_sha256=None,
            human_finding_snapshot_json=json_dumps(snapshot),
            human_finding_snapshot_sha256=digest,
            reviewer_user_id=user.get("user_id"),
            reviewer_subject_id=subject_id,
            reviewer_subject_kind=subject_kind,
            reviewer_display_name=display_name,
            reviewer_role=body.reviewer_role,
            decision="missed_by_system",
            correctness=5,
            relevance=body.relevance,
            actionability=body.actionability,
            traceability=body.traceability,
            severity_correctness="not_applicable",
            reviewer_confidence=body.reviewer_confidence,
            rationale=body.rationale,
            comment=body.comment,
            revision_number=1,
            reviewer_revision_number=1,
            supersedes_review_id=None,
            created_by_user_id=user.get("user_id"),
            created_at=now,
            updated_at=now,
        )
        db.add(row)
        db.flush()
        response = _to_response(row)

    write_audit_event(
        "human_finding_created",
        "finding_review",
        response.id,
        {
            "project_id": project_id,
            "finding_id": finding_id,
            "reviewer_subject_id": subject_id,
            "decision": "missed_by_system",
            "human_finding_snapshot_sha256": digest,
            "system_finding_fabricated": False,
        },
    )
    return response


def create_finding_adjudication(
    project_id: str,
    finding_id: str,
    body: CreateFindingAdjudicationRequest,
    *,
    user: dict[str, Any],
) -> FindingAdjudicationResponse:
    if user.get("role") not in {"admin", "manager"}:
        raise AppError(
            "adjudicator_permission_denied",
            "Adjudication requires admin or manager role",
            403,
        )
    disagreement = get_finding_disagreement(project_id, finding_id)
    if disagreement.status not in {"disagreement", "stale_adjudication"}:
        raise AppError(
            "adjudication_not_required",
            "Adjudication requires an active disagreement between at least two reviewers",
            409,
        )
    if body.expected_basis_fingerprint_sha256 != disagreement.basis_fingerprint_sha256:
        raise AppError(
            "adjudication_basis_changed",
            "The latest independent reviews changed after the adjudication page was opened; reload before saving",
            409,
        )
    subject_id, subject_kind, display_name = _resolve_subject(
        user,
        requested_id=body.adjudicator_subject_id,
        requested_display_name=body.adjudicator_display_name,
    )
    reviewer_subjects = {item.reviewer_subject_id for item in disagreement.latest_reviews}
    if subject_id in reviewer_subjects:
        raise AppError(
            "adjudicator_not_independent",
            "The adjudicator must be distinct from all basis reviewers under the provisional policy",
            409,
        )

    finding = _find_system_finding(project_id, finding_id)
    now = datetime.now(timezone.utc)
    with db_session() as db:
        latest = (
            db.query(FindingAdjudication)
            .filter(
                FindingAdjudication.project_id == project_id,
                FindingAdjudication.finding_id == finding_id,
            )
            .order_by(
                FindingAdjudication.adjudication_round.desc(),
                FindingAdjudication.created_at.desc(),
            )
            .first()
        )
        row = FindingAdjudication(
            project_id=project_id,
            campaign_id=finding.get("campaign_id"),
            case_id=finding.get("case_id"),
            creative_record_id=finding.get("creative_record_id"),
            creative_asset_id=finding.get("creative_asset_id"),
            test_run_id=finding.get("test_run_id"),
            finding_id=finding_id,
            source_kind="system",
            policy_id=ADJUDICATION_POLICY_ID,
            basis_review_ids_json=json_dumps(disagreement.basis_review_ids),
            basis_fingerprint_sha256=disagreement.basis_fingerprint_sha256,
            adjudicator_user_id=user.get("user_id"),
            adjudicator_subject_id=subject_id,
            adjudicator_subject_kind=subject_kind,
            adjudicator_display_name=display_name,
            adjudicator_role=body.adjudicator_role,
            decision=body.decision,
            correctness=body.correctness,
            relevance=body.relevance,
            actionability=body.actionability,
            traceability=body.traceability,
            severity_correctness=body.severity_correctness,
            adjudicator_confidence=body.adjudicator_confidence,
            rationale=body.rationale,
            comment=body.comment,
            adjudication_round=(latest.adjudication_round + 1) if latest else 1,
            supersedes_adjudication_id=latest.id if latest else None,
            created_by_user_id=user.get("user_id"),
            created_at=now,
            updated_at=now,
        )
        db.add(row)
        db.flush()
        response = _to_adjudication_response(row)

    write_audit_event(
        "finding_adjudication_created",
        "finding_adjudication",
        response.id,
        {
            "project_id": project_id,
            "finding_id": finding_id,
            "policy_id": ADJUDICATION_POLICY_ID,
            "basis_review_ids": response.basis_review_ids,
            "basis_fingerprint_sha256": response.basis_fingerprint_sha256,
            "adjudicator_subject_id": response.adjudicator_subject_id,
            "decision": response.decision,
            "adjudication_round": response.adjudication_round,
            "supersedes_adjudication_id": response.supersedes_adjudication_id,
        },
    )
    return response


def list_project_reviews(
    project_id: str,
    *,
    finding_id: str | None = None,
) -> list[FindingReviewResponse]:
    _workspace_dict(project_id)
    return [_to_response(item) for item in _all_reviews(project_id, finding_id)]


def list_project_adjudications(
    project_id: str,
    *,
    finding_id: str | None = None,
) -> list[FindingAdjudicationResponse]:
    _workspace_dict(project_id)
    return [_to_adjudication_response(item) for item in _all_adjudications(project_id, finding_id)]


def latest_review_index(project_id: str) -> dict[str, FindingReviewResponse]:
    latest: dict[str, FindingReview] = {}
    for row in _latest_review_rows(project_id).values():
        current = latest.get(row.finding_id)
        if current is None or row.revision_number > current.revision_number:
            latest[row.finding_id] = row
    return {key: _to_response(value) for key, value in latest.items()}
