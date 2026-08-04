#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import sys
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.cta_pilot_prep_003 import (
    build_artifact_manifest,
    canonical_json_bytes,
    load_json,
    validate_case_matrix,
    write_summary_bundle,
)
from scripts.cta_pilot_prep_003_support import (
    ADJUDICATOR,
    REVIEWER_A,
    REVIEWER_B,
    SYSTEM_USER,
    adjudication_request,
    blind_role,
    check,
    create_project,
    diagnostic_body,
    expect_status,
    register_case,
    review_request,
    seed_blind_context,
    synthetic_workspace,
)
from src.main import app
from src.modules.calibration_dashboard import service as dashboard_service
from src.modules.calibration_dashboard.schemas import (
    CreateWorkflowMeasurementRequest,
    UpsertCalibrationCaseRequest,
)
from src.modules.finding_reviews import service as review_service
from src.modules.finding_reviews.schemas import CreateHumanFindingRequest


@dataclass(frozen=True)
class RehearsalExecution:
    project_id: str
    run_record: dict[str, Any]
    artifacts: dict[str, bytes]
    intake_summary: dict[str, Any]
    dashboard: Any


def _run_blind_stage(
    *,
    client: TestClient,
    cases: list[dict[str, Any]],
    created: dict[str, dict[str, Any]],
) -> tuple[dict[str, dict[str, Any]], dict[str, bool]]:
    prompt_ids, profile_id = seed_blind_context()
    revisions: dict[str, dict[str, Any]] = {}
    revealed_after_freeze: dict[str, bool] = {}

    for fixture in cases:
        if fixture["initial_state"] != "included":
            continue
        case_key = fixture["case_key"]
        case_id = created[case_key]["id"]
        outcome_payload = deepcopy(fixture["outcome_payload"])

        with blind_role("manager"):
            sealed = client.post(
                f"/blind-runs/projects/{created[case_key]['project_id']}"
                f"/cases/{case_id}/outcome-envelope",
                json={
                    "outcome_schema_version": "cta-pilot-prep-003/outcome-v1",
                    "outcome_payload": outcome_payload,
                    "provenance": {
                        "synthetic": True,
                        "scenario": fixture["scenario"],
                    },
                },
            )
            expect_status(sealed, 201, f"seal outcome {case_key}")
            check("outcome_payload" not in sealed.json(), f"{case_key}: outcome leaked")
            blocked = client.get(
                f"/blind-runs/projects/{created[case_key]['project_id']}"
                f"/cases/{case_id}/outcome-envelope/reveal"
            )
            expect_status(blocked, 409, f"pre-freeze outcome barrier {case_key}")

        with blind_role("analyst"):
            frozen = client.post(
                f"/blind-runs/projects/{created[case_key]['project_id']}"
                f"/cases/{case_id}/revisions",
                json=diagnostic_body(fixture, prompt_ids, profile_id),
            )
            expect_status(frozen, 201, f"freeze diagnostic {case_key}")
            check("outcome_payload" not in frozen.text, f"{case_key}: freeze leaked outcome")
            revisions[case_key] = frozen.json()

        with blind_role("manager"):
            revealed = client.get(
                f"/blind-runs/projects/{created[case_key]['project_id']}"
                f"/cases/{case_id}/outcome-envelope/reveal"
            )
            expect_status(revealed, 200, f"post-freeze outcome reveal {case_key}")
            check(
                revealed.json()["outcome_payload"] == outcome_payload,
                f"{case_key}: revealed outcome changed",
            )
            revealed_after_freeze[case_key] = True

    return revisions, revealed_after_freeze


def _create_human_omission(project_id: str, workspace: dict[str, Any]) -> None:
    campaign = next(
        item for item in workspace["campaigns"] if item["case_id"] == "SYN-CONFLICT-001"
    )
    asset = campaign["assets"][0]
    human = review_service.create_human_finding(
        project_id,
        CreateHumanFindingRequest(
            campaign_id=campaign["campaign_id"],
            creative_record_id=asset["creative_record_id"],
            creative_asset_id=asset["creative_asset_id"],
            criterion="synthetic_omission",
            title="Synthetic omission retained separately",
            text="A synthetic omission is recorded without fabricating a system finding.",
            proposed_severity="medium",
            reviewer_role="synthetic independent reviewer",
            relevance=5,
            actionability=4,
            traceability=4,
            reviewer_confidence=0.85,
            rationale="Synthetic human-added finding for rehearsal coverage.",
        ),
        user=REVIEWER_A,
    )
    check(human.system_finding_snapshot is None, "Human finding fabricated a snapshot")


