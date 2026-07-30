from __future__ import annotations

import hashlib
import math
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path, PurePosixPath
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

from .io import read_json, read_records
from .spec import (
    GENERATED_FILES, HEADERS, INTEGER_FIELDS, LINKAGE_IDS, NUMBER_FIELDS,
    PACKAGE_ID, PACKAGE_VERSION, SCHEMA_VERSION, build_schema,
)


@dataclass(frozen=True)
class ValidationIssue:
    severity: str
    code: str
    message: str
    record_id: str | None = None
    field: str | None = None
    row_number: int | None = None


@dataclass(frozen=True)
class ValidationResult:
    input: str
    format: str
    record_count: int
    errors: tuple[ValidationIssue, ...]
    warnings: tuple[ValidationIssue, ...]

    @property
    def valid(self) -> bool:
        return not self.errors

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": "valid" if self.valid else "invalid",
            "input": self.input, "format": self.format,
            "record_count": self.record_count,
            "error_count": len(self.errors), "warning_count": len(self.warnings),
            "errors": [asdict(item) for item in self.errors],
            "warnings": [asdict(item) for item in self.warnings],
        }


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _bool(value: Any) -> Any:
    if isinstance(value, bool):
        return value
    text = str(value or "").strip().lower()
    return False if text in {"false", "0", "no"} else True if text in {"true", "1", "yes"} else value


def _number(value: Any, integer: bool = False) -> Any:
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        return value
    try:
        number = float(str(value).replace(",", "."))
    except ValueError:
        return value
    if not math.isfinite(number):
        return value
    if integer:
        return int(number) if number.is_integer() else value
    return number


