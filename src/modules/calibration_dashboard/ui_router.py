from __future__ import annotations

from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse

from src.modules.calibration_dashboard.schemas import (
    CreateWorkflowMeasurementRequest,
    UpsertCalibrationCaseRequest,
)
from src.modules.calibration_dashboard.service import (
    compose_dashboard,
    create_workflow_measurement,
    list_case_evidence,
    list_workflow_measurements,
    upsert_case_evidence,
)
from src.modules.ui.router import _error, _render
from src.shared.errors import AppError
from src.shared.security.auth import get_current_user_from_request

router = APIRouter()


@router.get("/ui/projects/{project_id}/calibration", include_in_schema=False)
def ui_calibration_dashboard(
    request: Request,
    project_id: str,
    evidence_filter: str = "all",
):
    if evidence_filter not in {"all", "real_client", "synthetic", "unclassified"}:
        evidence_filter = "all"
    try:
        dashboard = compose_dashboard(project_id, evidence_filter=evidence_filter)
        cases = list_case_evidence(project_id)
        selected_case_ids = {item.case_id for item in dashboard.cases}
        measurements = [
            item
            for item in list_workflow_measurements(project_id)
            if item.case_id in selected_case_ids
        ]
    except AppError as exc:
        return _error(request, exc.message)
    return _render(
        request,
        "calibration_dashboard/dashboard.html",
        project_id=project_id,
        dashboard=dashboard,
        classifications={item.case_id: item for item in cases},
        measurements=measurements,
        saved=request.query_params.get("saved") == "1",
    )


@router.post(
    "/ui/projects/{project_id}/calibration/cases/{case_id}",
    include_in_schema=False,
)
def ui_save_case(
    request: Request,
    project_id: str,
    case_id: str,
    evidence_class: str = Form(...),
    inclusion_status: str = Form(...),
    source_reference: str = Form(default=""),
    notes: str = Form(default=""),
):
    try:
        body = UpsertCalibrationCaseRequest(
            evidence_class=evidence_class,
            inclusion_status=inclusion_status,
            source_reference=source_reference or None,
            notes=notes or None,
        )
        upsert_case_evidence(
            project_id,
            case_id,
            body,
            user=get_current_user_from_request(request),
        )
    except (AppError, ValueError) as exc:
        return _error(request, exc.message if isinstance(exc, AppError) else str(exc))
    return RedirectResponse(
        url=f"/ui/projects/{project_id}/calibration?saved=1",
        status_code=303,
    )


@router.post(
    "/ui/projects/{project_id}/calibration/workflow",
    include_in_schema=False,
)
def ui_save_workflow(
    request: Request,
    project_id: str,
    case_id: str = Form(...),
    stage: str = Form(...),
    status: str = Form(...),
    wall_clock_seconds: float = Form(...),
    operator_touch_seconds: float = Form(...),
    manual_action_count: int = Form(...),
    report_version: str = Form(default=""),
    notes: str = Form(default=""),
):
    try:
        body = CreateWorkflowMeasurementRequest(
            case_id=case_id,
            stage=stage,
            status=status,
            wall_clock_seconds=wall_clock_seconds,
            operator_touch_seconds=operator_touch_seconds,
            manual_action_count=manual_action_count,
            report_version=report_version or None,
            notes=notes or None,
        )
        create_workflow_measurement(
            project_id,
            body,
            user=get_current_user_from_request(request),
        )
    except (AppError, ValueError) as exc:
        return _error(request, exc.message if isinstance(exc, AppError) else str(exc))
    return RedirectResponse(
        url=f"/ui/projects/{project_id}/calibration?saved=1",
        status_code=303,
    )