def _record_dashboard_inputs(
    matrix: dict[str, Any],
    project_id: str,
) -> None:
    inclusion_map = {
        "included": "included",
        "excluded": "excluded",
        "deferred": "deferred",
        "needs_clarification": "deferred",
    }
    for fixture in validate_case_matrix(matrix):
        dashboard_service.upsert_case_evidence(
            project_id,
            fixture["case_key"],
            UpsertCalibrationCaseRequest(
                evidence_class="synthetic",
                inclusion_status=inclusion_map[fixture["initial_state"]],
                source_reference=f"synthetic:{fixture['scenario']}",
                notes=(
                    "Original pilot state needs_clarification."
                    if fixture["initial_state"] == "needs_clarification"
                    else None
                ),
            ),
            user=SYSTEM_USER,
        )
        workflow = fixture["workflow"]
        dashboard_service.create_workflow_measurement(
            project_id,
            CreateWorkflowMeasurementRequest(
                case_id=fixture["case_key"],
                stage="intake_to_pilot_summary",
                status=workflow["status"],
                wall_clock_seconds=workflow["wall_clock_seconds"],
                operator_touch_seconds=workflow["operator_touch_seconds"],
                manual_action_count=workflow["manual_action_count"],
                report_version="cta-pilot-prep-003/v1",
                notes="Explicit synthetic operator measurement.",
            ),
            user=SYSTEM_USER,
        )


def _run_review_stage(
    *,
    matrix: dict[str, Any],
    project_id: str,
) -> tuple[dict[str, dict[str, Any]], bytes, Any]:
    cases = validate_case_matrix(matrix)
    review_results = {
        item["case_key"]: {"status": "not_applicable", "decision": None}
        for item in cases
    }
    by_key = {item["case_key"]: item for item in cases}

    with synthetic_workspace(matrix, project_id) as workspace:
        findings = review_service.list_reviewable_findings(project_id)
        finding_by_case = {item.case_id: item for item in findings}
        planned = [item for item in cases if item.get("review_plan")]
        check(len(findings) == len(planned), "Unexpected reviewable finding count")

        for case_key, finding in sorted(finding_by_case.items()):
            fixture = by_key[case_key]
            plan = fixture["review_plan"]
            review_service.create_system_review(
                project_id,
                finding.finding_id,
                review_request(finding, plan["reviewer_a"]),
                user=REVIEWER_A,
            )
            review_service.create_system_review(
                project_id,
                finding.finding_id,
                review_request(finding, plan["reviewer_b"]),
                user=REVIEWER_B,
            )
            state = review_service.get_finding_disagreement(project_id, finding.finding_id)
            if plan.get("adjudication_decision"):
                check(state.status == "disagreement", f"{case_key}: disagreement missing")
                adjudication = review_service.create_finding_adjudication(
                    project_id,
                    finding.finding_id,
                    adjudication_request(state, plan["adjudication_decision"]),
                    user=ADJUDICATOR,
                )
                final_state = review_service.get_finding_disagreement(
                    project_id, finding.finding_id
                )
                check(final_state.status == "adjudicated", f"{case_key}: not adjudicated")
                review_results[case_key] = {
                    "status": final_state.status,
                    "decision": adjudication.decision,
                }
            else:
                check(
                    state.status == plan["expected_status"],
                    f"{case_key}: unexpected review state {state.status}",
                )
                review_results[case_key] = {
                    "status": state.status,
                    "decision": plan["reviewer_a"]["decision"],
                }

        _create_human_omission(project_id, workspace)
        _record_dashboard_inputs(matrix, project_id)
        dashboard = dashboard_service.compose_dashboard(
            project_id, evidence_filter="synthetic"
        )
        package_one, _ = review_service.build_calibration_package(project_id)
        package_two, _ = review_service.build_calibration_package(project_id)
        check(package_one == package_two, "Independent-review export is not deterministic")
        return review_results, package_one, dashboard


def _deterministic_exports(
    client: TestClient,
    project_id: str,
    review_package: bytes,
    matrix: dict[str, Any],
) -> dict[str, bytes]:
    intake_one = client.get(f"/pilot-intake/projects/{project_id}/export.json")
    intake_two = client.get(f"/pilot-intake/projects/{project_id}/export.json")
    expect_status(intake_one, 200, "pilot intake export")
    check(intake_one.content == intake_two.content, "Pilot intake export changed")

    with blind_role("analyst"):
        blind_one = client.get(f"/blind-runs/projects/{project_id}/export.json")
        blind_two = client.get(f"/blind-runs/projects/{project_id}/export.json")
    expect_status(blind_one, 200, "blind-run export")
    check(blind_one.content == blind_two.content, "Blind-run export changed")
    blind_payload = blind_one.json()
    check(
        blind_payload["claim_boundary"]["outcome_payload_included"] is False,
        "Blind export claim boundary allows outcome payloads",
    )
    check(
        all("outcome_payload" not in item for item in blind_payload["revisions"]),
        "Outcome leaked into blind revision export",
    )

    with synthetic_workspace(matrix, project_id):
        dashboard_json_one = dashboard_service.dashboard_json_bytes(
            project_id, evidence_filter="synthetic"
        )
        dashboard_json_two = dashboard_service.dashboard_json_bytes(
            project_id, evidence_filter="synthetic"
        )
        dashboard_xlsx_one = dashboard_service.dashboard_xlsx_bytes(
            project_id, evidence_filter="synthetic"
        )
        dashboard_xlsx_two = dashboard_service.dashboard_xlsx_bytes(
            project_id, evidence_filter="synthetic"
        )
    check(dashboard_json_one == dashboard_json_two, "Dashboard JSON changed")
    check(dashboard_xlsx_one == dashboard_xlsx_two, "Dashboard XLSX changed")

    return {
        "pilot-intake.json": intake_one.content,
        "blind-runs.json": blind_one.content,
        "independent-review.zip": review_package,
        "calibration-dashboard.json": dashboard_json_one,
        "calibration-dashboard.xlsx": dashboard_xlsx_one,
    }


