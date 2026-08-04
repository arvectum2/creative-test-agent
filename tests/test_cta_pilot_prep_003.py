from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

from scripts.cta_pilot_prep_003 import (
    build_pilot_summary,
    canonical_json_bytes,
    synthetic_self_test_record,
    validate_case_matrix,
)
from scripts.cta_pilot_prep_003_runtime import (
    run_synthetic_rehearsal,
    write_execution_bundle,
)

MATRIX = json.loads(
    (
        Path(__file__).parent
        / "fixtures"
        / "pilot_rehearsal"
        / "cases.json"
    ).read_text(encoding="utf-8")
)


def test_case_matrix_and_summary_are_deterministic_and_fail_closed():
    cases = validate_case_matrix(MATRIX)
    assert {item["scenario"] for item in cases} == {
        "normal",
        "missing",
        "conflicting",
        "multi_asset",
        "rate_only",
        "harmful_false_positive",
    }

    record = synthetic_self_test_record(MATRIX)
    first = canonical_json_bytes(build_pilot_summary(MATRIX, record))
    second = canonical_json_bytes(build_pilot_summary(MATRIX, record))
    assert first == second
    payload = json.loads(first)
    assert payload["case_count"] == 6
    assert payload["completed_blind_run_case_count"] == 4
    assert payload["adjudicated_disagreement_count"] == 2
    assert payload["harmful_false_positive_count"] == 1
    assert payload["workflow_totals"]["manual_action_count"] == 34
    assert payload["claim_boundary"]["validated_model_accuracy_claimed"] is False
    assert payload["claim_boundary"]["missing_values_inferred"] is False


def test_full_synthetic_controlled_pilot_rehearsal(tmp_path):
    execution = run_synthetic_rehearsal(
        MATRIX,
        project_id=f"cta-pilot-prep-003-{uuid4()}",
    )
    summary = build_pilot_summary(MATRIX, execution.run_record)

    assert execution.intake_summary["total_cases"] == 6
    assert execution.intake_summary["counts_reconstructed_from_rates"] is False
    assert execution.intake_summary["non_exact_to_exact_promotion_count"] == 0
    assert summary["completed_blind_run_case_count"] == 4
    assert summary["outcome_reveal_after_freeze_count"] == 4
    assert summary["adjudicated_disagreement_count"] == 2
    assert summary["harmful_false_positive_count"] == 1
    assert summary["workflow_totals"] == {
        "wall_clock_seconds": 2940.0,
        "operator_touch_seconds": 1260.0,
        "manual_action_count": 34,
    }

    cases = {item["case_key"]: item for item in summary["cases"]}
    assert cases["SYN-MISSING-001"]["metrics"] == {
        "impressions": None,
        "clicks": None,
        "rate": None,
    }
    assert cases["SYN-RATE-ONLY-002"]["metrics"] == {
        "impressions": None,
        "clicks": None,
        "rate": 0.034,
    }
    assert cases["SYN-MULTI-ASSET-002"]["linkage_confidence"] == "probable"
    assert cases["SYN-MULTI-ASSET-002"]["asset_count"] == 2
    assert cases["SYN-HFP-001"]["final_review_decision"] == "harmful_false_positive"

    paths = write_execution_bundle(
        matrix=MATRIX,
        execution=execution,
        output_dir=tmp_path,
    )
    assert paths["summary"].exists()
    assert paths["manifest"].exists()
    manifest = json.loads(paths["manifest"].read_text(encoding="utf-8"))
    assert manifest["artifact_count"] == 6
    assert {item["name"] for item in manifest["files"]} == {
        "pilot-intake.json",
        "blind-runs.json",
        "independent-review.zip",
        "calibration-dashboard.json",
        "calibration-dashboard.xlsx",
        "pilot-summary.json",
    }
    blind_export = json.loads(execution.artifacts["blind-runs.json"])
    assert blind_export["claim_boundary"]["outcome_payload_included"] is False
    assert all("outcome_payload" not in item for item in blind_export["revisions"])
    assert execution.dashboard.claim_boundary["validated_model_accuracy_claimed"] is False
