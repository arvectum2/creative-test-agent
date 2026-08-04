from __future__ import annotations

from datetime import datetime, timezone

from src.modules.blind_runs.models import BlindOutcomeEnvelope
from src.modules.blind_runs.schemas import (
    OutcomeEnvelopeMetadataResponse,
    RecordOutcomeEnvelopeRequest,
    RevealedOutcomeEnvelopeResponse,
)
from src.modules.blind_runs.support import (
    OUTCOME_CUSTODIAN_ROLES,
    ensure_project,
    get_case_row,
    get_outcome_row,
    hash_value,
    latest_revision,
    load_json,
    outcome_metadata_response,
    require_included_case,
    require_role,
)
from src.shared.db.repository import db_session
from src.shared.errors import AppError


def record_outcome_envelope(
    project_id: str,
    case_id: str,
    body: RecordOutcomeEnvelopeRequest,
    *,
    user: dict | None,
) -> OutcomeEnvelopeMetadataResponse:
    require_role(user, OUTCOME_CUSTODIAN_ROLES, "outcome_custodian_role_required")
    with db_session() as db:
        ensure_project(db, project_id)
        case = get_case_row(db, project_id, case_id)
        require_included_case(case)
        existing = (
            db.query(BlindOutcomeEnvelope)
            .filter(
                BlindOutcomeEnvelope.project_id == project_id,
                BlindOutcomeEnvelope.pilot_case_id == case_id,
            )
            .first()
        )
        if existing is not None:
            raise AppError(
                "outcome_envelope_exists",
                "Outcome envelope already exists and is immutable",
                409,
            )
        payload_json, payload_sha256 = hash_value(body.outcome_payload)
        provenance_json, provenance_sha256 = hash_value(body.provenance)
        now = datetime.now(timezone.utc)
        row = BlindOutcomeEnvelope(
            project_id=project_id,
            pilot_case_id=case.id,
            case_key=case.case_key,
            outcome_schema_version=body.outcome_schema_version,
            outcome_payload_json=payload_json,
            outcome_payload_sha256=payload_sha256,
            provenance_json=provenance_json,
            provenance_sha256=provenance_sha256,
            created_by_user_id=(user or {}).get("user_id"),
            sealed_at=now,
            created_at=now,
        )
        db.add(row)
        db.flush()
        db.refresh(row)
        return outcome_metadata_response(row)


def get_outcome_envelope_metadata(
    project_id: str,
    case_id: str,
    *,
    user: dict | None,
) -> OutcomeEnvelopeMetadataResponse:
    require_role(user, OUTCOME_CUSTODIAN_ROLES, "outcome_custodian_role_required")
    with db_session() as db:
        ensure_project(db, project_id)
        get_case_row(db, project_id, case_id)
        return outcome_metadata_response(get_outcome_row(db, project_id, case_id))


def reveal_outcome_envelope(
    project_id: str,
    case_id: str,
    *,
    user: dict | None,
) -> RevealedOutcomeEnvelopeResponse:
    require_role(user, OUTCOME_CUSTODIAN_ROLES, "outcome_custodian_role_required")
    with db_session() as db:
        ensure_project(db, project_id)
        get_case_row(db, project_id, case_id)
        outcome = get_outcome_row(db, project_id, case_id)
        if latest_revision(db, project_id, case_id) is None:
            raise AppError(
                "outcome_access_before_freeze_forbidden",
                "Outcome plaintext cannot be revealed before a diagnostic revision is frozen",
                409,
            )
        metadata = outcome_metadata_response(outcome)
        return RevealedOutcomeEnvelopeResponse(
            **metadata.model_dump(),
            outcome_payload=load_json(outcome.outcome_payload_json, {}),
            provenance=load_json(outcome.provenance_json, {}),
        )
