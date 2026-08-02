"""Tests for the CTA-BENCH-002 benchmark harness.

Covers deterministic visual/LLM case set generation, the fixture self-test and
the loopback-only security boundary. These tests do not require any local model
server and must stay deterministic.
"""

import json

import pytest

from scripts.cta_bench_002 import llm_cases, visual_cases
from scripts.cta_bench_002.clients import (
    FixtureLlmBenchmarkClient,
    TesseractBenchmarkClient,
    VlmBenchmarkClient,
)


class TestVisualCaseSet:
    def test_generation_is_deterministic(self):
        errors = visual_cases.check_determinism()
        assert errors == []

    def test_validate_generated(self, tmp_path):
        visual_cases.generate(tmp_path / "visual")
        errors = visual_cases.validate_generated(tmp_path / "visual")
        assert errors == []

    def test_covers_all_tz_categories(self):
        from scripts.cta_bench_002.visual_cases import VISUAL_CATEGORIES

        cases = visual_cases.build_case_specs()
        categories = {case["category"] for case in cases}
        assert categories == set(VISUAL_CATEGORIES)

    def test_spec_sha_is_bound(self, tmp_path):
        visual_cases.generate(tmp_path / "visual")
        manifest = json.loads(
            (tmp_path / "visual" / "case_manifest_visual.json").read_text(encoding="utf-8")
        )
        spec = json.loads((tmp_path / "visual" / "case_spec.json").read_text(encoding="utf-8"))
        import hashlib

        expected = hashlib.sha256(
            json.dumps(spec, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        assert manifest["spec_sha256"] == expected


class TestLlmCaseSet:
    def test_manifest_is_valid(self, tmp_path):
        llm_cases.write_manifest(tmp_path / "llm")
        errors = llm_cases.validate_manifest(tmp_path / "llm")
        assert errors == []

    def test_covers_all_stages(self):
        manifest = llm_cases.build_manifest()
        stages = {case["stage"] for case in manifest["cases"]}
        assert stages == {
            "creative_summary",
            "audience_simulation",
            "brand_safety_review",
            "brandbook_compliance_review",
            "rubric_scoring",
            "final_recommendation",
        }

    def test_has_russian_and_english_cases(self):
        manifest = llm_cases.build_manifest()
        languages = {case["input_language"] for case in manifest["cases"]}
        assert "ru" in languages
        assert "en" in languages


class TestFixtureSelfTest:
    def test_fixture_is_schema_valid(self):
        from scripts.cta_bench_002.runner import _run_llm_candidate

        fixture = FixtureLlmBenchmarkClient()
        cases = llm_cases.build_manifest()["cases"]
        runs, summary = _run_llm_candidate("fixture:llm-contract", fixture, cases, repeats=1)
        assert summary["schema_valid_rate"] == 1.0
        assert summary["fallback_rate"] == 0.0
        assert summary["repair_rate"] == 0.0
        assert summary["forbidden_claim_total"] == 0

    def test_fixture_never_selectable(self):
        assert FixtureLlmBenchmarkClient.harness_only is True


class TestSecurityBoundary:
    def test_vlm_client_rejects_non_loopback(self):
        with pytest.raises(ValueError):
            VlmBenchmarkClient(
                base_url="http://example.com:8080",
                model="test-model",
            )

    def test_vlm_client_accepts_loopback(self):
        client = VlmBenchmarkClient(
            base_url="http://127.0.0.1:8083",
            model="test-model",
        )
        assert client.model == "test-model"


class TestAggregateIntegrity:
    def test_required_artifacts_use_case_pack_paths(self):
        from scripts.cta_bench_002.aggregate import REQUIRED_ARTIFACTS

        assert "case_pack/visual/case_manifest_visual.json" in REQUIRED_ARTIFACTS
        assert "case_pack/llm/case_manifest_llm.json" in REQUIRED_ARTIFACTS

    def test_integrity_manifest_skips_self_and_uses_relative_paths(self, tmp_path):
        from scripts.cta_bench_002 import metrics

        (tmp_path / "case_pack").mkdir()
        visual = tmp_path / "case_pack" / "visual"
        visual.mkdir()
        (visual / "case_manifest_visual.json").write_text("{}", encoding="utf-8")
        (tmp_path / "runs.jsonl").write_text("[]\n", encoding="utf-8")

        files = [
            tmp_path / "runs.jsonl",
            tmp_path / "case_pack" / "visual" / "case_manifest_visual.json",
            tmp_path / "integrity_manifest.json",
        ]
        metrics.write_integrity_manifest(tmp_path, files)
        manifest = json.loads((tmp_path / "integrity_manifest.json").read_text(encoding="utf-8"))
        names = {item["filename"] for item in manifest["artifacts"]}
        assert names == {"runs.jsonl", "case_pack/visual/case_manifest_visual.json"}
        assert "integrity_manifest.json" not in names

    def test_validate_artifacts_accepts_aggregated_revision(self, tmp_path):
        from scripts.cta_bench_002 import metrics
        from scripts.cta_bench_002.aggregate import REQUIRED_ARTIFACTS, validate_artifacts

        (tmp_path / "case_pack" / "visual").mkdir(parents=True)
        (tmp_path / "case_pack" / "llm").mkdir(parents=True)
        for name in REQUIRED_ARTIFACTS:
            path = tmp_path / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("x\n", encoding="utf-8")
        metrics.write_integrity_manifest(
            tmp_path, [tmp_path / name for name in REQUIRED_ARTIFACTS]
        )
        assert validate_artifacts(tmp_path) == []


class TestRunCompatibilityFailure:
    def test_run_records_unavailable_candidate(self, tmp_path, monkeypatch):
        from scripts.cta_bench_002 import __main__ as cli
        from scripts.cta_bench_002.clients import EndpointError

        revision_dir = tmp_path / "artifacts" / "cta-bench-002" / "20260801-test"
        visual_dir = revision_dir / "case_pack" / "visual"
        llm_dir = revision_dir / "case_pack" / "llm"
        visual_dir.mkdir(parents=True)
        llm_dir.mkdir(parents=True)

        from scripts.cta_bench_002 import llm_cases, visual_cases

        visual_cases.generate(visual_dir)
        llm_cases.write_manifest(llm_dir)
        (revision_dir / "environment.json").write_text("{}", encoding="utf-8")

        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(cli, "_revision_dir", lambda revision: revision_dir)
        import scripts.cta_bench_002.runner as runner_mod

        monkeypatch.setattr(
            runner_mod,
            "_client_for",
            lambda candidate_id, base_url, model, timeout: (_ for _ in ()).throw(
                EndpointError("PaddleOCR is not installed: No module named 'paddleocr'")
            ),
        )

        class Args:
            revision = "20260801-test"
            candidate = "OCR-CHALLENGER"
            repeats = 2
            timeout_seconds = 120

        result = cli._cmd_run(Args())
        assert result == 0
        persisted = json.loads(
            (revision_dir / "candidates" / "OCR-CHALLENGER" / "runs.json").read_text(encoding="utf-8")
        )
        assert persisted["summary"]["status"] == "unavailable"
        assert "compatibility_failure" in persisted["summary"]
