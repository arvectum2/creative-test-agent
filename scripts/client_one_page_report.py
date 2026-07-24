from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.modules.client_one_page_reports.rendering import (
    build_report_bundle,
    compose_report_evidence,
    validate_report_bundle,
)

DEFAULT_OUTPUT = Path("data/generated/client_one_page_report_self_test")
FIXED_GENERATED_AT = "2026-07-24T20:00:00+00:00"


def _sample_context() -> dict:
    return {
        "client": {"id": "fictional-client", "name": "FICTIONAL CLIENT"},
        "project": {"id": "synthetic-project", "name": "Synthetic creative pilot"},
        "source": {
            "source_file_id": "synthetic-file",
            "source_table_id": "synthetic-table",
            "import_session_id": "synthetic-session",
            "filename": "synthetic_history.csv",
            "sha256": "a" * 64,
        },
        "data_quality": {
            "id": "synthetic-dq",
            "input_fingerprint": "b" * 64,
            "overall_status": "review_required",
            "source_file_count": 2,
            "source_table_count": 1,
            "source_row_count": 24,
            "source_column_count": 10,
            "confirmed_mapping_count": 8,
            "normalized_row_count": 20,
            "partial_row_count": 4,
            "creative_record_count": 4,
            "linked_creative_count": 3,
            "unlinked_creative_count": 1,
            "performance_observation_count": 20,
            "blocking_issue_count": 0,
            "warning_issue_count": 2,
            "info_issue_count": 1,
            "total_issue_count": 3,
        },
        "prediction_readiness": {
            "id": "synthetic-readiness",
            "input_fingerprint": "c" * 64,
            "overall_status": "degraded",
            "capability_count": 5,
            "ready_count": 1,
            "degraded_count": 2,
            "unavailable_count": 2,
            "not_applicable_count": 0,
            "unresolved_client_question_count": 1,
            "unresolved_analyst_question_count": 1,
        },
        "issues": [
            {
                "id": "issue-1",
                "category": "creative_linking",
                "code": "creative_link_missing",
                "severity": "warning",
                "affected_count": 1,
                "message": "One creative is not linked to historical rows.",
                "remediation_hint": "Confirm the creative identifier for the unmatched asset.",
            },
            {
                "id": "issue-2",
                "category": "metric_consistency",
                "code": "ctr_consistency_review",
                "severity": "warning",
                "affected_count": 2,
                "message": "Two supplied CTR values require source confirmation.",
                "remediation_hint": "Confirm whether CTR is supplied as ratio or percent.",
            },
        ],
        "capabilities": [
            {
                "capability_key": "historical_ctr_prediction",
                "title": "Historical CTR prediction",
                "status": "degraded",
                "mode": "calibration_only",
                "evidence_strength": "weak",
                "user_message": "Historical comparison is directional and not a validated forecast.",
                "missing_inputs": ["More comparable historical observations"],
                "degraded_inputs": [],
                "prohibited_operations": ["Validated accuracy claim"],
            },
            {
                "capability_key": "creative_lift_estimation",
                "title": "Creative lift estimation",
                "status": "unavailable",
                "mode": "descriptive_only",
                "evidence_strength": "none",
                "user_message": "Causal creative lift is unavailable.",
                "missing_inputs": ["Comparable exposed and control evidence"],
                "degraded_inputs": [],
                "prohibited_operations": ["Causal lift claim"],
            },
            {
                "capability_key": "synthetic_click_intent",
                "title": "Synthetic click intent",
                "status": "degraded",
                "mode": "proxy_only",
                "evidence_strength": "weak",
                "user_message": "Synthetic click-intent output is a labelled proxy only.",
                "missing_inputs": [],
                "degraded_inputs": ["No real respondents"],
                "prohibited_operations": ["Represent proxy as real respondent evidence"],
            },
            {
                "capability_key": "brand_lift_proxy",
                "title": "Brand-lift proxy",
                "status": "unavailable",
                "mode": "configuration_only",
                "evidence_strength": "none",
                "user_message": "Brand-lift proxy is not configured for client use.",
                "missing_inputs": ["Approved questionnaire and interpretation protocol"],
                "degraded_inputs": [],
                "prohibited_operations": ["Observed brand-lift claim"],
            },
            {
                "capability_key": "compliance_risk_review",
                "title": "Compliance risk review",
                "status": "ready",
                "mode": "linked_assets_only",
                "evidence_strength": "moderate",
                "user_message": "Observable compliance risks may be reviewed on linked assets.",
                "missing_inputs": [],
                "degraded_inputs": [],
                "prohibited_operations": ["Legal approval claim"],
            },
        ],
        "provenance": {
            "data_quality_run_id": "synthetic-dq",
            "data_quality_input_fingerprint": "b" * 64,
            "prediction_readiness_run_id": "synthetic-readiness",
            "prediction_readiness_input_fingerprint": "c" * 64,
            "source_file_sha256": "a" * 64,
        },
    }


