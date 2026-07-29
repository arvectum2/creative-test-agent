from __future__ import annotations

from uuid import uuid4

from fastapi.testclient import TestClient

from src.main import app
from src.modules.clients.models import Client
from src.modules.creative_assets.models import CreativeAsset
from src.modules.normalized_data.models import (
    Campaign,
    CreativeRecord,
    NormalizationRun,
    NormalizationRunStatus,
    PerformanceObservation,
    Placement,
)
from src.modules.projects.models import Project, ProjectStatus
from src.modules.test_runs.models import TestRun
from src.shared.db.repository import db_session, json_dumps


client = TestClient(app)


def _seed_campaign_evidence_workspace() -> dict[str, str]:
    suffix = uuid4().hex
    with db_session() as db:
        account = Client(name=f"Synthetic Ozon {suffix}", industry="test")
        db.add(account)
        db.flush()
        project = Project(
            client_id=account.id,
            name=f"Synthetic Ozon Campaign Evidence {suffix}",
            status=ProjectStatus.active,
        )
        db.add(project)
        db.flush()
        run = NormalizationRun(
            source_table_id=f"synthetic-table-{suffix}",
            source_file_id=f"synthetic-file-{suffix}",
            import_session_id=f"synthetic-session-{suffix}",
            project_id=project.id,
            run_number=1,
            normalizer_name="ozon_showcase_loader",
            normalizer_version="1.0.0",
            mapping_fingerprint="a" * 64,
            mapping_snapshot_json="{}",
            status=NormalizationRunStatus.completed,
            campaign_count=5,
            creative_count=8,
            placement_count=15,
            performance_observation_count=15,
            warnings_json=json_dumps({
                "source_fingerprint": "b" * 64,
                "limitations": [
                    {"code": "campaign_multi_asset"},
                    {"code": "campaign_without_accepted_asset"},
                    {"code": "asset_without_outcomes"},
                ],
            }),
        )
        db.add(run)
        db.flush()

        specs = [
            ("OZON-007", "Theraflex Ultra", 0.341, 0.412, 7.1),
            ("OZON-003", "Rennie", 0.221, 0.258, 3.7),
            ("OZON-001", "Bepanthen Ointment", 0.242, 0.260, 1.8),
            ("OZON-006", "Supradyn Energy", 0.219, 0.240, 2.1),
            ("OZON-004", "Relief", 0.291, 0.326, 3.5),
        ]
        campaigns: dict[str, Campaign] = {}
        for case_id, brand, _, _, _ in specs:
            campaign = Campaign(
                normalization_run_id=run.id,
                project_id=project.id,
                reference_key=case_id,
                brand=brand,
                product=brand,
                metadata_json=json_dumps({
                    "case_id": case_id,
                    "period_start": "2025-01-01",
                    "period_end": "2025-02-01",
                    "platform": "OZON",
                    "campaign_level_outcomes": True,
                    "individual_asset_attribution_allowed": False,
                }),
            )
            db.add(campaign)
            db.flush()
            campaigns[case_id] = campaign

        assets: dict[str, CreativeAsset] = {}

        def add_asset(case_id, filename, status, confidence, platform="OZON"):
            asset = CreativeAsset(
                title=filename,
                asset_type="image",
                original_filename=filename,
                file_path=f"/tmp/{filename}",
                mime_type="image/png",
                file_size_bytes=100,
                project_id=project.id,
                metadata_json=json_dumps({
                    "linked_case_id": case_id,
                    "linkage_status": status,
                    "linkage_confidence": confidence,
                    "brand": campaigns[case_id].brand if case_id else "Triderm",
                    "inferred_platform": platform,
                    "linkage_notes": ["Synthetic evidence only"],
                }),
            )
            db.add(asset)
            db.flush()
            record = CreativeRecord(
                normalization_run_id=run.id,
                project_id=project.id,
                reference_key=uuid4().hex,
                display_reference=filename,
                creative_asset_id=asset.id,
                metadata_json=json_dumps({
                    "linked_case_id": case_id,
                    "linkage_status": status,
                    "linkage_confidence": confidence,
                    "brand": campaigns[case_id].brand if case_id else "Triderm",
                    "inferred_platform": platform,
                    "notes": ["Synthetic evidence only"],
                }),
            )
            db.add(record)
            db.flush()
            assets[filename] = asset
            return asset

        add_asset("OZON-007", "theraflex-a.png", "one_to_many", 0.8)
        add_asset("OZON-007", "theraflex-b.png", "one_to_many", 0.8)
        add_asset("OZON-003", "rennie-a.png", "one_to_many", 0.7)
        add_asset("OZON-003", "rennie-b.png", "one_to_many", 0.7)
        add_asset("OZON-001", "bepanthen-a.png", "one_to_many", 0.8)
        add_asset("OZON-006", "supradyn-energy.png", "exact", 1.0)
        add_asset("OZON-004", "relief-vk.png", "rejected", 1.0, platform="VK")

        triderm = CreativeAsset(
            title="Triderm",
            asset_type="image",
            original_filename="triderm.png",
            file_path="/tmp/triderm.png",
            mime_type="image/png",
            file_size_bytes=100,
            project_id=project.id,
            metadata_json=json_dumps({
                "linked_case_id": None,
                "linkage_status": "missing",
                "linkage_confidence": 0.0,
                "brand": "Triderm",
                "inferred_platform": "OZON",
                "linkage_notes": ["No outcome row"],
            }),
        )
        db.add(triderm)
        db.flush()
        db.add(CreativeRecord(
            normalization_run_id=run.id,
            project_id=project.id,
            reference_key=uuid4().hex,
            display_reference="triderm.png",
            creative_asset_id=triderm.id,
            metadata_json=json_dumps({
                "linked_case_id": None,
                "linkage_status": "missing",
                "linkage_confidence": 0.0,
                "brand": "Triderm",
                "inferred_platform": "OZON",
                "notes": ["No outcome row"],
            }),
        ))

        metric_names = ("ad_recall", "awareness", "purchase_intent")
        for case_id, _brand, cg, tg, uplift in specs:
            for index, metric in enumerate(metric_names):
                source_row_id = f"{case_id}-{metric}-{suffix}"
                placement = Placement(
                    normalization_run_id=run.id,
                    project_id=project.id,
                    source_row_id=source_row_id,
                    campaign_id=campaigns[case_id].id,
                    creative_record_id=None,
                    platform_id=None,
                    audience_segment_id=None,
                    placement_type="campaign_brand_lift",
                    metadata_json=json_dumps({
                        "campaign_level_outcome": True,
                        "individual_asset_attribution_allowed": False,
                    }),
                )
                db.add(placement)
                db.flush()
                db.add(PerformanceObservation(
                    normalization_run_id=run.id,
                    project_id=project.id,
                    source_row_id=source_row_id,
                    placement_id=placement.id,
                    metadata_json=json_dumps({
                        "case_id": case_id,
                        "metric": metric,
                        "control_n": 1000,
                        "test_n": 1100,
                        "cg_rate": cg + index * 0.001,
                        "tg_rate": tg + index * 0.001,
                        "uplift_pp_descriptive": uplift,
                        "evidence_status": "descriptive_only",
                        "platform": "OZON",
                        "period_start": "2025-01-01",
                        "period_end": "2025-02-01",
                        "causal_interpretation_allowed": False,
                        "numeric_prediction_generated": False,
                        "notes": [],
                    }),
                ))

        diagnostic_asset = assets["supradyn-energy.png"]
        diagnostic = TestRun(
            creative_asset_id=diagnostic_asset.id,
            project_id=project.id,
            status="completed",
            summary="Clear single-minded proposition with a visible packshot.",
            overall_score=7.2,
            final_recommendation="revise",
            structured_findings_json=json_dumps({
                "findings": [{"title": "CTA is visible", "visual_evidence_refs": ["visual:test"]}],
                "scorecard": [{"criterion": "brand_prominence_and_legibility", "score": 8, "rationale": "Brand is readable"}],
                "risks": [{"risk": "Generic benefit language"}],
                "effective_recommendation": "manual_review_required",
                "visual_traceability_status": "complete",
                "visual_decision_status": "manual_review_required",
                "final_recommendation_details": {"confidence_score": 0.8},
            }),
        )
        db.add(diagnostic)
        db.flush()
        return {
            "project_id": project.id,
            "theraflex_campaign_id": campaigns["OZON-007"].id,
            "supradyn_campaign_id": campaigns["OZON-006"].id,
        }


