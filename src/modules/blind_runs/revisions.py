from __future__ import annotations

from datetime import datetime, timezone

from src.modules.blind_runs.models import BlindDiagnosticRevision
from src.modules.blind_runs.schemas import (
    BlindDiagnosticRevisionResponse,
    FreezeDiagnosticRevisionRequest,
)
from src.modules.blind_runs.support import (
    DIAGNOSTIC_WRITER_ROLES,
    SCHEMA_VERSION,
    assert_no_outcome_fields,
    ensure_project,
    get_case_row,
    hash_value,
    input_provenance_snapshot,
    latest_revision,
    model_profile_snapshot,
    prompt_manifest,
    require_included_case,
    require_role,
    revision_response,
)
from src.shared.db.repository import db_session
from src.shared.errors import AppError


def freeze_diagnostic_revision(
    project_id: str,
    case_id: str,
    body: FreezeDiagnosticRevisionRequest,
    *,
    user: dict | None,
) -> BlindDiagnosticRevisionResponse:
    require_role(user, DIAGNOSTIC_WRITER_ROLES, "diagnostic_role_required")
    assert_no_outcome_fields(body.diagnostic_output, "diagnostic_output")
    assert_no_outcome_fields(body.execution_metadata, "execution_metadata")
    with db_session() as db:
        ensure_project(db, project_id)
        case = get_case_row(db, project_id, case_id)
        require_included_case(case)

        replay = (
            db.query(BlindDiagnosticRevision)
            .filter(
                BlindDiagnosticRevision.project_id == project_id,
                BlindDiagnosticRevision.pilot_case_id == case_id,
                BlindDiagnosticRevision.execution_id == body.execution_id,
            )
            .first()
        )
        if replay is not None:
            raise AppError(
                "blind_run_replay_detected",
                "Execution identifier was already frozen; use a new identifier for a rerun",
                409,
            )

        previous = latest_revision(db, project_id, case_id)
        revision_number = 1 if previous is None else previous.revision_number + 1
        prompts = prompt_manifest(db, body.prompt_version_ids)
        model_profile = model_profile_snapshot(db, body.model_profile_id)
        input_provenance = input_provenance_snapshot(case)
        assert_no_outcome_fields(prompts, "prompt_manifest")
        assert_no_outcome_fields(model_profile, "model_profile")
        assert_no_outcome_fields(input_provenance, "input_provenance")

        output_json, output_sha256 = hash_value(body.diagnostic_output)
        input_json, input_sha256 = hash_value(input_provenance)
        prompt_json, prompt_sha256 = hash_value(prompts)
        model_json, model_sha256 = hash_value(model_profile)
        metadata_json, metadata_sha256 = hash_value(body.execution_metadata)
        manifest = {
            "schema_version": SCHEMA_VERSION,
            "project_id": project_id,
            "pilot_case_id": case.id,
            "case_key": case.case_key,
            "revision_number": revision_number,
            "execution_id": body.execution_id,
            "supersedes_revision_id": previous.id if previous else None,
            "previous_revision_sha256": previous.revision_sha256 if previous else None,
            "diagnostic_output_sha256": output_sha256,
            "input_provenance_sha256": input_sha256,
            "prompt_manifest_sha256": prompt_sha256,
            "model_profile_sha256": model_sha256,
            "code_revision": body.code_revision,
            "execution_metadata_sha256": metadata_sha256,
        }
        manifest_json, revision_sha256 = hash_value(manifest)
        now = datetime.now(timezone.utc)
        row = BlindDiagnosticRevision(
            project_id=project_id,
            pilot_case_id=case.id,
            case_key=case.case_key,
            revision_number=revision_number,
            execution_id=body.execution_id,
            supersedes_revision_id=previous.id if previous else None,
            previous_revision_sha256=previous.revision_sha256 if previous else None,
            diagnostic_output_json=output_json,
            diagnostic_output_sha256=output_sha256,
            input_provenance_json=input_json,
            input_provenance_sha256=input_sha256,
            prompt_manifest_json=prompt_json,
            prompt_manifest_sha256=prompt_sha256,
            model_profile_json=model_json,
            model_profile_sha256=model_sha256,
            code_revision=body.code_revision,
            execution_metadata_json=metadata_json,
            execution_metadata_sha256=metadata_sha256,
            revision_manifest_json=manifest_json,
            revision_sha256=revision_sha256,
            created_by_user_id=(user or {}).get("user_id"),
            frozen_at=now,
            created_at=now,
        )
        db.add(row)
        db.flush()
        db.refresh(row)
        return revision_response(row)


def list_case_revisions(
    project_id: str,
    case_id: str,
) -> list[BlindDiagnosticRevisionResponse]:
    with db_session() as db:
        ensure_project(db, project_id)
        get_case_row(db, project_id, case_id)
        rows = (
            db.query(BlindDiagnosticRevision)
            .filter(
                BlindDiagnosticRevision.project_id == project_id,
                BlindDiagnosticRevision.pilot_case_id == case_id,
            )
            .order_by(BlindDiagnosticRevision.revision_number.asc())
            .all()
        )
        return [revision_response(row) for row in rows]


def get_revision(
    project_id: str,
    case_id: str,
    revision_id: str,
) -> BlindDiagnosticRevisionResponse:
    with db_session() as db:
        ensure_project(db, project_id)
        get_case_row(db, project_id, case_id)
        row = (
            db.query(BlindDiagnosticRevision)
            .filter(
                BlindDiagnosticRevision.project_id == project_id,
                BlindDiagnosticRevision.pilot_case_id == case_id,
                BlindDiagnosticRevision.id == revision_id,
            )
            .first()
        )
        if row is None:
            raise AppError("blind_revision_not_found", "Blind revision not found", 404)
        return revision_response(row)
