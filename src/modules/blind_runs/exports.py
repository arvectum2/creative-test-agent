from __future__ import annotations

from typing import Any

from src.modules.blind_runs.models import BlindDiagnosticRevision
from src.modules.blind_runs.support import (
    SCHEMA_VERSION,
    canonical_json,
    ensure_project,
    revision_response,
)
from src.shared.db.repository import db_session


def export_payload(project_id: str) -> dict[str, Any]:
    with db_session() as db:
        ensure_project(db, project_id)
        rows = (
            db.query(BlindDiagnosticRevision)
            .filter(BlindDiagnosticRevision.project_id == project_id)
            .order_by(
                BlindDiagnosticRevision.case_key.asc(),
                BlindDiagnosticRevision.revision_number.asc(),
                BlindDiagnosticRevision.id.asc(),
            )
            .all()
        )
        revisions = [revision_response(row).model_dump(mode="json") for row in rows]
    return {
        "schema_version": SCHEMA_VERSION,
        "project_id": project_id,
        "revisions": revisions,
        "claim_boundary": {
            "synthetic_acceptance_only": True,
            "real_controlled_pilot_completed": False,
            "validated_model_accuracy_claimed": False,
            "causal_interpretation_claimed": False,
            "numeric_uplift_prediction_claimed": False,
            "outcome_payload_included": False,
        },
    }


def export_json_bytes(project_id: str) -> bytes:
    return (canonical_json(export_payload(project_id)) + "\n").encode("utf-8")