def run_synthetic_rehearsal(
    matrix: dict[str, Any],
    *,
    project_id: str | None = None,
) -> RehearsalExecution:
    cases = validate_case_matrix(matrix)
    project_id = project_id or f"pilot-rehearsal-{uuid4()}"
    create_project(project_id)
    client = TestClient(app)
    created = {
        fixture["case_key"]: register_case(client, project_id, fixture)
        for fixture in cases
    }

    intake = client.get(f"/pilot-intake/projects/{project_id}/data-quality-summary")
    expect_status(intake, 200, "pilot intake DQ summary")
    intake_summary = intake.json()
    check(intake_summary["total_cases"] == 6, "Expected six registered cases")
    check(not intake_summary["counts_reconstructed_from_rates"], "Counts reconstructed")
    check(
        intake_summary["non_exact_to_exact_promotion_count"] == 0,
        "Non-exact linkage promoted to exact",
    )

    revisions, reveals = _run_blind_stage(client=client, cases=cases, created=created)
    reviews, review_package, dashboard = _run_review_stage(
        matrix=matrix, project_id=project_id
    )
    check(
        dashboard.claim_boundary["validated_model_accuracy_claimed"] is False,
        "Dashboard claimed validated model accuracy",
    )
    metrics = {item.key: item for item in dashboard.metrics}
    check(metrics["harmful_false_positive_count"].value == 1, "HFP not captured")
    check(metrics["human_added_finding_count"].value == 1, "Omission not captured")

    artifacts = _deterministic_exports(client, project_id, review_package, matrix)
    artifact_hashes = {
        name: hashlib.sha256(payload).hexdigest()
        for name, payload in sorted(artifacts.items())
    }
    case_results = []
    for fixture in cases:
        case_key = fixture["case_key"]
        case_results.append(
            {
                "case_key": case_key,
                "state": created[case_key]["state"],
                "linkage_confidence": created[case_key]["linkage_confidence"],
                "asset_count": created[case_key]["asset_count"],
                "metrics": created[case_key]["metrics"],
                "blind_revision_count": 1 if case_key in revisions else 0,
                "outcome_revealed_after_freeze": reveals.get(case_key, False),
                "review_status": reviews[case_key]["status"],
                "final_review_decision": reviews[case_key]["decision"],
                "workflow": fixture["workflow"],
            }
        )

    return RehearsalExecution(
        project_id=project_id,
        run_record={
            "project_id": project_id,
            "case_results": case_results,
            "artifact_hashes": artifact_hashes,
        },
        artifacts=artifacts,
        intake_summary=intake_summary,
        dashboard=dashboard,
    )


def write_execution_bundle(
    *,
    matrix: dict[str, Any],
    execution: RehearsalExecution,
    output_dir: Path,
) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}
    for name, payload in sorted(execution.artifacts.items()):
        path = output_dir / name
        path.write_bytes(payload)
        paths[name] = path

    summary_paths = write_summary_bundle(
        matrix=matrix,
        run_record=execution.run_record,
        output_dir=output_dir,
    )
    paths.update(summary_paths)
    summary_bytes = summary_paths["summary"].read_bytes()
    manifest = build_artifact_manifest(
        {**execution.artifacts, "pilot-summary.json": summary_bytes}
    )
    manifest_path = output_dir / "rehearsal-manifest.json"
    manifest_path.write_bytes(canonical_json_bytes(manifest))
    paths["manifest"] = manifest_path

    record_path = output_dir / "sanitized-run-record.json"
    record_path.write_bytes(canonical_json_bytes(execution.run_record))
    paths["run_record"] = record_path
    return paths


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the CTA-PILOT-PREP-003 full synthetic stub rehearsal"
    )
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    matrix = load_json(args.fixture)
    execution = run_synthetic_rehearsal(matrix)
    paths = write_execution_bundle(
        matrix=matrix,
        execution=execution,
        output_dir=args.output_dir,
    )
    print(f"project_id: {execution.project_id}")
    for name, path in sorted(paths.items()):
        print(f"{name}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
