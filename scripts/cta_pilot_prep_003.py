#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SCHEMA_VERSION = "cta-pilot-prep-003/rehearsal-summary-v1"
MANIFEST_VERSION = "cta-pilot-prep-003/artifact-manifest-v1"
REQUIRED_SCENARIOS = {
    "normal",
    "missing",
    "conflicting",
    "multi_asset",
    "rate_only",
    "harmful_false_positive",
}
FORBIDDEN_CLAIM_PHRASES = (
    "validated model accuracy",
    "validated accuracy",
    "causal brand lift",
    "numeric uplift prediction",
)


class RehearsalValidationError(ValueError):
    """Raised when synthetic rehearsal evidence violates the pilot boundary."""


def canonical_json_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def sha256_hex(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RehearsalValidationError(f"{path} must contain a JSON object")
    return payload


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise RehearsalValidationError(message)


def _is_sha256(value: Any) -> bool:
    if not isinstance(value, str) or len(value) != 64:
        return False
    try:
        int(value, 16)
    except ValueError:
        return False
    return True


def validate_case_matrix(matrix: dict[str, Any]) -> list[dict[str, Any]]:
    _require(
        matrix.get("schema_version") == "cta-pilot-prep-003/case-matrix-v1",
        "Unsupported rehearsal case-matrix schema",
    )
    cases = matrix.get("cases")
    _require(isinstance(cases, list), "cases must be a list")
    _require(len(cases) >= 6, "At least six synthetic cases are required")

    scenarios = {item.get("scenario") for item in cases if isinstance(item, dict)}
    _require(
        REQUIRED_SCENARIOS.issubset(scenarios),
        f"Missing required scenarios: {sorted(REQUIRED_SCENARIOS - scenarios)}",
    )

    case_keys: set[str] = set()
    for item in cases:
        _require(isinstance(item, dict), "Each case must be a JSON object")
        case_key = item.get("case_key")
        _require(isinstance(case_key, str) and case_key, "case_key is required")
        _require(case_key not in case_keys, f"Duplicate case_key: {case_key}")
        case_keys.add(case_key)

        state = item.get("initial_state")
        _require(
            state in {"included", "excluded", "deferred", "needs_clarification"},
            f"{case_key}: unsupported initial_state",
        )
        linkage = item.get("source_linkage_confidence")
        _require(
            linkage in {"exact", "probable", "uncertain", "missing"},
            f"{case_key}: unsupported linkage confidence",
        )
        assets = item.get("asset_references")
        _require(isinstance(assets, list), f"{case_key}: asset_references must be a list")

        metrics = item.get("metrics")
        _require(isinstance(metrics, dict), f"{case_key}: metrics must be an object")
        impressions = metrics.get("impressions")
        clicks = metrics.get("clicks")
        rate = metrics.get("rate")
        if item.get("scenario") == "rate_only":
            _require(
                impressions is None and clicks is None and rate is not None,
                f"{case_key}: rate-only case must keep counts missing",
            )
        if item.get("scenario") == "missing":
            _require(
                impressions is None and clicks is None and rate is None,
                f"{case_key}: missing values must remain missing",
            )
        if item.get("scenario") == "multi_asset":
            _require(len(assets) >= 2, f"{case_key}: multi-asset case needs two assets")
            _require(
                linkage != "exact",
                f"{case_key}: multi-asset synthetic linkage must not be promoted to exact",
            )

        source_files = item.get("source_files")
        _require(
            isinstance(source_files, list) and source_files,
            f"{case_key}: source_files are required",
        )
        for source in source_files:
            _require(
                isinstance(source, dict) and _is_sha256(source.get("sha256")),
                f"{case_key}: every source file needs a valid SHA-256",
            )

        workflow = item.get("workflow")
        _require(isinstance(workflow, dict), f"{case_key}: workflow measurement is required")
        wall = workflow.get("wall_clock_seconds")
        touch = workflow.get("operator_touch_seconds")
        actions = workflow.get("manual_action_count")
        _require(
            isinstance(wall, (int, float)) and wall >= 0,
            f"{case_key}: invalid wall_clock_seconds",
        )
        _require(
            isinstance(touch, (int, float)) and 0 <= touch <= wall,
            f"{case_key}: operator touch must be between zero and wall clock",
        )
        _require(
            isinstance(actions, int) and actions >= 0,
            f"{case_key}: manual_action_count must be a non-negative integer",
        )

    return sorted(cases, key=lambda item: item["case_key"])


def _assert_claim_boundary_text(value: Any) -> None:
    text = json.dumps(value, ensure_ascii=False).lower()
    for phrase in FORBIDDEN_CLAIM_PHRASES:
        if phrase in text:
            raise RehearsalValidationError(
                f"Forbidden product claim phrase present in rehearsal record: {phrase}"
            )


def _case_result_map(run_record: dict[str, Any]) -> dict[str, dict[str, Any]]:
    results = run_record.get("case_results")
    _require(isinstance(results, list), "run record case_results must be a list")
    mapped: dict[str, dict[str, Any]] = {}
    for item in results:
        _require(isinstance(item, dict), "case result must be an object")
        case_key = item.get("case_key")
        _require(isinstance(case_key, str) and case_key, "case result case_key is required")
        _require(case_key not in mapped, f"Duplicate case result: {case_key}")
        mapped[case_key] = item
    return mapped


def build_pilot_summary(
    matrix: dict[str, Any],
    run_record: dict[str, Any],
) -> dict[str, Any]:
    cases = validate_case_matrix(matrix)
    _assert_claim_boundary_text(run_record)
    results = _case_result_map(run_record)
    expected_keys = {item["case_key"] for item in cases}
    _require(
        set(results) == expected_keys,
        "run record must contain exactly one result for every synthetic case",
    )

    state_counts = {
        "included": 0,
        "excluded": 0,
        "deferred": 0,
        "needs_clarification": 0,
    }
    completed_blind_runs = 0
    outcome_reveals_after_freeze = 0
    adjudicated_disagreements = 0
    harmful_false_positives = 0
    workflow_totals = {
        "wall_clock_seconds": 0.0,
        "operator_touch_seconds": 0.0,
        "manual_action_count": 0,
    }
    summary_cases: list[dict[str, Any]] = []

    for case in cases:
        result = results[case["case_key"]]
        observed_state = result.get("state")
        _require(
            observed_state == case["initial_state"],
            f"{case['case_key']}: state changed unexpectedly",
        )
        state_counts[observed_state] += 1

        metrics = result.get("metrics")
        _require(isinstance(metrics, dict), f"{case['case_key']}: result metrics missing")
        if case["scenario"] in {"missing", "rate_only"}:
            _require(
                metrics.get("impressions") is None and metrics.get("clicks") is None,
                f"{case['case_key']}: missing counts were reconstructed",
            )

        blind_revision_count = int(result.get("blind_revision_count", 0))
        if blind_revision_count:
            completed_blind_runs += 1
        revealed_after_freeze = bool(result.get("outcome_revealed_after_freeze", False))
        if revealed_after_freeze:
            outcome_reveals_after_freeze += 1

        review_status = result.get("review_status")
        if review_status == "adjudicated":
            adjudicated_disagreements += 1
        final_decision = result.get("final_review_decision")
        if final_decision == "harmful_false_positive":
            harmful_false_positives += 1

        workflow = result.get("workflow")
        _require(isinstance(workflow, dict), f"{case['case_key']}: workflow result missing")
        wall = float(workflow.get("wall_clock_seconds", -1))
        touch = float(workflow.get("operator_touch_seconds", -1))
        actions = workflow.get("manual_action_count")
        _require(0 <= touch <= wall, f"{case['case_key']}: invalid workflow timing")
        _require(isinstance(actions, int) and actions >= 0, f"{case['case_key']}: invalid actions")
        workflow_totals["wall_clock_seconds"] += wall
        workflow_totals["operator_touch_seconds"] += touch
        workflow_totals["manual_action_count"] += actions

        summary_cases.append(
            {
                "case_key": case["case_key"],
                "scenario": case["scenario"],
                "state": observed_state,
                "linkage_confidence": result.get("linkage_confidence"),
                "asset_count": result.get("asset_count"),
                "metrics": metrics,
                "blind_revision_count": blind_revision_count,
                "outcome_revealed_after_freeze": revealed_after_freeze,
                "review_status": review_status,
                "final_review_decision": final_decision,
                "workflow": workflow,
            }
        )

    artifact_hashes = run_record.get("artifact_hashes", {})
    _require(isinstance(artifact_hashes, dict), "artifact_hashes must be an object")
    for name, digest in artifact_hashes.items():
        _require(isinstance(name, str) and name, "artifact name must be non-empty")
        _require(_is_sha256(digest), f"{name}: invalid artifact SHA-256")

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": matrix.get("generated_at"),
        "project_id": run_record.get("project_id"),
        "evidence_class": "synthetic",
        "case_count": len(cases),
        "state_counts": state_counts,
        "completed_blind_run_case_count": completed_blind_runs,
        "outcome_reveal_after_freeze_count": outcome_reveals_after_freeze,
        "adjudicated_disagreement_count": adjudicated_disagreements,
        "harmful_false_positive_count": harmful_false_positives,
        "workflow_totals": workflow_totals,
        "cases": summary_cases,
        "artifact_hashes": dict(sorted(artifact_hashes.items())),
        "claim_boundary": {
            "validated_model_accuracy_claimed": False,
            "causal_brand_lift_claimed": False,
            "numeric_uplift_prediction_claimed": False,
            "real_client_evidence_included": False,
            "missing_values_inferred": False,
            "rounded_rates_used_to_reconstruct_counts": False,
            "non_exact_linkage_promoted_to_exact": False,
        },
        "limitations": [
            "Synthetic rehearsal evidence is process acceptance, not validated model accuracy.",
            "Local browser and production-model acceptance is a separate required gate.",
            "No real client material or real campaign outcome is included.",
        ],
    }


