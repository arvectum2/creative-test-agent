from __future__ import annotations

from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse

from src.modules.pilot_intake.schemas import (
    CreatePilotDecisionRequest,
    PilotMetricEvidence,
    RegisterPilotCaseRequest,
)
from src.modules.pilot_intake.service import (
    compose_data_quality_summary,
    create_decision,
    list_cases,
    list_decisions,
    register_case,
)
from src.modules.ui.router import _error, _render
from src.shared.errors import AppError
from src.shared.security.auth import get_current_user_from_request

router = APIRouter()


def _split_values(raw: str) -> list[str]:
    normalized = raw.replace("\n", ",")
    return sorted({item.strip() for item in normalized.split(",") if item.strip()})


@router.get("/ui/projects/{project_id}/pilot-intake", include_in_schema=False)
def ui_pilot_intake(request: Request, project_id: str):
    try:
        cases = list_cases(project_id)
        summary = compose_data_quality_summary(project_id)
        histories = {case.id: list_decisions(project_id, case.id) for case in cases}
    except AppError as exc:
        return _error(request, exc.message)
    return _render(
        request,
        "pilot_intake/dashboard.html",
        project_id=project_id,
        cases=cases,
        summary=summary,
        histories=histories,
        saved=request.query_params.get("saved") == "1",
    )


@router.post("/ui/projects/{project_id}/pilot-intake/cases", include_in_schema=False)
def ui_register_case(
    request: Request,
    project_id: str,
    case_key: str = Form(...),
    import_session_id: str = Form(...),
    initial_state: str = Form(...),
    source_linkage_confidence: str = Form(...),
    requested_linkage_confidence: str = Form(default=""),
    asset_references: str = Form(default=""),
    data_quality_run_ids: str = Form(default=""),
    impressions: int | None = Form(default=None),
    clicks: int | None = Form(default=None),
    rate: float | None = Form(default=None),
    decision_reason: str = Form(default="case_registered"),
):
    try:
        body = RegisterPilotCaseRequest(
            case_key=case_key,
            import_session_id=import_session_id,
            initial_state=initial_state,
            source_linkage_confidence=source_linkage_confidence,
            requested_linkage_confidence=requested_linkage_confidence or None,
            asset_references=_split_values(asset_references),
            data_quality_run_ids=_split_values(data_quality_run_ids),
            metrics=PilotMetricEvidence(
                impressions=impressions,
                clicks=clicks,
                rate=rate,
            ),
            provenance={"source": "pilot_intake_ui", "synthetic_or_local": True},
            decision_reason=decision_reason,
        )
        register_case(
            project_id,
            body,
            user=get_current_user_from_request(request),
        )
    except (AppError, ValueError) as exc:
        return _error(request, exc.message if isinstance(exc, AppError) else str(exc))
    return RedirectResponse(
        url=f"/ui/projects/{project_id}/pilot-intake?saved=1",
        status_code=303,
    )


@router.post(
    "/ui/projects/{project_id}/pilot-intake/cases/{case_id}/decisions",
    include_in_schema=False,
)
def ui_record_decision(
    request: Request,
    project_id: str,
    case_id: str,
    state: str = Form(...),
    reason: str = Form(...),
):
    try:
        create_decision(
            project_id,
            case_id,
            CreatePilotDecisionRequest(state=state, reason=reason),
            user=get_current_user_from_request(request),
        )
    except (AppError, ValueError) as exc:
        return _error(request, exc.message if isinstance(exc, AppError) else str(exc))
    return RedirectResponse(
        url=f"/ui/projects/{project_id}/pilot-intake?saved=1",
        status_code=303,
    )
