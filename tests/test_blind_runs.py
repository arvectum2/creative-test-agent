from __future__ import annotations

import copy
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from src.main import app
from src.modules.blind_runs.models import BlindDiagnosticRevision, BlindOutcomeEnvelope
from src.modules.model_profiles.models import ModelProfile
from src.modules.pilot_intake.models import PilotCase
from src.modules.projects.models import Project
from src.modules.prompt_registry.models import PromptVersion
from src.shared.db.repository import db_session

FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures" / "blind_runs" / "cases.json").read_text(
        encoding="utf-8"
    )
)
CODE_REVISION = "a" * 40


def _set_role(monkeypatch, role: str) -> None:
    import src.modules.blind_runs.router as blind_router

    monkeypatch.setattr(
        blind_router,
        "get_current_user_from_request",
        lambda _request: {
            "user_id": f"synthetic-{role}",
            "role": role,
            "display_name": f"Synthetic {role}",
            "is_active": True,
        },
    )


def _seed_context(project_id: str, *, state: str = "included") -> tuple[str, list[str], str]:
    case_id = f"case-{uuid4()}"
    prompt_ids = [f"prompt-summary-{uuid4()}", f"prompt-safety-{uuid4()}"]
    model_profile_id = f"model-profile-{uuid4()}"
    source_hash = hashlib.sha256(f"source-{project_id}".encode()).hexdigest()
    package_hash = hashlib.sha256(f"package-{project_id}".encode()).hexdigest()
    now = datetime.now(timezone.utc)
    with db_session() as db:
        db.add(
            Project(
                id=project_id,
                client_id=f"client-{project_id}",
                name=f"Synthetic blind run {project_id}",
                status="active",
            )
        )
        db.add(
            PilotCase(
                id=case_id,
                project_id=project_id,
                case_key=f"SYN-BLIND-{project_id[-8:]}",
                import_session_id=f"import-{uuid4()}",
                state=state,
                source_package_sha256=package_hash,
                source_files_json=json.dumps(
                    [
                        {
                            "source_file_id": f"file-{uuid4()}",
                            "original_filename": "synthetic-creative.txt",
                            "file_size_bytes": 128,
                            "sha256": source_hash,
                        }
                    ],
                    sort_keys=True,
                ),
                provenance_json=json.dumps(
                    {
                        "synthetic": True,
                        "outcome_payload": {
                            "actual_result": "SYNTHETIC-SECRET-OUTCOME-731"
                        },
                    },
                    sort_keys=True,
                ),
                source_linkage_confidence="exact",
                linkage_confidence="exact",
                asset_references_json=json.dumps(["synthetic-asset-001"]),
                asset_count=1,
                reported_impressions=1000,
                reported_clicks=40,
                reported_rate=0.04,
                data_quality_snapshot_json=json.dumps(
                    {
                        "overall_status": "passed",
                        "run_count": 1,
                        "confirmed_mapping_count": 2,
                        "suggested_mapping_count": 0,
                        "rejected_mapping_count": 0,
                        "unmapped_mapping_count": 0,
                        "warning_issue_count": 0,
                        "blocking_issue_count": 0,
                        "total_issue_count": 0,
                        "runs": [],
                    },
                    sort_keys=True,
                ),
                data_quality_run_count=1,
                overall_data_quality_status="passed",
                warning_issue_count=0,
                blocking_issue_count=0,
                created_by_user_id="synthetic-manager",
                updated_by_user_id="synthetic-manager",
                created_at=now,
                updated_at=now,
            )
        )
        db.add_all(
            [
                PromptVersion(
                    id=prompt_ids[0],
                    stage_name="summary",
                    version="synthetic-v1",
                    template_path="synthetic/prompts/summary.txt",
                    template_hash=hashlib.sha256(b"synthetic-summary").hexdigest(),
                    is_active=True,
                    metadata_json=json.dumps({"synthetic": True}),
                ),
                PromptVersion(
                    id=prompt_ids[1],
                    stage_name="safety",
                    version="synthetic-v2",
                    template_path="synthetic/prompts/safety.txt",
                    template_hash=hashlib.sha256(b"synthetic-safety").hexdigest(),
                    is_active=True,
                    metadata_json=json.dumps({"synthetic": True}),
                ),
            ]
        )
        db.add(
            ModelProfile(
                id=model_profile_id,
                profile_name=f"synthetic-blind-{uuid4()}",
                provider="stub",
                model="synthetic-local-model",
                base_url="http://127.0.0.1:1",
                enabled=True,
                default_for_demo=False,
                timeout_seconds=30,
                metadata_json=json.dumps(
                    {"profile_version": "synthetic-1", "local_only": True}
                ),
                notes="synthetic fixture only",
            )
        )
    return case_id, prompt_ids, model_profile_id


