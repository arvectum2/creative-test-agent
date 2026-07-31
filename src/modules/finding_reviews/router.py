from __future__ import annotations

import io

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse, StreamingResponse

from src.modules.finding_reviews.schemas import (
    CreateFindingAdjudicationRequest,
    CreateFindingReviewRequest,
    CreateHumanFindingRequest,
    FindingAdjudicationResponse,
    FindingReviewResponse,
    ReviewDisagreementResponse,
    ReviewableFindingDetailResponse,
    ReviewableFindingResponse,
)
from src.modules.finding_reviews.service import (
    build_calibration_package,
    create_finding_adjudication,
    create_human_finding,
    create_system_review,
    export_review_evidence,
    get_finding_disagreement,
    get_reviewable_finding,
    list_project_adjudications,
    list_project_disagreements,
    list_project_reviews,
    list_reviewable_findings,
)
from src.shared.security.auth import get_current_user_from_request

router = APIRouter(prefix="/finding-reviews", tags=["finding-reviews"])


def _reviewer_user(request: Request) -> dict:
    user = get_current_user_from_request(request)
    if user.get("role") not in {"admin", "manager", "analyst"}:
        raise HTTPException(status_code=403, detail="Reviewer role requires write permission")
    return user


def _adjudicator_user(request: Request) -> dict:
    user = get_current_user_from_request(request)
    if user.get("role") not in {"admin", "manager"}:
        raise HTTPException(status_code=403, detail="Adjudication requires admin or manager role")
    return user


@router.get(
    "/projects/{project_id}/findings",
    response_model=list[ReviewableFindingResponse],
)
def get_project_findings(
    project_id: str,
    campaign_id: str | None = Query(default=None),
):
    return list_reviewable_findings(project_id, campaign_id=campaign_id)


@router.get(
    "/projects/{project_id}/findings/{finding_id}",
    response_model=ReviewableFindingDetailResponse,
)
def get_project_finding(project_id: str, finding_id: str):
    return get_reviewable_finding(project_id, finding_id)


@router.get(
    "/projects/{project_id}/findings/{finding_id}/disagreement",
    response_model=ReviewDisagreementResponse,
)
def get_project_finding_disagreement(project_id: str, finding_id: str):
    return get_finding_disagreement(project_id, finding_id)


@router.get(
    "/projects/{project_id}/disagreements",
    response_model=list[ReviewDisagreementResponse],
)
def get_project_disagreements(project_id: str):
    return list_project_disagreements(project_id)


@router.post(
    "/projects/{project_id}/findings/{finding_id}/reviews",
    response_model=FindingReviewResponse,
    status_code=201,
)
def post_project_finding_review(
    project_id: str,
    finding_id: str,
    body: CreateFindingReviewRequest,
    request: Request,
):
    return create_system_review(project_id, finding_id, body, user=_reviewer_user(request))


@router.post(
    "/projects/{project_id}/findings/{finding_id}/adjudications",
    response_model=FindingAdjudicationResponse,
    status_code=201,
)
def post_project_finding_adjudication(
    project_id: str,
    finding_id: str,
    body: CreateFindingAdjudicationRequest,
    request: Request,
):
    return create_finding_adjudication(
        project_id,
        finding_id,
        body,
        user=_adjudicator_user(request),
    )


@router.get(
    "/projects/{project_id}/findings/{finding_id}/adjudications",
    response_model=list[FindingAdjudicationResponse],
)
def get_project_finding_adjudications(project_id: str, finding_id: str):
    return list_project_adjudications(project_id, finding_id=finding_id)


@router.post(
    "/projects/{project_id}/human-findings",
    response_model=FindingReviewResponse,
    status_code=201,
)
def post_project_human_finding(
    project_id: str,
    body: CreateHumanFindingRequest,
    request: Request,
):
    return create_human_finding(project_id, body, user=_reviewer_user(request))


@router.get(
    "/projects/{project_id}/reviews",
    response_model=list[FindingReviewResponse],
)
def get_project_reviews(
    project_id: str,
    finding_id: str | None = Query(default=None),
):
    return list_project_reviews(project_id, finding_id=finding_id)


@router.get(
    "/projects/{project_id}/adjudications",
    response_model=list[FindingAdjudicationResponse],
)
def get_project_adjudications(
    project_id: str,
    finding_id: str | None = Query(default=None),
):
    return list_project_adjudications(project_id, finding_id=finding_id)


@router.get("/projects/{project_id}/evidence.json")
def get_project_review_evidence(project_id: str):
    payload = export_review_evidence(project_id).model_dump(mode="json")
    return JSONResponse(
        content=payload,
        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
    )


@router.get("/projects/{project_id}/calibration-package.zip")
def get_project_review_calibration_package(project_id: str):
    data, filename = build_calibration_package(project_id)
    return StreamingResponse(
        io.BytesIO(data),
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )
