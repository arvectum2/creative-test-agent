import json
from pathlib import Path

from PIL import Image

from scripts.synthetic_creative_golden_pack import (
    OBSERVABLES,
    UNSUPPORTED,
    build_spec,
    check_determinism,
    expand_cases,
    generate,
    validate_generated,
    validate_spec,
)


def test_candidate_pack_has_twelve_pairs_and_twenty_four_cases():
    spec = build_spec()
    cases = expand_cases(spec)

    assert validate_spec(spec) == []
    assert spec["status"] == "candidate"
    assert spec["fictional_only"] is True
    assert spec["pair_count"] == 12
    assert spec["case_count"] == 24
    assert len(spec["pairs"]) == 12
    assert len(cases) == 24
    assert len({case["case_id"] for case in cases}) == 24
    assert len({case["pair_id"] for case in cases}) == 12


def test_every_pair_is_a_controlled_a_b_contrast_on_declared_axis():
    spec = build_spec()

    for pair in spec["pairs"]:
        assert {variant["variant"] for variant in pair["variants"]} == {"A", "B"}
        axis = pair["contrast_axis"]
        statuses = []
        for variant in pair["variants"]:
            expected = {
                **pair["shared_expectations"],
                **variant["expected_observations"],
            }
            statuses.append(expected[axis])
            assert set(expected) <= set(OBSERVABLES)
        assert statuses[0] != statuses[1]


def test_pack_encodes_observations_not_effectiveness_claims():
    spec = build_spec()
    cases = expand_cases(spec)

    assert spec["evidence_boundary"]["unsupported"] == UNSUPPORTED
    for case in cases:
        assert case["render"]["brand"] == "NOVALEN"
        assert case["expected_observations"]["brand_is_fictional"] == "present"
        assert case["expected_observations"]["market_effectiveness_not_evaluated"] == "present"
        assert case["expected_observations"]["real_respondent_evidence"] == "absent"
        assert "expected_ctr" not in case
        assert "lift" not in case
        assert "score" not in case


def test_generation_creates_valid_pngs_contact_sheet_and_manifests(tmp_path: Path):
    output = tmp_path / "pack"
    manifest = generate(output)

    assert validate_generated(output) == []
    assert manifest["case_count"] == 24
    assert manifest["pair_count"] == 12
    assert manifest["prediction_generated"] is False
    assert manifest["real_respondents_used"] is False
    assert len(manifest["cases"]) == 24
    assert len({entry["sha256"] for entry in manifest["cases"]}) == 24

    with Image.open(output / "contact_sheet.png") as sheet:
        assert sheet.format == "PNG"
        assert sheet.width == 1200
        assert sheet.height == 1620

    generated = json.loads((output / "generated_manifest.json").read_text(encoding="utf-8"))
    generated_spec = json.loads((output / "pack_spec.json").read_text(encoding="utf-8"))
    assert generated["spec_sha256"] == manifest["spec_sha256"]
    assert generated_spec["pack"]["version"] == "1.0.0"

    for entry in manifest["cases"]:
        with Image.open(output / entry["filename"]) as image:
            assert image.format == "PNG"
            assert image.size == (entry["width"], entry["height"])
            assert image.info["case_id"] == entry["case_id"]
            assert image.info["pair_id"] == entry["pair_id"]
            assert image.info["pack_id"] == "synthetic-creative-golden-pack"


def test_generation_is_byte_deterministic_in_same_runtime():
    assert check_determinism() == []
