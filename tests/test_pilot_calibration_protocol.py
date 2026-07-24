from __future__ import annotations

import csv
import json
from pathlib import Path

from scripts.pilot_calibration_protocol import (
    CORE_FILES,
    MANIFEST_FILE,
    HEADERS,
    build_summary,
    generate,
    populate_self_test,
    seal,
    summarize,
    validate,
)


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def _write_csv(path: Path, headers: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)


def test_generated_package_is_valid_deterministic_and_truthful(tmp_path: Path):
    left = tmp_path / "left"
    right = tmp_path / "right"
    first = generate(left)
    generate(right)

    assert validate(left) == []
    assert validate(right) == []
    assert first["template_only"] is True
    assert first["prediction_generated"] is False
    assert first["accuracy_promise"] is False
    assert first["causal_lift_claim"] is False
    assert {item["path"] for item in first["files"]} == set(CORE_FILES)

    for name in (*CORE_FILES, MANIFEST_FILE):
        assert (left / name).read_bytes() == (right / name).read_bytes()

    protocol = json.loads((left / "calibration_protocol.json").read_text("utf-8"))
    assert protocol["pilot_scope"]["planned_real_creative_cases_min"] == 15
    assert protocol["pilot_scope"]["planned_real_creative_cases_max"] == 20
    assert protocol["evidence_boundary"]["pilot_sample_is_not_robust_training_data"] is True
    assert protocol["analysis_policy"]["automatic_model_selection"] is False


def test_self_test_summary_keeps_synthetic_and_real_evidence_separate(tmp_path: Path):
    output = tmp_path / "package"
    generate(output)
    populate_self_test(output)
    assert validate(output) == []

    summary = summarize(output)

    assert summary["pilot_sample"]["included_case_count"] == 15
    assert summary["pilot_sample"]["real_client_case_count"] == 0
    assert summary["pilot_sample"]["synthetic_case_count"] == 15
    assert summary["pilot_sample"]["real_case_target_met"] is False
    assert summary["expert_review"]["review_count"] == 30
    assert summary["questionnaire"]["real_human_response_count"] == 0
    assert summary["questionnaire"]["synthetic_response_count"] == 180
    assert summary["claim_boundary"]["validated_accuracy_claim_permitted"] is False
    assert summary["claim_boundary"]["causal_creative_lift_claim_permitted"] is False
    assert validate(output) == []


def test_validator_rejects_causal_outcome_and_mislabeled_questionnaire(tmp_path: Path):
    output = tmp_path / "package"
    generate(output)

    outcomes = _read_csv(output / "outcome_linkage.csv")
    outcomes[0].update(
        {
            "case_id": "C001",
            "evidence_type": "historical_performance",
            "metric_name": "ctr",
            "metric_value": "0.02",
            "metric_unit": "fraction",
            "source_system": "test",
            "source_record_id": "record-1",
            "causal_interpretation_allowed": "true",
            "provenance_sha256": "a" * 64,
        }
    )
    _write_csv(output / "outcome_linkage.csv", HEADERS["outcome_linkage.csv"], outcomes)

    questionnaires = _read_csv(output / "questionnaire_evidence.csv")
    questionnaires[0].update(
        {
            "case_id": "C001",
            "study_id": "study-1",
            "response_source": "synthetic",
            "respondent_count": "10",
            "metric_name": "click_intent",
            "estimate": "4.2",
            "scale_min": "1",
            "scale_max": "7",
            "real_human_count": "2",
            "synthetic_count": "8",
        }
    )
    _write_csv(output / "questionnaire_evidence.csv", HEADERS["questionnaire_evidence.csv"], questionnaires)
    seal(output)

    errors = validate(output)
    assert any("causal_interpretation_allowed must be false" in item for item in errors)
    assert any("synthetic source cannot include real humans" in item for item in errors)


def test_manifest_detects_tampering(tmp_path: Path):
    output = tmp_path / "package"
    generate(output)
    path = output / "README.md"
    path.write_text(path.read_text("utf-8") + "tampered\n", encoding="utf-8")

    errors = validate(output)
    assert any("package manifest size mismatch: README.md" in item for item in errors)
    assert any("package manifest sha256 mismatch: README.md" in item for item in errors)


def test_summary_with_real_cases_requires_methodology_review_not_accuracy_claim(tmp_path: Path):
    output = tmp_path / "package"
    generate(output)
    populate_self_test(output)
    cases = _read_csv(output / "case_register.csv")
    for row in cases[:15]:
        row["evidence_class"] = "real_client"
        row["confidentiality"] = "nda_restricted"
    _write_csv(output / "case_register.csv", HEADERS["case_register.csv"], cases)
    seal(output)

    summary = build_summary(output)
    assert summary["status"] == "methodology_review_required"
    assert summary["pilot_sample"]["real_case_target_met"] is True
    assert summary["pilot_sample"]["robust_model_training_supported"] is False
    assert summary["claim_boundary"]["validated_accuracy_claim_permitted"] is False


def test_validator_requires_traceable_included_case_and_provisional_metrics(tmp_path: Path):
    output = tmp_path / "package"
    generate(output)
    cases = _read_csv(output / "case_register.csv")
    cases[0]["inclusion_status"] = "included"
    cases[0]["evidence_class"] = "real_client"
    _write_csv(output / "case_register.csv", HEADERS["case_register.csv"], cases)
    metrics = _read_csv(output / "metric_dictionary.csv")
    metrics[0]["final_threshold_allowed"] = "true"
    _write_csv(output / "metric_dictionary.csv", HEADERS["metric_dictionary.csv"], metrics)
    seal(output)

    errors = validate(output)
    assert any("included case requires creative_id" in item for item in errors)
    assert any("included case requires asset_sha256" in item for item in errors)
    assert any("final_threshold_allowed must remain false" in item for item in errors)


def test_validator_rejects_questionnaire_estimate_outside_scale(tmp_path: Path):
    output = tmp_path / "package"
    generate(output)
    rows = _read_csv(output / "questionnaire_evidence.csv")
    rows[0].update({
        "case_id": "C001", "study_id": "study", "response_source": "human",
        "respondent_count": "5", "metric_name": "clarity", "estimate": "9",
        "scale_min": "1", "scale_max": "7", "real_human_count": "5",
        "synthetic_count": "0",
    })
    _write_csv(output / "questionnaire_evidence.csv", HEADERS["questionnaire_evidence.csv"], rows)
    seal(output)
    assert any("estimate must be within scale bounds" in item for item in validate(output))
