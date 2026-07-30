from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient

from scripts.cta_demo_001 import (
    build_acceptance_bundle,
    synthetic_demo_inputs,
    validate_acceptance_bundle,
)
from src.main import app
from src.modules.client_demo.service import compose_ozon_client_demo

client = TestClient(app)


def _synthetic_state(*, with_report: bool = False):
    _raw, workspace, visual_map = synthetic_demo_inputs()
    report = None
    if with_report:
        from src.modules.client_demo.schemas import DemoReportArtifact, DemoReportState

        report = DemoReportState(
            report_id="rpt2-demo-test",
            report_version="2.0",
            release_status="manual_review_required",
            generated_at="2026-07-30T00:00:00+00:00",
            manifest_sha256="a" * 64,
            artifacts=[
                DemoReportArtifact(
                    artifact_type="html",
                    filename="client_report_v2.html",
                    media_type="text/html",
                    sha256="b" * 64,
                    size_bytes=100,
                )
            ],
        )
    return compose_ozon_client_demo(
        workspace,
        campaign_id="OZON-007",
        report=report,
        visual_by_asset=visual_map,
    )


def test_demo_state_preserves_canonical_seven_step_evidence_path():
    demo = _synthetic_state(with_report=True)
    assert demo.demo_ready is True
    assert [item.ordinal for item in demo.steps] == list(range(1, 8))
    assert [item.code for item in demo.steps] == [
        "showcase_project",
        "campaign_selection",
        "original_creative",
        "visual_extraction",
        "funnel_diagnostics",
        "cg_tg_comparison",
        "report_download",
    ]
    assert all(item.status == "ready" for item in demo.steps)
    assert demo.primary_asset is not None
    assert demo.primary_asset.visual_extraction.observations
    assert demo.primary_asset.asset.diagnostic.status == "completed"
    assert demo.selected_campaign.outcomes
    assert demo.evidence_boundaries.causal_interpretation_allowed is False
    assert demo.evidence_boundaries.individual_asset_outcome_attribution_allowed is False
    assert demo.evidence_boundaries.missing_values_inferred is False


def test_demo_browser_and_json_routes_render_without_manual_uuid_or_json(monkeypatch):
    demo = _synthetic_state()
    monkeypatch.setattr(
        "src.modules.client_demo.ui_router.build_ozon_client_demo",
        lambda *args, **kwargs: demo,
    )
    monkeypatch.setattr(
        "src.modules.client_demo.router.build_ozon_client_demo",
        lambda *args, **kwargs: demo,
    )

    page = client.get("/ui/projects/synthetic-ozon-showcase/campaign-evidence/demo")
    assert page.status_code == 200
    assert "Ozon End-to-End Client Demo" in page.text
    assert "Показать исходный креатив" in page.text
    assert "Показать visual extraction" in page.text
    assert "Показать funnel diagnostics" in page.text
    assert "Сопоставить с CG/TG" in page.text
    assert "Generate evidence-bound report v2" in page.text
    assert "causal_interpretation_allowed=false" in page.text

    payload = client.get("/campaign-evidence/demo/projects/synthetic-ozon-showcase")
    assert payload.status_code == 200
    assert payload.json()["selected_case_id"] == "OZON-007"
    assert len(payload.json()["steps"]) == 7


def test_demo_report_form_redirects_to_integrity_checked_download_state(monkeypatch):
    fake_report = SimpleNamespace(
        report_id="rpt2-demo-test",
        report_version="2.0",
        release_status="manual_review_required",
        manifest_sha256="c" * 64,
    )
    monkeypatch.setattr(
        "src.modules.client_demo.ui_router.generate_client_report_v2",
        lambda *args, **kwargs: fake_report,
    )
    monkeypatch.setattr(
        "src.modules.client_demo.ui_router.write_audit_event",
        lambda *args, **kwargs: None,
    )
    response = client.post(
        "/ui/projects/synthetic-ozon-showcase/campaign-evidence/demo/report",
        data={"campaign_id": "campaign-theraflex", "locale": "ru"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert "campaign_id=campaign-theraflex" in response.headers["location"]
    assert "report_id=rpt2-demo-test" in response.headers["location"]


def test_synthetic_acceptance_bundle_is_complete_and_valid(tmp_path):
    output = tmp_path / "cta-demo-001"
    manifest = build_acceptance_bundle(output)
    assert manifest["task"] == "CTA-DEMO-001"
    assert manifest["synthetic_only"] is True
    assert manifest["real_client_materials_committed"] is False
    assert not validate_acceptance_bundle(output)
    assert (output / "cta_demo_001_manifest.json").is_file()
    assert (output / "cta_demo_001_operator_checklist.md").is_file()
    assert (output / "report_v2" / "client_report_v2_full.pptx").is_file()
