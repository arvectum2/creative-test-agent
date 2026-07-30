from __future__ import annotations

import json
from pathlib import Path

from scripts.client_report_v2 import FIXED_GENERATED_AT, synthetic_assessments, synthetic_workspace
from src.modules.client_report_v2.rendering import (
    ARTIFACT_MEDIA_TYPES,
    build_report_bundle,
    compose_report_evidence,
    validate_evidence,
    validate_report_bundle,
)


def _evidence():
    evidence = compose_report_evidence(
        synthetic_workspace(),
        expert_assessments=synthetic_assessments(),
        locale="ru",
        generated_at=FIXED_GENERATED_AT,
    )
    evidence["input_fingerprint"] = "f" * 64
    evidence["report_run_id"] = "rpt2-test-acceptance"
    return evidence


def test_required_layers_and_finding_references_are_evidence_bound():
    evidence = _evidence()
    assert not validate_evidence(evidence)
    assert set(evidence) >= {
        "observed_facts",
        "agent_diagnostics",
        "factual_outcomes",
        "expert_assessment",
        "limitations_and_confidence",
        "evidence_registry",
    }
    registry = evidence["evidence_registry"]
    for finding in evidence["agent_diagnostics"]["findings"]:
        assert finding["scope"] == "individual_asset"
        assert finding["evidence_references"]
        assert all(reference in registry for reference in finding["evidence_references"])


def test_campaign_outcomes_remain_campaign_set_and_missing_values_stay_missing():
    evidence = _evidence()
    outcomes = evidence["factual_outcomes"]["outcomes"]
    assert outcomes
    assert all(item["scope"] == "campaign_set" for item in outcomes)
    assert all(item["individual_asset_attribution_allowed"] is False for item in outcomes)
    assert all(item["causal_interpretation_allowed"] is False for item in outcomes)
    partial = next(item for item in outcomes if item["observation_id"] == "obs-rennie-awareness")
    assert partial["tg_rate"] is None
    assert partial["uplift_pp_descriptive"] is None


def test_missing_expert_assessment_is_explicit_not_reviewed():
    evidence = _evidence()
    assessments = evidence["expert_assessment"]["assessments"]
    assert len(assessments) == evidence["summary"]["finding_count"]
    missing = next(item for item in assessments if item["finding_id"] == "finding:test-run-rennie:1")
    assert missing["verdict"] == "not_reviewed"
    assert missing["status"] == "not_reviewed"
    assert evidence["summary"]["release_status"] == "manual_review_required"


def test_all_six_formats_are_generated_and_integrity_checked(tmp_path: Path):
    manifest = build_report_bundle(_evidence(), tmp_path)
    assert not validate_report_bundle(tmp_path)
    assert {item["artifact_type"] for item in manifest["artifacts"]} == set(ARTIFACT_MEDIA_TYPES)
    assert (tmp_path / "client_report_v2.html").is_file()
    assert (tmp_path / "client_report_v2_one_page.pptx").is_file()
    assert (tmp_path / "client_report_v2_full.pptx").is_file()
    assert (tmp_path / "client_report_v2.docx").is_file()
    assert (tmp_path / "client_report_v2_evidence.json").is_file()
    assert (tmp_path / "client_report_v2_appendix.xlsx").is_file()


def test_bundle_generation_is_deterministic(tmp_path: Path):
    first = build_report_bundle(_evidence(), tmp_path / "first")
    second = build_report_bundle(_evidence(), tmp_path / "second")
    assert {
        item["artifact_type"]: item["sha256"] for item in first["artifacts"]
    } == {
        item["artifact_type"]: item["sha256"] for item in second["artifacts"]
    }
    first_evidence = json.loads((tmp_path / "first" / "client_report_v2_evidence.json").read_text())
    assert first_evidence["claim_boundary"]["missing_values_inferred"] is False