def _revision_body(
    execution_id: str,
    prompt_ids: list[str],
    model_profile_id: str,
    *,
    output: dict | None = None,
) -> dict:
    return {
        "execution_id": execution_id,
        "diagnostic_output": copy.deepcopy(output or FIXTURE["diagnostic_output"]),
        "prompt_version_ids": list(reversed(prompt_ids)),
        "model_profile_id": model_profile_id,
        "code_revision": CODE_REVISION,
        "execution_metadata": {
            "synthetic": True,
            "runtime": "stub",
            "attempt": execution_id,
        },
    }


def test_frozen_revision_is_immutable_replay_safe_and_append_only(monkeypatch):
    project_id = f"blind-freeze-{uuid4()}"
    case_id, prompt_ids, model_profile_id = _seed_context(project_id)
    _set_role(monkeypatch, "analyst")
    client = TestClient(app)

    body = _revision_body("synthetic-execution-001", prompt_ids, model_profile_id)
    first_response = client.post(
        f"/blind-runs/projects/{project_id}/cases/{case_id}/revisions",
        json=body,
    )
    assert first_response.status_code == 201, first_response.text
    first = first_response.json()
    assert first["revision_number"] == 1
    assert first["supersedes_revision_id"] is None
    assert first["previous_revision_sha256"] is None
    assert len(first["revision_sha256"]) == 64
    assert len(first["diagnostic_output_sha256"]) == 64
    assert len(first["input_provenance_sha256"]) == 64
    assert len(first["prompt_manifest_sha256"]) == 64
    assert len(first["model_profile_sha256"]) == 64
    assert len(first["execution_metadata_sha256"]) == 64
    assert [item["stage_name"] for item in first["prompt_manifest"]] == [
        "safety",
        "summary",
    ]
    assert first["model_profile"]["metadata"]["profile_version"] == "synthetic-1"
    assert first["input_provenance"]["source_package_sha256"]
    assert "reported_impressions" not in first["input_provenance"]
    assert "case_provenance_plaintext" not in first["input_provenance"]
    assert "SYNTHETIC-SECRET-OUTCOME-731" not in first_response.text

    replay = client.post(
        f"/blind-runs/projects/{project_id}/cases/{case_id}/revisions",
        json=body,
    )
    assert replay.status_code == 409
    assert "already frozen" in replay.text

    rerun_body = _revision_body(
        "synthetic-execution-002",
        prompt_ids,
        model_profile_id,
        output=FIXTURE["rerun_output"],
    )
    second_response = client.post(
        f"/blind-runs/projects/{project_id}/cases/{case_id}/revisions",
        json=rerun_body,
    )
    assert second_response.status_code == 201, second_response.text
    second = second_response.json()
    assert second["revision_number"] == 2
    assert second["supersedes_revision_id"] == first["id"]
    assert second["previous_revision_sha256"] == first["revision_sha256"]
    assert second["revision_sha256"] != first["revision_sha256"]

    history = client.get(
        f"/blind-runs/projects/{project_id}/cases/{case_id}/revisions"
    )
    assert history.status_code == 200
    assert [item["revision_number"] for item in history.json()] == [1, 2]
    assert history.json()[0]["revision_sha256"] == first["revision_sha256"]

    with pytest.raises(RuntimeError, match="frozen and append-only"):
        with db_session() as db:
            row = (
                db.query(BlindDiagnosticRevision)
                .filter(BlindDiagnosticRevision.id == first["id"])
                .one()
            )
            row.diagnostic_output_json = json.dumps({"mutated": True})

    with pytest.raises(RuntimeError, match="cannot be deleted"):
        with db_session() as db:
            row = (
                db.query(BlindDiagnosticRevision)
                .filter(BlindDiagnosticRevision.id == first["id"])
                .one()
            )
            db.delete(row)

    first_export = client.get(f"/blind-runs/projects/{project_id}/export.json")
    second_export = client.get(f"/blind-runs/projects/{project_id}/export.json")
    assert first_export.status_code == 200
    assert first_export.content == second_export.content
    assert first_export.headers["x-blind-run-sha256"] == hashlib.sha256(
        first_export.content
    ).hexdigest()
    exported = first_export.json()
    assert [item["revision_number"] for item in exported["revisions"]] == [1, 2]
    assert exported["revisions"][0]["revision_manifest"]["code_revision"] == CODE_REVISION
    assert exported["revisions"][1]["previous_revision_sha256"] == first["revision_sha256"]
    assert exported["claim_boundary"]["outcome_payload_included"] is False
    assert "SYNTHETIC-SECRET-OUTCOME-731" not in first_export.text


