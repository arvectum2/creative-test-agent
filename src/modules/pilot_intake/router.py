from __future__ import annotations

import hashlib

from fastapi import APIRouter, Request
from fastapi.responses import Response

from src.modules.audit_log.service import write_audit_event
from src.modules.pilot_intake.schemas import (
    CreatePilotDecisionRequest,
    PilotCaseDecisionResponse,
    PilotCaseResponse,
    PilotIntakeDataQualitySummary,
    RegisterPilotCaseRequest,
)
from src.modules.pilot_intake.service import (
    compose_data_quality_summary,
    create_decision,
    export_json_bytes,
    get_case,
    list_cases,
    list_decisions,
    register_case,
)
from src.shared.security.auth import get_current_user_from_request

router = APIRouter(prefix="/pilot-intake", tags=["pilot-intake"])


def _user(request: Request) -> dict:
    return get_current_user_from_request(request)


@router.post(
    "/projects/{project_id}/cases",
    response_model=PilotCaseResponse,
    status_code=201,
)
def post_case(
    project_id: str,
    body: RegisterPilotCaseRequest,
    request: Request,
):
    result = register_case(project_id, body, user=_user(request))
    write_audit_event(
        "pilot_case_registered",
        "pilot_case",
        result.id,
        {
            "project_id": project_id,
            "case_key": result.case_key,
            "state": result.state,
            "source_package_sha256": result.source_package_sha256,
            "source_linkage_confidence": result.source_linkage_confidence,
            "linkage_confidence": result.linkage_confidence,
            "data_quality_status": result.data_quality.overall_status,
        },
    )
    return result


@router.get("/projects/{project_id}/cases", response_model=list[PilotCaseResponse])
def get_cases(project_id: str):
    return list_cases(project_id)


@router.get(
    "/projects/{project_id}/cases/{case_id}",
    response_model=PilotCaseResponse,
)
def get_case_by_id(project_id: str, case_id: str):
    return get_case(project_id, case_id)


@router.post(
    "/projects/{project_id}/cases/{case_id}/decisions",
    response_model=PilotCaseDecisionResponse,
    status_code=201,
)
def post_decision(
    project_id: str,
    case_id: str,
    body: CreatePilotDecisionRequest,
    request: Request,
):
    result = create_decision(project_id, case_id, body, user=_user(request))
    write_audit_event(
        "pilot_case_decision_recorded",
        "pilot_case",
        case_id,
        {
            "project_id": project_id,
            "case_key": result.case_key,
            "sequence": result.sequence,
            "from_state": result.from_state,
            "to_state": result.to_state,
            "reason": result.reason,
        },
    )
    return result


@router.get(
    "/projects/{project_id}/cases/{case_id}/history",
    response_model=list[PilotCaseDecisionResponse],
)
def get_decision_history(project_id: str, case_id: str):
    return list_decisions(project_id, case_id)


@router.get(
    "/projects/{project_id}/data-quality-summary",
    response_model=PilotIntakeDataQualitySummary,
)
def get_data_quality_summary(project_id: str):
    return compose_data_quality_summary(project_id)


@router.get("/projects/{project_id}/export.json")
def export_case_register(project_id: str):
    data = export_json_bytes(project_id)
    return Response(
        content=data,
        media_type="application/json",
        headers={
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
            "X-Pilot-Intake-SHA256": hashlib.sha256(data).hexdigest(),
        },
    )
