from __future__ import annotations

import hashlib
import io
import json

from fastapi import APIRouter, Query, Request
from fastapi.responses import Response, StreamingResponse

from src.modules.calibration_dashboard.schemas import (
    CalibrationCaseResponse,
    CalibrationDashboardResponse,
    CreateWorkflowMeasurementRequest,
    EvidenceFilter,
    UpsertCalibrationCaseRequest,
    WorkflowMeasurementResponse,
)
from src.modules.calibration_dashboard.service import (
    compose_dashboard,
    create_workflow_measurement,
    dashboard_json_bytes,
    dashboard_xlsx_bytes,
    export_manifest,
    list_case_evidence,
    list_workflow_measurements,
    upsert_case_evidence,
)
from src.shared.security.auth import get_current_user_from_request

router = APIRouter(prefix="/calibration-dashboard", tags=["calibration-dashboard"])


def _writer(request: Request) -> dict:
    user = get_current_user_from_request(request)
    if user.get("role") not in {"admin", "manager", "analyst"}:
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="Write permission required")
    return user


@router.get("/projects/{project_id}", response_model=CalibrationDashboardResponse)
def get_dashboard(
    project_id: str,
    evidence_filter: EvidenceFilter = Query(default="all"),
):
    return compose_dashboard(project_id, evidence_filter=evidence_filter)


@router.get("/projects/{project_id}/cases", response_model=list[CalibrationCaseResponse])
def get_cases(project_id: str):
    return list_case_evidence(project_id)


@router.put("/projects/{project_id}/cases/{case_id}", response_model=CalibrationCaseResponse)
def put_case(
    project_id: str,
    case_id: str,
    body: UpsertCalibrationCaseRequest,
    request: Request,
):
    return upsert_case_evidence(project_id, case_id, body, user=_writer(request))


@router.get(
    "/projects/{project_id}/workflow-measurements",
    response_model=list[WorkflowMeasurementResponse],
)
def get_workflow_measurements(project_id: str):
    return list_workflow_measurements(project_id)


@router.post(
    "/projects/{project_id}/workflow-measurements",
    response_model=WorkflowMeasurementResponse,
    status_code=201,
)
def post_workflow_measurement(
    project_id: str,
    body: CreateWorkflowMeasurementRequest,
    request: Request,
):
    return create_workflow_measurement(project_id, body, user=_writer(request))


@router.get("/projects/{project_id}/export.json")
def export_json(project_id: str, evidence_filter: EvidenceFilter = Query(default="all")):
    data = dashboard_json_bytes(project_id, evidence_filter=evidence_filter)
    return Response(
        content=data,
        media_type="application/json",
        headers={
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
            "X-Calibration-Payload-SHA256": hashlib.sha256(data).hexdigest(),
        },
    )


@router.get("/projects/{project_id}/manifest.json")
def export_project_manifest(
    project_id: str,
    evidence_filter: EvidenceFilter = Query(default="all"),
):
    payload = export_manifest(project_id, evidence_filter=evidence_filter)
    data = (json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode(
        "utf-8"
    )
    return Response(
        content=data,
        media_type="application/json",
        headers={
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
            "X-Calibration-Payload-SHA256": hashlib.sha256(data).hexdigest(),
        },
    )


@router.get("/projects/{project_id}/export.xlsx")
def export_xlsx(project_id: str, evidence_filter: EvidenceFilter = Query(default="all")):
    data = dashboard_xlsx_bytes(project_id, evidence_filter=evidence_filter)
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in project_id)[:80]
    safe = safe or "project"
    return StreamingResponse(
        io.BytesIO(data),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f'attachment; filename="calibration-dashboard-{safe}.xlsx"',
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
            "X-Calibration-Payload-SHA256": hashlib.sha256(data).hexdigest(),
        },
    )
