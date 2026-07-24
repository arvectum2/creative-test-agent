from __future__ import annotations

import hashlib
import json
from pathlib import Path

from src.modules.pre_tz_demo import run_messy_demo


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def test_pre_tz_messy_demo_runs_complete_local_pipeline(tmp_path):
    workspace = tmp_path / "cta_pre_012_demo"

    manifest = run_messy_demo(
        workspace,
        reset=True,
        respondent_count=8,
    )

    assert manifest["status"] == "completed"
    assert manifest["safety"] == {
        "local_only": True,
        "cloud_llm_allowed": False,
        "prediction_generated": False,
        "fabricated_ctr_generated": False,
        "synthetic_responses_label": "synthetic",
        "synthetic_responses_are_real_people": False,
    }

    assert manifest["import"]["session_status"] == "completed"
    assert manifest["import"]["integrity_ok"] is True
    assert manifest["inspection"]["status"] == "completed"
    assert manifest["inspection"]["format"] == "csv"
    assert manifest["inspection"]["data_rows"] >= 15

    assert manifest["mapping"]["confirmed_count"] == 10
    assert "Комментарий клиента" in manifest["mapping"]["custom_headers_preserved"]
    assert "Лишнее поле" in manifest["mapping"]["custom_headers_preserved"]

    assert manifest["normalization"]["status"] == "completed"
    assert manifest["normalization"]["source_rows"] >= 15
    assert (
        manifest["normalization"]["normalized_rows"]
        + manifest["normalization"]["partial_rows"]
        >= 15
    )
    assert manifest["normalization"]["creative_records"] >= 3
    assert manifest["normalization"]["performance_observations"] >= 15

    assert manifest["data_quality"]["total_issues"] > 0
    assert manifest["data_quality"]["overall_status"] in {
        "passed",
        "review_required",
        "blocked",
    }
    assert (
        manifest["clarifications"]["client_question_count"]
        + manifest["clarifications"]["analyst_question_count"]
        > 0
    )

    capabilities = manifest["prediction_readiness"]["capabilities"]
    assert set(capabilities) == {
        "historical_ctr_prediction",
        "creative_lift_estimation",
        "synthetic_click_intent",
        "brand_lift_proxy",
        "compliance_risk_review",
    }
    assert manifest["prediction_readiness"]["prediction_generated"] is False

    proxy = manifest["quantitative_proxy"]
    assert proxy["study_status"] == "closed"
    assert proxy["response_count"] == 8
    assert proxy["generated_response_count"] == 8
    assert proxy["source_counts"] == {"synthetic": 8}
    assert proxy["not_real_people"] is True

    report = manifest["report"]
    report_path = Path(report["path"])
    assert report["status"] == "completed"
    assert report_path.is_file()
    assert report["sheet_count"] >= 8
    assert report["sha256"] == report["verified_sha256"] == _sha256(report_path)

    manifest_path = workspace / "demo_manifest.json"
    assert manifest_path.is_file()
    persisted = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert persisted["report"]["sha256"] == report["sha256"]
