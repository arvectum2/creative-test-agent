import json
from pathlib import Path

import pytest

from scripts.synthetic_creative_golden_pack import generate
from src.shared.vision.benchmarking import (
    GoldenContractFixtureCandidate,
    OllamaVlmCandidate,
    parse_json_object,
    run_benchmark,
    score_observations,
    score_text,
    validate_benchmark,
)


def test_golden_contract_self_test_produces_integrity_checked_artifacts(tmp_path: Path):
    golden_dir = tmp_path / "golden"
    output_dir = tmp_path / "benchmark"
    generate(golden_dir)

    result = run_benchmark(
        pack_dir=golden_dir,
        output_dir=output_dir,
        candidates=[GoldenContractFixtureCandidate()],
        repeats=2,
    )

    assert validate_benchmark(output_dir) == []
    assert result["evidence_boundary"]["model_selected"] is False
    assert result["evidence_boundary"]["prediction_generated"] is False
    candidate = result["candidates"][0]
    assert candidate["candidate"]["harness_only"] is True
    assert candidate["summary"]["eligible_for_model_selection"] is False
    assert candidate["summary"]["text_quality_first_pass"]["f1"] == 1.0
    assert candidate["summary"]["observation_quality_first_pass"]["f1"] == 1.0
    assert candidate["summary"]["observation_quality_consensus"]["f1"] == 1.0
    assert candidate["summary"]["observation_repeatability"]["mean_agreement"] == 1.0
    assert (output_dir / "benchmark_results.json").is_file()
    assert (output_dir / "benchmark_summary.csv").is_file()
    assert (output_dir / "benchmark_report.md").is_file()
    assert (output_dir / "benchmark_manifest.json").is_file()


def test_observation_scoring_counts_uncertain_and_missing_as_abstention():
    score = score_observations(
        {
            "cta_present": "present",
            "brand_present": "absent",
            "offer_clarity": "present",
        },
        {
            "cta_present": "present",
            "brand_present": "uncertain",
        },
    )

    assert score["evaluated_slots"] == 3
    assert score["answered_slots"] == 1
    assert score["correct_slots"] == 1
    assert score["precision"] == 1.0
    assert score["recall"] == pytest.approx(1 / 3)
    assert score["abstention_rate"] == pytest.approx(2 / 3)


def test_text_scoring_uses_token_multisets():
    score = score_text("NOVALEN Learn more Learn more", "novalen learn more")

    assert score["expected_token_count"] == 5
    assert score["detected_token_count"] == 3
    assert score["matched_token_count"] == 3
    assert score["precision"] == 1.0
    assert score["recall"] == pytest.approx(3 / 5)


def test_vlm_json_parser_recovers_fenced_and_surrounded_object():
    fenced = '```json\n{"observations":{"cta_present":"present"},"detected_text":"CTA"}\n```'
    surrounded = 'Result follows: {"observations":{"cta_present":"absent"}} done.'

    assert parse_json_object(fenced)["detected_text"] == "CTA"
    assert (
        parse_json_object(surrounded)["observations"]["cta_present"]
        == "absent"
    )


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com",
        "http://192.168.1.20:11434",
        "http://ollama.internal:11434",
    ],
)
def test_vlm_candidate_rejects_non_loopback_endpoints(url: str):
    with pytest.raises(ValueError, match="loopback-only"):
        OllamaVlmCandidate("test-model", url)


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1:11434",
        "http://localhost:11434",
        "http://[::1]:11434",
    ],
)
def test_vlm_candidate_accepts_loopback_endpoints(url: str):
    candidate = OllamaVlmCandidate("test-model", url)

    assert candidate.candidate_id == "vlm:test-model"


def test_benchmark_validation_detects_tampered_artifact(tmp_path: Path):
    golden_dir = tmp_path / "golden"
    output_dir = tmp_path / "benchmark"
    generate(golden_dir)
    run_benchmark(
        pack_dir=golden_dir,
        output_dir=output_dir,
        candidates=[GoldenContractFixtureCandidate()],
        repeats=1,
        case_limit=2,
    )
    report = output_dir / "benchmark_report.md"
    report.write_text(report.read_text(encoding="utf-8") + "\ntampered\n", encoding="utf-8")

    errors = validate_benchmark(output_dir)

    assert "benchmark artifact SHA-256 mismatch: benchmark_report.md" in errors


def test_results_do_not_auto_select_fixture(tmp_path: Path):
    golden_dir = tmp_path / "golden"
    output_dir = tmp_path / "benchmark"
    generate(golden_dir)
    run_benchmark(
        pack_dir=golden_dir,
        output_dir=output_dir,
        candidates=[GoldenContractFixtureCandidate()],
        repeats=1,
        case_limit=1,
    )

    payload = json.loads(
        (output_dir / "benchmark_results.json").read_text(encoding="utf-8")
    )

    assert payload["evidence_boundary"]["model_selected"] is False
    assert payload["candidates"][0]["summary"]["automatic_selection_performed"] is False