def test_campaign_evidence_api_keeps_facts_diagnostics_and_linkage_separate():
    ids = _seed_campaign_evidence_workspace()
    response = client.get(f"/campaign-evidence/projects/{ids['project_id']}")
    assert response.status_code == 200
    body = response.json()

    assert body["summary"]["campaign_count"] == 5
    assert body["summary"]["outcome_count"] == 15
    assert body["summary"]["unlabelled_asset_count"] == 1
    assert body["evidence_boundaries"] == {
        "causal_interpretation_allowed": False,
        "numeric_uplift_prediction_generated": False,
        "individual_asset_outcome_attribution_allowed": False,
        "missing_values_inferred": False,
        "diagnostics_are_model_outputs_not_factual_outcomes": True,
    }
    assert [item["case_id"] for item in body["campaigns"][:4]] == [
        "OZON-007", "OZON-003", "OZON-001", "OZON-006"
    ]

    theraflex = next(item for item in body["campaigns"] if item["case_id"] == "OZON-007")
    assert theraflex["individual_asset_attribution_allowed"] is False
    assert len(theraflex["assets"]) == 2
    assert {item["linkage_status"] for item in theraflex["assets"]} == {"one_to_many"}
    assert "campaign_multi_asset" in {item["code"] for item in theraflex["limitations"]}
    assert all(item["causal_interpretation_allowed"] is False for item in theraflex["outcomes"])

    relief = next(item for item in body["campaigns"] if item["case_id"] == "OZON-004")
    assert relief["assets"][0]["linkage_status"] == "rejected"
    assert relief["assets"][0]["accepted_for_campaign_set"] is False
    assert {item["code"] for item in relief["limitations"]} >= {
        "campaign_without_accepted_asset", "rejected_asset_link"
    }

    assert body["unlabelled_assets"][0]["title"] == "Triderm"
    assert body["unlabelled_assets"][0]["linkage_status"] == "missing"