def build_artifact_manifest(artifacts: dict[str, bytes]) -> dict[str, Any]:
    entries = [
        {
            "name": name,
            "sha256": sha256_hex(payload),
            "size_bytes": len(payload),
        }
        for name, payload in sorted(artifacts.items())
    ]
    return {
        "schema_version": MANIFEST_VERSION,
        "files": entries,
        "artifact_count": len(entries),
    }


def write_summary_bundle(
    *,
    matrix: dict[str, Any],
    run_record: dict[str, Any],
    output_dir: Path,
) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    summary_bytes = canonical_json_bytes(build_pilot_summary(matrix, run_record))
    manifest = build_artifact_manifest({"pilot-summary.json": summary_bytes})
    manifest_bytes = canonical_json_bytes(manifest)

    summary_path = output_dir / "pilot-summary.json"
    manifest_path = output_dir / "rehearsal-manifest.json"
    summary_path.write_bytes(summary_bytes)
    manifest_path.write_bytes(manifest_bytes)
    return {"summary": summary_path, "manifest": manifest_path}


def synthetic_self_test_record(matrix: dict[str, Any]) -> dict[str, Any]:
    cases = validate_case_matrix(matrix)
    case_results: list[dict[str, Any]] = []
    for case in cases:
        review_plan = case.get("review_plan")
        included = case["initial_state"] == "included"
        final_decision = None
        review_status = "not_applicable"
        if isinstance(review_plan, dict):
            review_status = review_plan["expected_status"]
            final_decision = review_plan.get("adjudication_decision")
            if final_decision is None:
                final_decision = review_plan["reviewer_a"]["decision"]
        case_results.append(
            {
                "case_key": case["case_key"],
                "state": case["initial_state"],
                "linkage_confidence": case["source_linkage_confidence"],
                "asset_count": len(case["asset_references"]),
                "metrics": case["metrics"],
                "blind_revision_count": 1 if included else 0,
                "outcome_revealed_after_freeze": included and case.get("outcome_payload") is not None,
                "review_status": review_status,
                "final_review_decision": final_decision,
                "workflow": case["workflow"],
            }
        )
    return {
        "project_id": "synthetic-self-test",
        "case_results": case_results,
        "artifact_hashes": {},
    }


