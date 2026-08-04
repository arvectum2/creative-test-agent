from __future__ import annotations

import hashlib
import json
from contextlib import ExitStack, contextmanager
from copy import deepcopy
from pathlib import Path
from typing import Any, Iterator
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient

from src.modules.calibration_dashboard import service as dashboard_service
from src.modules.data_quality.models import DataQualityRun
from src.modules.finding_reviews.schemas import (
    CreateFindingAdjudicationRequest,
    CreateFindingReviewRequest,
)
from src.modules.import_sessions.models import ImportSession, ImportSourceFile
from src.modules.model_profiles.models import ModelProfile
from src.modules.projects.models import Project
from src.modules.prompt_registry.models import PromptVersion
from src.shared.db.repository import db_session
from src.shared.errors import AppError

CODE_REVISION = "b" * 40
REVIEWER_A = {
    "user_id": "pilot-rehearsal-reviewer-a",
    "role": "analyst",
    "display_name": "Pilot Rehearsal Reviewer A",
    "is_active": True,
}
REVIEWER_B = {
    "user_id": "pilot-rehearsal-reviewer-b",
    "role": "analyst",
    "display_name": "Pilot Rehearsal Reviewer B",
    "is_active": True,
}
ADJUDICATOR = {
    "user_id": "pilot-rehearsal-adjudicator",
    "role": "manager",
    "display_name": "Pilot Rehearsal Adjudicator",
    "is_active": True,
}
SYSTEM_USER = {
    "user_id": "pilot-rehearsal-system",
    "role": "admin",
    "display_name": "Pilot Rehearsal System",
    "is_active": True,
}


class RehearsalRuntimeError(RuntimeError):
    """Raised when the synthetic full-contour rehearsal fails closed."""


def check(condition: bool, message: str) -> None:
    if not condition:
        raise RehearsalRuntimeError(message)


def expect_status(response, status_code: int, label: str) -> None:
    if response.status_code != status_code:
        raise RehearsalRuntimeError(
            f"{label}: expected HTTP {status_code}, got {response.status_code}: "
            f"{response.text[:1000]}"
        )


def create_project(project_id: str) -> None:
    with db_session() as db:
        db.add(
            Project(
                id=project_id,
                client_id=f"client-{project_id}",
                name=f"Synthetic controlled pilot {project_id}",
                status="active",
            )
        )


def seed_import(project_id: str, fixture: dict[str, Any]) -> tuple[str, str]:
    session_id = f"session-{fixture['name']}-{uuid4()}"
    run_id = f"dq-{fixture['name']}-{uuid4()}"
    source_ids: list[str] = []
    with db_session() as db:
        db.add(
            ImportSession(
                id=session_id,
                project_id=project_id,
                name=f"Synthetic rehearsal {fixture['name']}",
                status="completed",
                file_count=len(fixture["source_files"]),
                total_bytes=sum(item["size"] for item in fixture["source_files"]),
            )
        )
        for index, source in enumerate(fixture["source_files"], start=1):
            source_id = f"file-{fixture['name']}-{index}-{uuid4()}"
            source_ids.append(source_id)
            db.add(
                ImportSourceFile(
                    id=source_id,
                    import_session_id=session_id,
                    project_id=project_id,
                    original_filename=source["filename"],
                    extension=Path(source["filename"]).suffix.lstrip("."),
                    declared_mime_type="application/octet-stream",
                    file_size_bytes=source["size"],
                    sha256=source["sha256"],
                    storage_path=(
                        f"synthetic/rehearsal/{fixture['name']}/{source['filename']}"
                    ),
                )
            )
        dq = fixture["dq"]
        db.add(
            DataQualityRun(
                id=run_id,
                source_table_id=f"table-{fixture['name']}-{uuid4()}",
                source_file_id=source_ids[0],
                import_session_id=session_id,
                project_id=project_id,
                run_number=1,
                engine_name="cta-pilot-prep-003-synthetic-dq",
                engine_version="1.0.0",
                input_fingerprint=hashlib.sha256(
                    fixture["case_key"].encode("utf-8")
                ).hexdigest(),
                status="completed",
                overall_status=dq["overall_status"],
                confirmed_mapping_count=dq["confirmed_mapping_count"],
                suggested_mapping_count=dq["suggested_mapping_count"],
                rejected_mapping_count=dq["rejected_mapping_count"],
                unmapped_mapping_count=dq["unmapped_mapping_count"],
                warning_issue_count=dq["warning_issue_count"],
                blocking_issue_count=dq["blocking_issue_count"],
                total_issue_count=dq["total_issue_count"],
            )
        )
    return session_id, run_id


