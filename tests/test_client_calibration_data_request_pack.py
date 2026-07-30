from __future__ import annotations

from pathlib import Path

from scripts.client_calibration_data_request_pack import (
    EXPECTED_INVALID_CODES, generate, self_test,
)
from src.modules.client_calibration_data_request.spec import valid_record
from src.modules.client_calibration_data_request.validation import (
    validate_file, validate_pack, validate_records,
)


def test_generate_and_acceptance(tmp_path: Path) -> None:
    output = tmp_path / "pack"
    manifest = generate(output)
    assert len(manifest["files"]) == 11
    assert validate_pack(output) == []
    assert self_test(tmp_path / "acceptance") == []


def test_valid_examples_pass_without_warnings(tmp_path: Path) -> None:
    output = tmp_path / "pack"
    generate(output)
    for name in ("valid_calibration_data.csv", "valid_calibration_data.json", "valid_calibration_data.xlsx"):
        result = validate_file(output / "examples" / name)
        assert result.valid, result.to_dict()
        assert result.warnings == (), result.to_dict()


def test_invalid_examples_fail_with_expected_codes(tmp_path: Path) -> None:
    output = tmp_path / "pack"
    generate(output)
    for name in ("invalid_calibration_data.csv", "invalid_calibration_data.json", "invalid_calibration_data.xlsx"):
        result = validate_file(output / "examples" / name)
        assert EXPECTED_INVALID_CODES <= {item.code for item in result.errors}, result.to_dict()


def test_missing_linkage_is_explicit_and_visible() -> None:
    row = valid_record()
    row.update({
        "asset_id": None, "placement_id": None, "linkage_status": "missing",
        "linkage_missing_fields": "asset_id;placement_id",
        "linkage_notes": "Keys were not exported by the source system.",
    })
    errors, warnings = validate_records([row])
    assert errors == []
    assert "LINKAGE_REVIEW_REQUIRED" in {item.code for item in warnings}


def test_exact_linkage_cannot_hide_missing_ids() -> None:
    row = valid_record()
    row["asset_id"] = None
    errors, _ = validate_records([row])
    assert "LINKAGE_ID_REQUIRED" in {item.code for item in errors}


def test_rates_only_requires_reason_and_warns() -> None:
    row = valid_record()
    row.update({
        "measurement_basis": "rates_only", "control_sample_count": None,
        "control_positive_count": None, "test_sample_count": None,
        "test_positive_count": None, "counts_unavailable_reason": None,
    })
    errors, warnings = validate_records([row])
    assert "RATES_ONLY_REASON_REQUIRED" in {item.code for item in errors}
    assert "COUNTS_PREFERRED" not in {item.code for item in warnings}
    row["counts_unavailable_reason"] = "Rounded rates only."
    errors, warnings = validate_records([row])
    assert errors == []
    assert "COUNTS_PREFERRED" in {item.code for item in warnings}


def test_count_rate_mismatch_and_duplicate_ids_fail() -> None:
    row = valid_record()
    row["test_rate"] = 0.9
    errors, _ = validate_records([row])
    assert "RATE_COUNT_MISMATCH" in {item.code for item in errors}
    first = valid_record()
    errors, _ = validate_records([first, dict(first)])
    assert "DUPLICATE_RECORD_ID" in {item.code for item in errors}