def _print_paths(paths: dict[str, Path]) -> None:
    for key, path in paths.items():
        print(f"{key}: {path}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="CTA-PILOT-PREP-003 synthetic controlled-pilot rehearsal harness"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate_parser = subparsers.add_parser("validate")
    validate_parser.add_argument("--fixture", type=Path, required=True)

    summarize_parser = subparsers.add_parser("summarize")
    summarize_parser.add_argument("--fixture", type=Path, required=True)
    summarize_parser.add_argument("--record", type=Path, required=True)
    summarize_parser.add_argument("--output-dir", type=Path, required=True)

    self_test_parser = subparsers.add_parser("self-test")
    self_test_parser.add_argument("--fixture", type=Path, required=True)
    self_test_parser.add_argument("--output-dir", type=Path, required=True)
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = build_parser().parse_args(list(argv) if argv is not None else None)
    matrix = load_json(args.fixture)

    if args.command == "validate":
        cases = validate_case_matrix(matrix)
        print(f"validated {len(cases)} synthetic cases")
        return 0

    if args.command == "summarize":
        record = load_json(args.record)
        _print_paths(
            write_summary_bundle(
                matrix=matrix,
                run_record=record,
                output_dir=args.output_dir,
            )
        )
        return 0

    record = synthetic_self_test_record(matrix)
    _print_paths(
        write_summary_bundle(
            matrix=matrix,
            run_record=record,
            output_dir=args.output_dir,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
