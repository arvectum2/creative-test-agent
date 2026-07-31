from __future__ import annotations

from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse

from src.modules.campaign_evidence.service import get_campaign_evidence_detail
from src.modules.finding_reviews.schemas import (
    CreateFindingAdjudicationRequest,
    CreateFindingReviewRequest,
    CreateHumanFindingRequest,
)
from src.modules.finding_reviews.service import (
    create_finding_adjudication,
    create_human_finding,
    create_system_review,
    get_finding_disagreement,
    get_reviewable_finding,
    list_project_reviews,
)
from src.modules.ui.router import _error, _render
from src.shared.errors import AppError
from src.shared.security.auth import get_current_user_from_request

router = APIRouter()

DECISIONS = (
    "supported",
    "partially_supported",
    "unsupported",
    "harmful_false_positive",
    "needs_rewording",
)
SEVERITY_CORRECTNESS = ("correct", "overstated", "understated", "not_applicable")


def _adjudicator_user(request: Request) -> dict:
    user = get_current_user_from_request(request)
    if user.get("role") not in {"admin", "manager"}:
        raise AppError("adjudicator_permission_denied", "Adjudication requires admin or manager role", 403)
    return user


@router.get(
    "/ui/projects/{project_id}/campaign-evidence/{campaign_id}/findings/{finding_id}/review",
    include_in_schema=False,
)
def ui_finding_review(
    request: Request,
    project_id: str,
    campaign_id: str,
    finding_id: str,
):
    try:
        finding = get_reviewable_finding(project_id, finding_id)
        if finding.campaign_id != campaign_id and finding.case_id != campaign_id:
            raise AppError("finding_campaign_mismatch", "Finding does not belong to this campaign", 404)
    except AppError as exc:
        return _error(request, exc.message)
    return _render(
        request,
        "finding_reviews/review.html",
        finding=finding,
        project_id=project_id,
        campaign_id=campaign_id,
        decisions=DECISIONS,
        severity_options=SEVERITY_CORRECTNESS,
        saved=request.query_params.get("saved") == "1",
    )


@router.post(
    "/ui/projects/{project_id}/campaign-evidence/{campaign_id}/findings/{finding_id}/review",
    include_in_schema=False,
)
def ui_save_finding_review(
    request: Request,
    project_id: str,
    campaign_id: str,
    finding_id: str,
    expected_system_finding_sha256: str = Form(...),
    reviewer_subject_id: str = Form(default=""),
    reviewer_display_name: str = Form(default=""),
    reviewer_role: str = Form(...),
    decision: str = Form(...),
    correctness: int = Form(...),
    relevance: int = Form(...),
    actionability: int = Form(...),
    traceability: int = Form(...),
    severity_correctness: str = Form(...),
    reviewer_confidence: float = Form(...),
    rationale: str = Form(...),
    comment: str = Form(default=""),
):
    try:
        body = CreateFindingReviewRequest(
            expected_system_finding_sha256=expected_system_finding_sha256,
            reviewer_subject_id=reviewer_subject_id or None,
            reviewer_display_name=reviewer_display_name or None,
            reviewer_role=reviewer_role,
            decision=decision,
            correctness=correctness,
            relevance=relevance,
            actionability=actionability,
            traceability=traceability,
            severity_correctness=severity_correctness,
            reviewer_confidence=reviewer_confidence,
            rationale=rationale,
            comment=comment or None,
        )
        create_system_review(
            project_id,
            finding_id,
            body,
            user=get_current_user_from_request(request),
        )
    except (AppError, ValueError) as exc:
        message = exc.message if isinstance(exc, AppError) else str(exc)
        return _error(request, message)
    return RedirectResponse(
        url=(
            f"/ui/projects/{project_id}/campaign-evidence/{campaign_id}/"
            f"findings/{finding_id}/review?saved=1"
        ),
        status_code=303,
    )


@router.get(
    "/ui/projects/{project_id}/campaign-evidence/{campaign_id}/findings/{finding_id}/adjudicate",
    include_in_schema=False,
)
def ui_finding_adjudication(
    request: Request,
    project_id: str,
    campaign_id: str,
    finding_id: str,
):
    try:
        finding = get_reviewable_finding(project_id, finding_id)
        if finding.campaign_id != campaign_id and finding.case_id != campaign_id:
            raise AppError("finding_campaign_mismatch", "Finding does not belong to this campaign", 404)
        disagreement = get_finding_disagreement(project_id, finding_id)
    except AppError as exc:
        return _error(request, exc.message)
    return _render(
        request,
        "finding_reviews/adjudication.html",
        finding=finding,
        disagreement=disagreement,
        project_id=project_id,
        campaign_id=campaign_id,
        decisions=DECISIONS,
        severity_options=SEVERITY_CORRECTNESS,
        saved=request.query_params.get("saved") == "1",
    )