def register_case(
    client: TestClient,
    project_id: str,
    fixture: dict[str, Any],
) -> dict[str, Any]:
    session_id, run_id = seed_import(project_id, fixture)
    response = client.post(
        f"/pilot-intake/projects/{project_id}/cases",
        json={
            "case_key": fixture["case_key"],
            "import_session_id": session_id,
            "initial_state": fixture["initial_state"],
            "source_linkage_confidence": fixture["source_linkage_confidence"],
            "asset_references": fixture["asset_references"],
            "metrics": fixture["metrics"],
            "data_quality_run_ids": [run_id],
            "provenance": {
                "fixture": fixture["name"],
                "scenario": fixture["scenario"],
                "synthetic": True,
            },
            "decision_reason": f"synthetic_{fixture['scenario']}_registered",
        },
    )
    expect_status(response, 201, f"register {fixture['case_key']}")
    return response.json()


def seed_blind_context() -> tuple[list[str], str]:
    prompt_ids = [f"prompt-rehearsal-{uuid4()}", f"prompt-safety-{uuid4()}"]
    profile_id = f"model-profile-rehearsal-{uuid4()}"
    with db_session() as db:
        db.add_all(
            [
                PromptVersion(
                    id=prompt_ids[0],
                    stage_name="summary",
                    version="rehearsal-v1",
                    template_path="synthetic/rehearsal/summary.txt",
                    template_hash=hashlib.sha256(b"rehearsal-summary").hexdigest(),
                    is_active=True,
                    metadata_json=json.dumps({"synthetic": True}, sort_keys=True),
                ),
                PromptVersion(
                    id=prompt_ids[1],
                    stage_name="brand_safety",
                    version="rehearsal-v1",
                    template_path="synthetic/rehearsal/brand_safety.txt",
                    template_hash=hashlib.sha256(b"rehearsal-safety").hexdigest(),
                    is_active=True,
                    metadata_json=json.dumps({"synthetic": True}, sort_keys=True),
                ),
            ]
        )
        db.add(
            ModelProfile(
                id=profile_id,
                profile_name=f"synthetic-rehearsal-{uuid4()}",
                provider="stub",
                model="synthetic-rehearsal-model",
                base_url="http://127.0.0.1:1",
                enabled=True,
                default_for_demo=False,
                timeout_seconds=30,
                metadata_json=json.dumps(
                    {
                        "profile_version": "cta-pilot-prep-003-stub-v1",
                        "local_only": True,
                    },
                    sort_keys=True,
                ),
                notes="Synthetic CTA-PILOT-PREP-003 fixture only",
            )
        )
    return prompt_ids, profile_id


def _blind_user(role: str) -> dict[str, Any]:
    return {
        "user_id": f"rehearsal-{role}",
        "role": role,
        "display_name": f"Rehearsal {role}",
        "is_active": True,
    }


@contextmanager
def blind_role(role: str) -> Iterator[None]:
    with patch(
        "src.modules.blind_runs.router.get_current_user_from_request",
        lambda _request: _blind_user(role),
    ):
        yield


def diagnostic_body(
    fixture: dict[str, Any],
    prompt_ids: list[str],
    profile_id: str,
) -> dict[str, Any]:
    return {
        "execution_id": f"rehearsal-{fixture['name']}-execution-v1",
        "diagnostic_output": deepcopy(fixture["diagnostic_output"]),
        "prompt_version_ids": list(reversed(prompt_ids)),
        "model_profile_id": profile_id,
        "code_revision": CODE_REVISION,
        "execution_metadata": {
            "synthetic": True,
            "scenario": fixture["scenario"],
            "runtime": "stub",
        },
    }


def _observation(case: dict[str, Any], index: int, item: dict[str, Any]) -> dict[str, Any]:
    cg_rate = item.get("cg_rate")
    tg_rate = item.get("tg_rate")
    uplift = None
    if isinstance(cg_rate, (int, float)) and isinstance(tg_rate, (int, float)):
        uplift = round((tg_rate - cg_rate) * 100, 6)
    return {
        "observation_id": f"obs-{case['name']}-{index}",
        "metric": item["metric"],
        "metric_label": item["metric"].replace("_", " ").title(),
        "control_n": item.get("control_n"),
        "test_n": item.get("test_n"),
        "cg_rate": cg_rate,
        "tg_rate": tg_rate,
        "uplift_pp_descriptive": uplift,
        "evidence_status": item.get("evidence_status", "observed"),
        "period_start": "2026-01-01",
        "period_end": "2026-01-31",
        "platform": "Synthetic",
        "source_sheet": "CTA-PILOT-PREP-003",
        "source_row_number": index,
        "causal_interpretation_allowed": False,
        "numeric_prediction_generated": False,
        "notes": ["Synthetic rehearsal evidence only."],
    }


def _asset_diagnostic(case: dict[str, Any], index: int) -> dict[str, Any]:
    output = case["diagnostic_output"]
    recommendation = output["recommendation"]
    return {
        "test_run_id": f"test-run-{case['name']}",
        "status": "completed",
        "summary": output["summary"],
        "overall_score": output["findings"][0]["score"],
        "proposed_recommendation": recommendation,
        "effective_recommendation": (
            "accepted" if recommendation == "accept" else "manual_review_required"
        ),
        "visual_traceability_status": "complete",
        "visual_decision_status": (
            "accepted" if recommendation == "accept" else "manual_review_required"
        ),
        "findings": deepcopy(output["findings"]) if index == 1 else [],
        "scorecard": [],
        "risks": [],
    }


def build_workspace(matrix: dict[str, Any], project_id: str) -> dict[str, Any]:
    included = [
        item for item in matrix["cases"] if item["initial_state"] == "included"
    ]
    campaigns: list[dict[str, Any]] = []
    accepted_assets = 0
    for case in included:
        assets: list[dict[str, Any]] = []
        for index, asset_id in enumerate(case["asset_references"], start=1):
            source = case["source_files"][min(index - 1, len(case["source_files"]) - 1)]
            assets.append(
                {
                    "creative_record_id": f"creative-{case['name']}-{index}",
                    "creative_asset_id": asset_id,
                    "title": f"Synthetic {case['name']} asset {index}",
                    "filename": source["filename"],
                    "brand": f"Synthetic {case['name']}",
                    "inferred_platform": "Synthetic",
                    "linkage_status": (
                        "exact"
                        if case["source_linkage_confidence"] == "exact"
                        else "one_to_many"
                    ),
                    "linkage_confidence": (
                        0.99
                        if case["source_linkage_confidence"] == "exact"
                        else 0.74
                    ),
                    "linkage_notes": ["Synthetic controlled-pilot rehearsal."],
                    "accepted_for_campaign_set": True,
                    "diagnostic": _asset_diagnostic(case, index),
                }
            )
            accepted_assets += 1

        observations = case["outcome_payload"]["observations"]
        campaigns.append(
            {
                "campaign_id": f"campaign-{case['name']}",
                "case_id": case["case_key"],
                "brand": f"Synthetic {case['name']}",
                "product": "Synthetic product",
                "period_start": "2026-01-01",
                "period_end": "2026-01-31",
                "platform": "Synthetic",
                "is_contrast_case": True,
                "showcase_rank": len(campaigns) + 1,
                "campaign_level_outcomes": True,
                "individual_asset_attribution_allowed": False,
                "assets": assets,
                "outcomes": [
                    _observation(case, index, item)
                    for index, item in enumerate(observations, start=1)
                ],
                "limitations": (
                    [
                        {
                            "code": "campaign_multi_asset",
                            "message": "Outcomes remain campaign-set evidence.",
                            "severity": "warning",
                            "context": {"asset_count": len(assets)},
                        }
                    ]
                    if case["scenario"] == "multi_asset"
                    else []
                ),
            }
        )

    return {
        "project_id": project_id,
        "project_name": f"Synthetic rehearsal {project_id}",
        "normalization_run_id": "norm-cta-pilot-prep-003",
        "source_fingerprint": hashlib.sha256(project_id.encode()).hexdigest(),
        "mapping_version": "cta-pilot-prep-003/synthetic-v1",
        "generated_from_loader": "cta-pilot-prep-003-test-fixture",
        "evidence_boundaries": {
            "causal_interpretation_allowed": False,
            "numeric_uplift_prediction_generated": False,
            "individual_asset_outcome_attribution_allowed": False,
            "missing_values_inferred": False,
            "diagnostics_are_model_outputs_not_factual_outcomes": True,
        },
        "summary": {
            "campaign_count": len(campaigns),
            "outcome_count": sum(len(item["outcomes"]) for item in campaigns),
            "creative_count": accepted_assets,
            "accepted_asset_count": accepted_assets,
            "rejected_asset_count": 0,
            "unlabelled_asset_count": 0,
            "campaigns_with_diagnostics": len(campaigns),
            "campaigns_with_limitations": sum(
                1 for item in campaigns if item["limitations"]
            ),
        },
        "campaigns": campaigns,
        "unlabelled_assets": [],
    }


@contextmanager
def synthetic_workspace(
    matrix: dict[str, Any],
    project_id: str,
) -> Iterator[dict[str, Any]]:
    workspace = build_workspace(matrix, project_id)

    def loader(requested_project_id: str) -> dict[str, Any]:
        if requested_project_id != project_id:
            raise AppError("project_not_found", "Project not found", 404)
        return deepcopy(workspace)

    with ExitStack() as stack:
        stack.enter_context(
            patch("src.modules.finding_reviews.service_core._workspace_dict", loader)
        )
        stack.enter_context(
            patch("src.modules.finding_reviews.service_commands._workspace_dict", loader)
        )
        stack.enter_context(
            patch(
                "src.modules.calibration_dashboard.service."
                "get_campaign_evidence_workspace",
                loader,
            )
        )
        yield workspace


def review_request(finding, plan: dict[str, Any]) -> CreateFindingReviewRequest:
    return CreateFindingReviewRequest(
        expected_system_finding_sha256=finding.snapshot_sha256,
        reviewer_role="synthetic independent reviewer",
        decision=plan["decision"],
        correctness=plan["correctness"],
        relevance=4,
        actionability=plan["actionability"],
        traceability=plan["traceability"],
        severity_correctness=plan["severity_correctness"],
        reviewer_confidence=0.9,
        rationale="Synthetic CTA-PILOT-PREP-003 independent review.",
        comment="No client data.",
    )


def adjudication_request(
    state,
    decision: str,
) -> CreateFindingAdjudicationRequest:
    return CreateFindingAdjudicationRequest(
        expected_basis_fingerprint_sha256=state.basis_fingerprint_sha256,
        adjudicator_role="synthetic methodology owner",
        decision=decision,
        correctness=3 if decision == "partially_supported" else 1,
        relevance=4,
        actionability=3 if decision == "partially_supported" else 1,
        traceability=4,
        severity_correctness=(
            "overstated" if decision == "harmful_false_positive" else "correct"
        ),
        adjudicator_confidence=0.9,
        rationale="Synthetic disagreement resolved from immutable basis reviews.",
        comment="Synthetic only.",
    )