def test_campaign_evidence_detail_exposes_asset_level_diagnostic_without_changing_outcomes():
    ids = _seed_campaign_evidence_workspace()
    response = client.get(
        f"/campaign-evidence/projects/{ids['project_id']}/campaigns/{ids['supradyn_campaign_id']}"
    )
    assert response.status_code == 200
    body = response.json()

    assert body["case_id"] == "OZON-006"
    assert body["outcomes"][0]["cg_rate"] == 0.219
    assert body["outcomes"][0]["tg_rate"] == 0.24
    assert body["outcomes"][0]["uplift_pp_descriptive"] == 2.1
    diagnostic = body["assets"][0]["diagnostic"]
    assert diagnostic["status"] == "completed"
    assert diagnostic["overall_score"] == 7.2
    assert diagnostic["effective_recommendation"] == "manual_review_required"
    assert diagnostic["visual_traceability_status"] == "complete"
    assert body["individual_asset_attribution_allowed"] is False


def test_campaign_evidence_browser_pages_render_offline_workspace_and_limitations():
    ids = _seed_campaign_evidence_workspace()
    workspace = client.get(f"/ui/projects/{ids['project_id']}/campaign-evidence")
    assert workspace.status_code == 200
    assert "Ozon Campaign Evidence Workspace" in workspace.text
    assert "Theraflex Ultra" in workspace.text
    assert "Rennie" in workspace.text
    assert "Triderm" in workspace.text
    assert "campaign_without_accepted_asset" in workspace.text

    detail = client.get(
        f"/ui/projects/{ids['project_id']}/campaign-evidence/{ids['theraflex_campaign_id']}"
    )
    assert detail.status_code == 200
    assert "Observed CG/TG outcomes" in detail.text
    assert "Agent diagnostics by asset" in detail.text
    assert "individual asset outcome attribution allowed" in detail.text.lower()
    assert "campaign_multi_asset" in detail.text