def test_outcome_envelope_cannot_leak_before_freeze_or_to_analyst(monkeypatch):
    project_id = f"blind-leakage-{uuid4()}"
    case_id, prompt_ids, model_profile_id = _seed_context(project_id)
    client = TestClient(app)

    _set_role(monkeypatch, "manager")
    outcome_response = client.post(
        f"/blind-runs/projects/{project_id}/cases/{case_id}/outcome-envelope",
        json={
            "outcome_schema_version": "synthetic-outcome/v1",
            "outcome_payload": FIXTURE["outcome_payload"],
            "provenance": {"synthetic": True, "source": "fixture"},
        },
    )
    assert outcome_response.status_code == 201, outcome_response.text
    outcome_metadata = outcome_response.json()
    assert "outcome_payload" not in outcome_metadata
    assert len(outcome_metadata["outcome_payload_sha256"]) == 64
    assert "SYNTHETIC-SECRET-OUTCOME-731" not in outcome_response.text

    before_freeze = client.get(
        f"/blind-runs/projects/{project_id}/cases/{case_id}/outcome-envelope/reveal"
    )
    assert before_freeze.status_code == 409
    assert "before a diagnostic revision is frozen" in before_freeze.text

    _set_role(monkeypatch, "analyst")
    assert (
        client.get(
            f"/blind-runs/projects/{project_id}/cases/{case_id}/outcome-envelope"
        ).status_code
        == 403
    )
    assert (
        client.get(
            f"/blind-runs/projects/{project_id}/cases/{case_id}/outcome-envelope/reveal"
        ).status_code
        == 403
    )

    leaked_request = _revision_body(
        "synthetic-leak-attempt",
        prompt_ids,
        model_profile_id,
    )
    leaked_request["outcome_payload"] = FIXTURE["outcome_payload"]
    rejected = client.post(
        f"/blind-runs/projects/{project_id}/cases/{case_id}/revisions",
        json=leaked_request,
    )
    assert rejected.status_code == 422

    metadata_leak = _revision_body(
        "synthetic-metadata-leak",
        prompt_ids,
        model_profile_id,
    )
    metadata_leak["execution_metadata"]["ground_truth"] = "forbidden"
    rejected_metadata = client.post(
        f"/blind-runs/projects/{project_id}/cases/{case_id}/revisions",
        json=metadata_leak,
    )
    assert rejected_metadata.status_code == 409
    assert "Outcome field is forbidden" in rejected_metadata.text

    output_leak = _revision_body(
        "synthetic-output-leak",
        prompt_ids,
        model_profile_id,
    )
    output_leak["diagnostic_output"]["ground_truth"] = "forbidden"
    rejected_output = client.post(
        f"/blind-runs/projects/{project_id}/cases/{case_id}/revisions",
        json=output_leak,
    )
    assert rejected_output.status_code == 409
    assert "diagnostic_output.ground_truth" in rejected_output.text

    frozen_response = client.post(
        f"/blind-runs/projects/{project_id}/cases/{case_id}/revisions",
        json=_revision_body("synthetic-freeze", prompt_ids, model_profile_id),
    )
    assert frozen_response.status_code == 201
    assert "SYNTHETIC-SECRET-OUTCOME-731" not in frozen_response.text

    assert (
        client.get(
            f"/blind-runs/projects/{project_id}/cases/{case_id}/outcome-envelope/reveal"
        ).status_code
        == 403
    )

    diagnostic_export = client.get(f"/blind-runs/projects/{project_id}/export.json")
    assert diagnostic_export.status_code == 200
    assert "SYNTHETIC-SECRET-OUTCOME-731" not in diagnostic_export.text
    assert all("outcome_payload" not in item for item in diagnostic_export.json()["revisions"])

    _set_role(monkeypatch, "manager")
    revealed = client.get(
        f"/blind-runs/projects/{project_id}/cases/{case_id}/outcome-envelope/reveal"
    )
    assert revealed.status_code == 200, revealed.text
    assert revealed.json()["outcome_payload"] == FIXTURE["outcome_payload"]

    with pytest.raises(RuntimeError, match="sealed and immutable"):
        with db_session() as db:
            row = (
                db.query(BlindOutcomeEnvelope)
                .filter(BlindOutcomeEnvelope.id == outcome_metadata["id"])
                .one()
            )
            row.outcome_payload_json = json.dumps({"mutated": True})


def test_blind_run_routes_are_project_scoped(monkeypatch):
    project_a = f"blind-project-a-{uuid4()}"
    project_b = f"blind-project-b-{uuid4()}"
    case_a, prompts_a, profile_a = _seed_context(project_a)
    case_b, _, _ = _seed_context(project_b)
    _set_role(monkeypatch, "analyst")
    client = TestClient(app)

    created = client.post(
        f"/blind-runs/projects/{project_a}/cases/{case_a}/revisions",
        json=_revision_body("shared-execution-id", prompts_a, profile_a),
    )
    assert created.status_code == 201
    revision_id = created.json()["id"]

    assert (
        client.get(
            f"/blind-runs/projects/{project_b}/cases/{case_a}/revisions"
        ).status_code
        == 404
    )
    assert (
        client.get(
            f"/blind-runs/projects/{project_b}/cases/{case_b}/revisions/{revision_id}"
        ).status_code
        == 404
    )

    cross_project_prompt = _revision_body(
        "cross-project-attempt",
        prompts_a,
        profile_a,
    )
    response = client.post(
        f"/blind-runs/projects/{project_b}/cases/{case_a}/revisions",
        json=cross_project_prompt,
    )
    assert response.status_code == 404
