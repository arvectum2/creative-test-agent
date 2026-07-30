from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path

from src.modules.client_calibration_data_request.io import (
    build_xlsx, write_dictionary, write_json, write_records_csv,
)
from src.modules.client_calibration_data_request.spec import (
    EXPECTED_INVALID_CODES, GENERATED_FILES, PACKAGE_ID, PACKAGE_VERSION,
    SCHEMA_VERSION, build_schema, client_instruction, invalid_record, valid_record,
)
from src.modules.client_calibration_data_request.validation import (
    ValidationIssue, sha256, validate_file, validate_pack, validate_records,
)

DEFAULT_OUTPUT = Path("data/generated/client_calibration_data_request/v1")


def seal(root: Path) -> dict:
    root = root.expanduser().resolve()
    missing = [name for name in GENERATED_FILES if not (root / name).is_file()]
    if missing:
        raise ValueError("cannot seal package; missing files: " + ", ".join(missing))
    manifest = {
        "package_id": PACKAGE_ID,
        "package_version": PACKAGE_VERSION,
        "schema_version": SCHEMA_VERSION,
        "contains_client_data": False,
        "causal_interpretation_allowed": False,
        "numeric_uplift_prediction": False,
        "individual_asset_attribution_claim": False,
        "absolute_counts_preferred": True,
        "files": [
            {"path": name, "size_bytes": (root / name).stat().st_size, "sha256": sha256(root / name)}
            for name in GENERATED_FILES
        ],
    }
    write_json(root / "package_manifest.json", manifest)
    return manifest


def generate(root: Path, clean: bool = True) -> dict:
    root = root.expanduser().resolve()
    if clean and root.exists():
        shutil.rmtree(root)
    (root / "examples").mkdir(parents=True, exist_ok=True)
    write_json(root / "calibration_data_request.schema.json", build_schema())
    write_records_csv(root / "calibration_data_request_template.csv", [])
    build_xlsx(root / "calibration_data_request_template.xlsx", [])
    write_dictionary(root / "data_dictionary.csv")
    (root / "client_instruction_ru.md").write_text(client_instruction(), encoding="utf-8")

    good, bad = valid_record(), invalid_record()
    write_records_csv(root / "examples/valid_calibration_data.csv", [good])
    write_records_csv(root / "examples/invalid_calibration_data.csv", [bad])
    write_json(root / "examples/valid_calibration_data.json", {"schema_version": SCHEMA_VERSION, "records": [good]})
    write_json(root / "examples/invalid_calibration_data.json", {"schema_version": SCHEMA_VERSION, "records": [bad]})
    build_xlsx(root / "examples/valid_calibration_data.xlsx", [good])
    build_xlsx(root / "examples/invalid_calibration_data.xlsx", [bad])
    return seal(root)


def check_determinism() -> list[str]:
    with tempfile.TemporaryDirectory() as left_raw, tempfile.TemporaryDirectory() as right_raw:
        left, right = Path(left_raw), Path(right_raw)
        generate(left)
        generate(right)
        return [
            name for name in (*GENERATED_FILES, "package_manifest.json")
            if sha256(left / name) != sha256(right / name)
        ]


def _rates_only_check() -> list[ValidationIssue]:
    row = valid_record()
    row.update({
        "measurement_basis": "rates_only",
        "control_sample_count": None, "control_positive_count": None,
        "test_sample_count": None, "test_positive_count": None,
        "counts_unavailable_reason": "The source exports rounded rates only.",
    })
    errors, warnings = validate_records([row])
    issues = list(errors)
    if "COUNTS_PREFERRED" not in {item.code for item in warnings}:
        issues.append(ValidationIssue("error", "COUNTS_PREFERENCE_WARNING_MISSING", "rates_only must emit COUNTS_PREFERRED."))
    return issues


def self_test(root: Path) -> list[ValidationIssue]:
    generate(root)
    issues = validate_pack(root)
    for name in ("invalid_calibration_data.csv", "invalid_calibration_data.json", "invalid_calibration_data.xlsx"):
        result = validate_file(root / "examples" / name)
        codes = {item.code for item in result.errors}
        if not EXPECTED_INVALID_CODES <= codes:
            issues.append(ValidationIssue("error", "INVALID_EXAMPLE_TOO_WEAK", f"{name} missing expected codes: {sorted(EXPECTED_INVALID_CODES - codes)}"))
    issues.extend(_rates_only_check())
    drift = check_determinism()
    if drift:
        issues.append(ValidationIssue("error", "NON_DETERMINISTIC_GENERATION", "Files differ: " + ", ".join(drift)))
    return issues


def _print_issues(issues: list[ValidationIssue]) -> None:
    for issue in issues:
        location = ""
        if issue.record_id:
            location += f" record={issue.record_id}"
        if issue.row_number:
            location += f" row={issue.row_number}"
        if issue.field:
            location += f" field={issue.field}"
        print(f"{issue.severity.upper()} {issue.code}:{location} {issue.message}", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate and validate CTA-DATA-002 calibration data packs.")
    parser.add_argument("command", choices=("generate", "seal", "validate", "validate-pack", "self-test", "check-determinism"))
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--input", type=Path)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.command == "generate":
            manifest = generate(args.output)
            print(json.dumps({"status": "generated", "output": str(args.output), "file_count": len(manifest["files"])}, sort_keys=True))
            return 0
        if args.command == "seal":
            if not args.input:
                parser.error("seal requires --input")
            manifest = seal(args.input)
            print(json.dumps({"status": "sealed", "input": str(args.input), "file_count": len(manifest["files"])}, sort_keys=True))
            return 0
        if args.command == "validate":
            if not args.input:
                parser.error("validate requires --input")
            result = validate_file(args.input)
            print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2, sort_keys=True))
            return 0 if result.valid and (not args.strict or not result.warnings) else 1
        if args.command == "validate-pack":
            if not args.input:
                parser.error("validate-pack requires --input")
            issues = validate_pack(args.input)
        elif args.command == "self-test":
            issues = self_test(args.output)
        else:
            drift = check_determinism()
            issues = [] if not drift else [ValidationIssue("error", "NON_DETERMINISTIC_GENERATION", ", ".join(drift))]
        if issues:
            _print_issues(issues)
            return 1
        print(json.dumps({"status": "valid", "command": args.command}, sort_keys=True))
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