def _sample_survey() -> dict:
    return {
        "study": {"id": "synthetic-study", "status": "closed"},
        "total_responses": 12,
        "source_counts": {"synthetic": 12},
        "metric_keys": ["clarity", "brand_recall_proxy", "click_intent_proxy"],
        "interpretation_notes": [
            "Synthetic responses are labelled and are not observations from real people.",
            "Questionnaire scores are proxy measures and are not observed campaign lift.",
        ],
    }


def _hashes(path: Path) -> dict[str, str]:
    return {
        item.name: hashlib.sha256(item.read_bytes()).hexdigest()
        for item in sorted(path.iterdir())
        if item.is_file()
    }


def self_test(output: Path) -> int:
    evidence = compose_report_evidence(
        _sample_context(),
        locale="ru",
        survey=_sample_survey(),
        generated_at=FIXED_GENERATED_AT,
    )
    manifest = build_report_bundle(evidence, output)
    errors = validate_report_bundle(output)
    if manifest.get("slide_count") != 1 or manifest.get("page_count") != 1:
        errors.append("self-test report must contain one slide and one printable page")
    if manifest.get("prediction_generated") is not False:
        errors.append("self-test must not generate a prediction")
    if errors:
        return _print_errors(errors)
    print(
        json.dumps(
            {
                "status": "valid",
                "command": "self-test",
                "output": str(output),
                "verdict": manifest["verdict"],
                "slide_count": 1,
                "page_count": 1,
                "prediction_generated": False,
            },
            sort_keys=True,
        )
    )
    return 0


def check_determinism() -> int:
    with tempfile.TemporaryDirectory() as left_raw, tempfile.TemporaryDirectory() as right_raw:
        left, right = Path(left_raw), Path(right_raw)
        if self_test(left) or self_test(right):
            return 1
        if _hashes(left) != _hashes(right):
            return _print_errors(["one-page report hashes differ between repeated fixed-input generations"])
    print(json.dumps({"status": "valid", "command": "check-determinism"}, sort_keys=True))
    return 0


def _print_errors(errors: list[str]) -> int:
    for error in errors:
        print(f"ERROR: {error}", file=sys.stderr)
    return 1 if errors else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate and validate provisional one-page client reports.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    sample = subparsers.add_parser("self-test")
    sample.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    validate = subparsers.add_parser("validate")
    validate.add_argument("--input", type=Path, required=True)
    subparsers.add_parser("check-determinism")
    generate = subparsers.add_parser("generate")
    generate.add_argument("--data-quality-run-id", required=True)
    generate.add_argument("--prediction-readiness-run-id", default=None)
    generate.add_argument("--quantitative-study-id", default=None)
    generate.add_argument("--locale", choices=("ru", "en"), default="ru")
    generate.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.command == "self-test":
            return self_test(args.output)
        if args.command == "validate":
            errors = validate_report_bundle(args.input)
            if errors:
                return _print_errors(errors)
            print(json.dumps({"status": "valid", "command": "validate", "input": str(args.input)}, sort_keys=True))
            return 0
        if args.command == "check-determinism":
            return check_determinism()
        from src.modules.client_one_page_reports.service import generate_client_one_page_report
        result = generate_client_one_page_report(
            args.data_quality_run_id,
            prediction_readiness_run_id=args.prediction_readiness_run_id,
            quantitative_study_id=args.quantitative_study_id,
            locale=args.locale,
            force=args.force,
        )
        print(result.model_dump_json())
        return 0
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