@router.post(
    "/ui/projects/{project_id}/campaign-evidence/{campaign_id}/findings/{finding_id}/adjudicate",
    include_in_schema=False,
)
def ui_save_finding_adjudication(
    request: Request,
    project_id: str,
    campaign_id: str,
    finding_id: str,
    expected_basis_fingerprint_sha256: str = Form(...),
    adjudicator_subject_id: str = Form(default=""),
    adjudicator_display_name: str = Form(default=""),
    adjudicator_role: str = Form(...),
    decision: str = Form(...),
    correctness: int = Form(...),
    relevance: int = Form(...),
    actionability: int = Form(...),
    traceability: int = Form(...),
    severity_correctness: str = Form(...),
    adjudicator_confidence: float = Form(...),
    rationale: str = Form(...),
    comment: str = Form(default=""),
):
    try:
        body = CreateFindingAdjudicationRequest(
            expected_basis_fingerprint_sha256=expected_basis_fingerprint_sha256,
            adjudicator_subject_id=adjudicator_subject_id or None,
            adjudicator_display_name=adjudicator_display_name or None,
            adjudicator_role=adjudicator_role,
            decision=decision,
            correctness=correctness,
            relevance=relevance,
            actionability=actionability,
            traceability=traceability,
            severity_correctness=severity_correctness,
            adjudicator_confidence=adjudicator_confidence,
            rationale=rationale,
            comment=comment or None,
        )
        create_finding_adjudication(
            project_id,
            finding_id,
            body,
            user=_adjudicator_user(request),
        )
    except (AppError, ValueError) as exc:
        message = exc.message if isinstance(exc, AppError) else str(exc)
        return _error(request, message)
    return RedirectResponse(
        url=(
            f"/ui/projects/{project_id}/campaign-evidence/{campaign_id}/"
            f"findings/{finding_id}/adjudicate?saved=1"
        ),
        status_code=303,
    )


@router.get(
    "/ui/projects/{project_id}/campaign-evidence/{campaign_id}/human-findings/new",
    include_in_schema=False,
)
def ui_new_human_finding(request: Request, project_id: str, campaign_id: str):
    try:
        campaign = get_campaign_evidence_detail(project_id, campaign_id)
    except AppError as exc:
        return _error(request, exc.message)
    return _render(
        request,
        "finding_reviews/human_finding.html",
        project_id=project_id,
        campaign=campaign,
    )


@router.post(
    "/ui/projects/{project_id}/campaign-evidence/{campaign_id}/human-findings/new",
    include_in_schema=False,
)
def ui_save_human_finding(
    request: Request,
    project_id: str,
    campaign_id: str,
    creative_record_id: str = Form(default=""),
    creative_asset_id: str = Form(default=""),
    criterion: str = Form(...),
    title: str = Form(...),
    text: str = Form(...),
    proposed_severity: str = Form(...),
    reviewer_subject_id: str = Form(default=""),
    reviewer_display_name: str = Form(default=""),
    reviewer_role: str = Form(...),
    relevance: int = Form(...),
    actionability: int = Form(...),
    traceability: int = Form(...),
    reviewer_confidence: float = Form(...),
    rationale: str = Form(...),
    comment: str = Form(default=""),
):
    try:
        body = CreateHumanFindingRequest(
            campaign_id=campaign_id,
            creative_record_id=creative_record_id or None,
            creative_asset_id=creative_asset_id or None,
            criterion=criterion,
            title=title,
            text=text,
            proposed_severity=proposed_severity,
            reviewer_subject_id=reviewer_subject_id or None,
            reviewer_display_name=reviewer_display_name or None,
            reviewer_role=reviewer_role,
            relevance=relevance,
            actionability=actionability,
            traceability=traceability,
            reviewer_confidence=reviewer_confidence,
            rationale=rationale,
            comment=comment or None,
        )
        create_human_finding(
            project_id,
            body,
            user=get_current_user_from_request(request),
        )
    except (AppError, ValueError) as exc:
        message = exc.message if isinstance(exc, AppError) else str(exc)
        return _error(request, message)
    return RedirectResponse(
        url=f"/ui/projects/{project_id}/campaign-evidence/{campaign_id}",
        status_code=303,
    )


@router.get("/ui/projects/{project_id}/finding-reviews", include_in_schema=False)
def ui_project_finding_reviews(request: Request, project_id: str):
    try:
        reviews = list_project_reviews(project_id)
    except AppError as exc:
        return _error(request, exc.message)
    return _render(
        request,
        "finding_reviews/history.html",
        project_id=project_id,
        reviews=reviews,
    )
