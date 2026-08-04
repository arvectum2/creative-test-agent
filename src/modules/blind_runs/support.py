from __future__ import annotations

import hashlib
import json
from typing import Any

from src.modules.blind_runs.models import BlindDiagnosticRevision, BlindOutcomeEnvelope
from src.modules.blind_runs.schemas import (
    BlindDiagnosticRevisionResponse,
    ModelProfileSnapshot,
    OutcomeEnvelopeMetadataResponse,
    PromptVersionSnapshot,
)
from src.modules.model_profiles.models import ModelProfile
from src.modules.pilot_intake.models import PilotCase
from src.modules.projects.models import Project
from src.modules.prompt_registry.models import PromptVersion
from src.shared.errors import AppError

SCHEMA_VERSION = "cta-pilot-prep-002/v1"
DIAGNOSTIC_WRITER_ROLES = {"admin", "manager", "analyst"}
OUTCOME_CUSTODIAN_ROLES = {"admin", "manager"}
_RESERVED_OUTCOME_KEYS = {
    "actual_outcome",
    "actual_result",
    "campaign_outcome",
    "ground_truth",
    "observed_outcome",
    "observed_result",
    "outcome",
    "outcome_fields",
    "outcome_payload",
    "outcomes",
    "post_exposure_result",
    "validated_label",
}


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def hash_value(value: Any) -> tuple[str, str]:
    canonical = canonical_json(value)
    return canonical, hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def load_json(value: str | None, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return default


def require_role(user: dict | None, allowed: set[str], code: str) -> None:
    if (user or {}).get("role") not in allowed:
        raise AppError(code, "Role is not permitted for this blind-run operation", 403)


def ensure_project(db, project_id: str) -> Project:
    project = db.query(Project).filter(Project.id == project_id).first()
    if project is None:
        raise AppError("project_not_found", "Project not found", 404)
    return project


def get_case_row(db, project_id: str, case_id: str) -> PilotCase:
    row = (
        db.query(PilotCase)
        .filter(PilotCase.project_id == project_id, PilotCase.id == case_id)
        .first()
    )
    if row is None:
        raise AppError("pilot_case_not_found", "Pilot case not found", 404)
    return row


def require_included_case(row: PilotCase) -> None:
    if row.state != "included":
        raise AppError(
            "pilot_case_not_included",
            "Blind diagnostic revisions require an included pilot case",
            409,
        )


def assert_no_outcome_fields(value: Any, path: str) -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            normalized = str(key).strip().lower().replace("-", "_").replace(" ", "_")
            if normalized in _RESERVED_OUTCOME_KEYS:
                raise AppError(
                    "outcome_field_forbidden",
                    f"Outcome field is forbidden in diagnostic material: {path}.{key}",
                    409,
                )
            assert_no_outcome_fields(nested, f"{path}.{key}")
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            assert_no_outcome_fields(nested, f"{path}[{index}]")


def prompt_manifest(db, prompt_version_ids: list[str]) -> list[dict[str, Any]]:
    rows = db.query(PromptVersion).filter(PromptVersion.id.in_(prompt_version_ids)).all()
    if {row.id for row in rows} != set(prompt_version_ids):
        raise AppError(
            "prompt_version_not_found",
            "One or more prompt versions were not found",
            404,
        )
    manifest: list[dict[str, Any]] = []
    for row in sorted(rows, key=lambda item: (item.stage_name, item.version, item.id)):
        template_hash = (row.template_hash or "").lower()
        if len(template_hash) != 64 or any(
            char not in "0123456789abcdef" for char in template_hash
        ):
            raise AppError(
                "prompt_hash_invalid",
                f"Prompt version {row.id} does not have a valid SHA-256 hash",
                409,
            )
        manifest.append(
            {
                "id": row.id,
                "stage_name": row.stage_name,
                "version": row.version,
                "template_path": row.template_path,
                "template_hash": template_hash,
                "metadata": load_json(row.metadata_json, None),
            }
        )
    return manifest


def model_profile_snapshot(db, model_profile_id: str) -> dict[str, Any]:
    row = db.query(ModelProfile).filter(ModelProfile.id == model_profile_id).first()
    if row is None:
        raise AppError("model_profile_not_found", "Model profile not found", 404)
    return {
        "id": row.id,
        "profile_name": row.profile_name,
        "provider": row.provider,
        "model": row.model,
        "base_url": row.base_url,
        "enabled": bool(row.enabled),
        "default_for_demo": bool(row.default_for_demo),
        "timeout_seconds": row.timeout_seconds,
        "metadata": load_json(row.metadata_json, None),
    }


def input_provenance_snapshot(row: PilotCase) -> dict[str, Any]:
    _, case_provenance_sha256 = hash_value(load_json(row.provenance_json, {}))
    return {
        "policy": "blind-diagnostic-input/v1",
        "project_id": row.project_id,
        "pilot_case_id": row.id,
        "case_key": row.case_key,
        "import_session_id": row.import_session_id,
        "source_package_sha256": row.source_package_sha256,
        "source_files": load_json(row.source_files_json, []),
        "case_provenance_sha256": case_provenance_sha256,
        "source_linkage_confidence": row.source_linkage_confidence,
        "linkage_confidence": row.linkage_confidence,
        "asset_references": load_json(row.asset_references_json, []),
        "data_quality": load_json(row.data_quality_snapshot_json, {}),
        "excluded_from_diagnostic_snapshot": [
            "reported_impressions",
            "reported_clicks",
            "reported_rate",
            "case_provenance_plaintext",
            "outcome_fields",
        ],
    }


def latest_revision(db, project_id: str, case_id: str) -> BlindDiagnosticRevision | None:
    return (
        db.query(BlindDiagnosticRevision)
        .filter(
            BlindDiagnosticRevision.project_id == project_id,
            BlindDiagnosticRevision.pilot_case_id == case_id,
        )
        .order_by(BlindDiagnosticRevision.revision_number.desc())
        .first()
    )


def get_outcome_row(db, project_id: str, case_id: str) -> BlindOutcomeEnvelope:
    row = (
        db.query(BlindOutcomeEnvelope)
        .filter(
            BlindOutcomeEnvelope.project_id == project_id,
            BlindOutcomeEnvelope.pilot_case_id == case_id,
        )
        .first()
    )
    if row is None:
        raise AppError("outcome_envelope_not_found", "Outcome envelope not found", 404)
    return row


def revision_response(row: BlindDiagnosticRevision) -> BlindDiagnosticRevisionResponse:
    return BlindDiagnosticRevisionResponse(
        id=row.id,
        project_id=row.project_id,
        pilot_case_id=row.pilot_case_id,
        case_key=row.case_key,
        revision_number=row.revision_number,
        execution_id=row.execution_id,
        supersedes_revision_id=row.supersedes_revision_id,
        previous_revision_sha256=row.previous_revision_sha256,
        diagnostic_output=load_json(row.diagnostic_output_json, {}),
        diagnostic_output_sha256=row.diagnostic_output_sha256,
        input_provenance=load_json(row.input_provenance_json, {}),
        input_provenance_sha256=row.input_provenance_sha256,
        prompt_manifest=[
            PromptVersionSnapshot.model_validate(item)
            for item in load_json(row.prompt_manifest_json, [])
        ],
        prompt_manifest_sha256=row.prompt_manifest_sha256,
        model_profile=ModelProfileSnapshot.model_validate(
            load_json(row.model_profile_json, {})
        ),
        model_profile_sha256=row.model_profile_sha256,
        code_revision=row.code_revision,
        execution_metadata=load_json(row.execution_metadata_json, {}),
        execution_metadata_sha256=row.execution_metadata_sha256,
        revision_manifest=load_json(row.revision_manifest_json, {}),
        revision_sha256=row.revision_sha256,
        created_by_user_id=row.created_by_user_id,
        frozen_at=row.frozen_at,
        created_at=row.created_at,
    )


def outcome_metadata_response(row: BlindOutcomeEnvelope) -> OutcomeEnvelopeMetadataResponse:
    return OutcomeEnvelopeMetadataResponse(
        id=row.id,
        project_id=row.project_id,
        pilot_case_id=row.pilot_case_id,
        case_key=row.case_key,
        outcome_schema_version=row.outcome_schema_version,
        outcome_payload_sha256=row.outcome_payload_sha256,
        provenance_sha256=row.provenance_sha256,
        created_by_user_id=row.created_by_user_id,
        sealed_at=row.sealed_at,
        created_at=row.created_at,
    )
