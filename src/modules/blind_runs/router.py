from __future__ import annotations

import hashlib

from fastapi import APIRouter, Request
from fastapi.responses import Response

from src.modules.audit_log.service import write_audit_event
from src.modules.blind_runs.schemas import (
    BlindDiagnosticRevisionResponse,
    FreezeDiagnosticRevisionRequest,
    OutcomeEnvelopeMetadataResponse,
    RecordOutcomeEnvelopeRequest,
    RevealedOutcomeEnvelopeResponse,
)
from src.modules.blind_runs.service import (
    export_json_bytes,
    freeze_diagnostic_revision,
    get_outcome_envelope_metadata,
    get_revision,
    list_case_revisions,
    record_outcome_envelope,
    reveal_outcome_envelope,
)
from src.shared.security.auth import get_current_user_from_request

router = APIRouter(prefix="/blind-runs", tags=["blind-runs"])


def _user(request: Request) -> dict:
    return get_current_user_from_request(request)


@router.post(
    "/projects/{project_id}/cases/{case_id}/revisions",
    response_model=BlindDiagnosticRevisionResponse,
    status_code=201,
)
def post_diagnostic_revision(
    project_id: str,
    case_id: str,
    body: FreezeDiagnosticRevisionRequest,
    request: Request,
):
    result = freeze_diagnostic_revision(
        project_id,
        case_id,
        body,
        user=_user(request),
    )
    write_audit_event(
        "blind_diagnostic_revision_frozen",
        "blind_diagnostic_revision",
        result.id,
        {
            "project_id": project_id,
            "pilot_case_id": case_id,
            "case_key": result.case_key,
            "revision_number": result.revision_number,
            "execution_id": result.execution_id,
            "revision_sha256": result.revision_sha256,
            "diagnostic_output_sha256": result.diagnostic_output_sha256,
            "input_provenance_sha256": result.input_provenance_sha256,
            "prompt_manifest_sha256": result.prompt_manifest_sha256,
            "model_profile_sha256": result.model_profile_sha256,
            "code_revision": result.code_revision,
        },
    )
    return result


@router.get(
    "/projects/{project_id}/cases/{case_id}/revisions",
    response_model=list[BlindDiagnosticRevisionResponse],
)
def get_case_revisions(project_id: str, case_id: str):
    return list_case_revisions(project_id, case_id)


@router.get(
    "/projects/{project_id}/cases/{case_id}/revisions/{revision_id}",
    response_model=BlindDiagnosticRevisionResponse,
)
def get_case_revision(project_id: str, case_id: str, revision_id: str):
    return get_revision(project_id, case_id, revision_id)


@router.post(
    "/projects/{project_id}/cases/{case_id}/outcome-envelope",
    response_model=OutcomeEnvelopeMetadataResponse,
    status_code=201,
)
def post_outcome_envelope(
    project_id: str,
    case_id: str,
    body: RecordOutcomeEnvelopeRequest,
    request: Request,
):
    result = record_outcome_envelope(
        project_id,
        case_id,
        body,
        user=_user(request),
    )
    write_audit_event(
        "blind_outcome_envelope_recorded",
        "blind_outcome_envelope",
        result.id,
        {
            "project_id": project_id,
            "pilot_case_id": case_id,
            "case_key": result.case_key,
            "outcome_schema_version": result.outcome_schema_version,
            "outcome_payload_sha256": result.outcome_payload_sha256,
            "provenance_sha256": result.provenance_sha256,
            "plaintext_logged": False,
        },
    )
    return result


@router.get(
    "/projects/{project_id}/cases/{case_id}/outcome-envelope",
    response_model=OutcomeEnvelopeMetadataResponse,
)
def get_outcome_envelope(project_id: str, case_id: str, request: Request):
    return get_outcome_envelope_metadata(
        project_id,
        case_id,
        user=_user(request),
    )


@router.get(
    "/projects/{project_id}/cases/{case_id}/outcome-envelope/reveal",
    response_model=RevealedOutcomeEnvelopeResponse,
)
def reveal_outcome(
    project_id: str,
    case_id: str,
    request: Request,
):
    result = reveal_outcome_envelope(
        project_id,
        case_id,
        user=_user(request),
    )
    write_audit_event(
        "blind_outcome_envelope_revealed",
        "blind_outcome_envelope",
        result.id,
        {
            "project_id": project_id,
            "pilot_case_id": case_id,
            "case_key": result.case_key,
            "outcome_payload_sha256": result.outcome_payload_sha256,
            "plaintext_logged": False,
        },
    )
    return result


@router.get("/projects/{project_id}/export.json")
def export_blind_revisions(project_id: str):
    data = export_json_bytes(project_id)
    return Response(
        content=data,
        media_type="application/json",
        headers={
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
            "X-Blind-Run-SHA256": hashlib.sha256(data).hexdigest(),
        },
    )