def normalize(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for raw in records:
        if not isinstance(raw, dict):
            result.append({"_invalid_record": raw})
            continue
        row: dict[str, Any] = {}
        for name in HEADERS:
            value = raw.get(name)
            if isinstance(value, str):
                value = value.strip() or None
            if name in INTEGER_FIELDS:
                value = _number(value, integer=True)
            elif name in NUMBER_FIELDS:
                value = _number(value)
            elif name == "causal_interpretation_allowed" and value is not None:
                value = _bool(value)
            row[name] = value
        if "_row_number" in raw:
            row["_row_number"] = raw["_row_number"]
        result.append(row)
    return result


def _schema_issue(error: Any, record: dict[str, Any] | None) -> ValidationIssue:
    path = list(error.absolute_path)
    field = str(path[-1]) if path and not isinstance(path[-1], int) else None
    code = {
        "required": "REQUIRED_FIELD", "enum": "INVALID_ENUM", "format": "INVALID_DATE",
        "additionalProperties": "UNKNOWN_FIELD", "type": "INVALID_TYPE",
    }.get(error.validator, "SCHEMA_VALIDATION_ERROR")
    if error.validator == "const":
        code = "CAUSAL_INTERPRETATION_FORBIDDEN" if field == "causal_interpretation_allowed" else "INVALID_CONSTANT"
    elif error.validator == "pattern":
        code = "INVALID_SHA256" if field and "sha256" in field else "INVALID_PATTERN"
    elif error.validator in {"minimum", "maximum"}:
        code = "INVALID_RATE_RANGE" if field and "rate" in field else "INVALID_RANGE"
    if error.validator == "required" and isinstance(error.validator_value, list):
        missing = [name for name in error.validator_value if name not in (error.instance or {})]
        if missing:
            field = missing[0]
    return ValidationIssue(
        "error", code, error.message,
        (record or {}).get("record_id"), field, (record or {}).get("_row_number"),
    )


def _append(items: list[ValidationIssue], issue: ValidationIssue) -> None:
    if issue not in items:
        items.append(issue)


def _semantic(row: dict[str, Any]) -> tuple[list[ValidationIssue], list[ValidationIssue]]:
    errors: list[ValidationIssue] = []
    warnings: list[ValidationIssue] = []
    record_id, row_number = row.get("record_id"), row.get("_row_number")

    def error(code: str, message: str, field: str | None = None) -> None:
        _append(errors, ValidationIssue("error", code, message, record_id, field, row_number))

    def warning(code: str, message: str, field: str | None = None) -> None:
        _append(warnings, ValidationIssue("warning", code, message, record_id, field, row_number))

    status = row.get("linkage_status")
    linkage_required = ["campaign_id", "asset_id", "placement_id", "platform", "placement_name"]
    if status == "exact":
        for name in linkage_required:
            if not row.get(name):
                error("LINKAGE_ID_REQUIRED", f"Exact linkage requires {name}.", name)
    elif status in {"probable", "one_to_many", "uncertain", "missing", "rejected"}:
        if not row.get("linkage_notes"):
            error("LINKAGE_NOTES_REQUIRED", "Non-exact linkage requires linkage_notes.", "linkage_notes")
        else:
            warning("LINKAGE_REVIEW_REQUIRED", f"Linkage status {status} requires analyst review.", "linkage_status")
    if status == "missing":
        declared = {part.strip() for part in str(row.get("linkage_missing_fields") or "").split(";") if part.strip()}
        if not declared:
            error("MISSING_LINKAGE_FIELDS_REQUIRED", "Missing linkage must list absent IDs.", "linkage_missing_fields")
        invalid = declared - LINKAGE_IDS
        if invalid:
            error("INVALID_MISSING_LINKAGE_FIELD", "Only campaign_id, asset_id and placement_id may be listed.", "linkage_missing_fields")
        for name in LINKAGE_IDS:
            blank = not row.get(name)
            if blank and name not in declared:
                error("UNDECLARED_MISSING_LINKAGE", f"Blank {name} was not declared missing.", name)
            if not blank and name in declared:
                error("FALSE_MISSING_LINKAGE", f"{name} is populated but declared missing.", name)

    basis, unit = row.get("measurement_basis"), row.get("metric_unit")
    if basis == "absolute_counts":
        for name in ("control_sample_count", "test_sample_count"):
            if not isinstance(row.get(name), int) or row[name] <= 0:
                error("ABSOLUTE_COUNT_REQUIRED", f"{name} must be a positive integer.", name)
        if unit == "proportion":
            for name in ("control_positive_count", "test_positive_count"):
                if not isinstance(row.get(name), int) or row[name] < 0:
                    error("POSITIVE_COUNT_REQUIRED", f"{name} must be a non-negative integer.", name)
            for prefix in ("control", "test"):
                sample, positive = row.get(f"{prefix}_sample_count"), row.get(f"{prefix}_positive_count")
                rate = row.get(f"{prefix}_rate")
                if isinstance(sample, int) and isinstance(positive, int):
                    if positive > sample:
                        error("POSITIVE_EXCEEDS_SAMPLE", f"{prefix}_positive_count exceeds sample count.")
                    elif isinstance(rate, (int, float)) and abs(rate - positive / sample) > 0.005:
                        error("RATE_COUNT_MISMATCH", f"{prefix}_rate differs from counts by more than 0.005.", f"{prefix}_rate")
    elif basis == "rates_only":
        if not row.get("counts_unavailable_reason"):
            error("RATES_ONLY_REASON_REQUIRED", "rates_only requires counts_unavailable_reason.", "counts_unavailable_reason")
        else:
            warning("COUNTS_PREFERRED", "Rounded rates are accepted as degraded evidence; absolute counts are preferred.", "measurement_basis")
        if row.get("test_rate") is None:
            error("RATE_REQUIRED", "rates_only requires test_rate.", "test_rate")
    elif basis == "continuous_value":
        if row.get("test_value") is None:
            error("TEST_VALUE_REQUIRED", "continuous_value requires test_value.", "test_value")
    elif basis == "not_available" and not row.get("measurement_notes"):
        error("MEASUREMENT_NOTES_REQUIRED", "not_available requires measurement_notes.", "measurement_notes")

    for name in ("control_rate", "test_rate"):
        value = row.get(name)
        if value is not None and (not isinstance(value, (int, float)) or not 0 <= value <= 1):
            error("INVALID_RATE_RANGE", f"{name} must be between 0 and 1.", name)
    try:
        start = date.fromisoformat(str(row.get("observation_start")))
        end = date.fromisoformat(str(row.get("observation_end")))
        if end < start:
            error("OBSERVATION_DATE_ORDER", "observation_end precedes observation_start.", "observation_end")
    except ValueError:
        pass
    if row.get("causal_interpretation_allowed") is not False:
        error("CAUSAL_INTERPRETATION_FORBIDDEN", "causal_interpretation_allowed must be false.", "causal_interpretation_allowed")
    for name in ("asset_sha256", "source_file_sha256"):
        value = row.get(name)
        if value is not None and (not isinstance(value, str) or len(value) != 64 or any(ch not in "0123456789abcdefABCDEF" for ch in value)):
            error("INVALID_SHA256", f"{name} must be a 64-character hexadecimal SHA-256.", name)
    return errors, warnings


def validate_records(records: list[dict[str, Any]]) -> tuple[list[ValidationIssue], list[ValidationIssue]]:
    records = normalize(records)
    errors: list[ValidationIssue] = []
    warnings: list[ValidationIssue] = []
    document = {"schema_version": SCHEMA_VERSION, "records": [{k: v for k, v in row.items() if k != "_row_number"} for row in records]}
    validator = Draft202012Validator(build_schema(), format_checker=FormatChecker())
    for item in sorted(validator.iter_errors(document), key=lambda error: list(error.absolute_path)):
        path = list(item.absolute_path)
        record = records[path[1]] if len(path) > 1 and path[0] == "records" and isinstance(path[1], int) and path[1] < len(records) else None
        _append(errors, _schema_issue(item, record))
    seen: set[str] = set()
    for row in records:
        record_id = row.get("record_id")
        if record_id in seen:
            _append(errors, ValidationIssue("error", "DUPLICATE_RECORD_ID", f"Duplicate record_id: {record_id}.", record_id, "record_id", row.get("_row_number")))
        if record_id:
            seen.add(record_id)
        row_errors, row_warnings = _semantic(row)
        for item in row_errors:
            _append(errors, item)
        for item in row_warnings:
            _append(warnings, item)
    return errors, warnings


def validate_file(path: Path) -> ValidationResult:
    path = path.expanduser().resolve()
    try:
        records, parse_codes = read_records(path)
    except Exception as exc:
        issue = ValidationIssue("error", "UNREADABLE_INPUT", str(exc))
        return ValidationResult(str(path), path.suffix.lower().lstrip("."), 0, (issue,), ())
    errors = [ValidationIssue("error", code, code.replace("_", " ").title()) for code in parse_codes]
    warnings: list[ValidationIssue] = []
    if not records and not errors:
        errors.append(ValidationIssue("error", "NO_RECORDS", "No populated calibration rows found."))
    if records:
        semantic_errors, semantic_warnings = validate_records(records)
        errors.extend(item for item in semantic_errors if item not in errors)
        warnings.extend(item for item in semantic_warnings if item not in warnings)
    return ValidationResult(
        str(path), path.suffix.lower().lstrip("."), len(records), tuple(errors), tuple(warnings)
    )


def validate_pack(root: Path) -> list[ValidationIssue]:
    root = root.expanduser().resolve()
    required = set(GENERATED_FILES) | {"package_manifest.json"}
    missing = [name for name in sorted(required) if not (root / name).is_file()]
    if missing:
        return [ValidationIssue("error", "MISSING_PACKAGE_FILE", "Missing files: " + ", ".join(missing))]
    try:
        manifest = read_json(root / "package_manifest.json")
    except Exception as exc:
        return [ValidationIssue("error", "INVALID_PACKAGE_MANIFEST", str(exc))]
    issues: list[ValidationIssue] = []
    if (manifest.get("package_id"), manifest.get("package_version"), manifest.get("schema_version")) != (PACKAGE_ID, PACKAGE_VERSION, SCHEMA_VERSION):
        issues.append(ValidationIssue("error", "PACKAGE_IDENTITY_MISMATCH", "Package identity/version mismatch."))
    for key, expected in (
        ("contains_client_data", False), ("causal_interpretation_allowed", False),
        ("numeric_uplift_prediction", False), ("individual_asset_attribution_claim", False),
        ("absolute_counts_preferred", True),
    ):
        if manifest.get(key) is not expected:
            issues.append(ValidationIssue("error", "PACKAGE_BOUNDARY_MISMATCH", f"{key} must be {expected!r}.", field=key))
    files = manifest.get("files") if isinstance(manifest.get("files"), list) else []
    if [item.get("path") for item in files if isinstance(item, dict)] != list(GENERATED_FILES):
        issues.append(ValidationIssue("error", "PACKAGE_FILE_LIST_MISMATCH", "Manifest file list/order mismatch."))
    for item in files:
        name = str(item.get("path", ""))
        pure = PurePosixPath(name)
        if not name or pure.is_absolute() or ".." in pure.parts or "\\" in name:
            issues.append(ValidationIssue("error", "UNSAFE_MANIFEST_PATH", name))
            continue
        path = root / name
        if not path.is_file() or item.get("size_bytes") != path.stat().st_size or item.get("sha256") != sha256(path):
            issues.append(ValidationIssue("error", "PACKAGE_FILE_INTEGRITY", name))
    for name in ("valid_calibration_data.csv", "valid_calibration_data.json", "valid_calibration_data.xlsx"):
        result = validate_file(root / "examples" / name)
        if not result.valid or result.warnings:
            issues.append(ValidationIssue("error", "VALID_EXAMPLE_FAILED", name))
    return issues
