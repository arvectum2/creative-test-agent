from __future__ import annotations

import io
from copy import deepcopy
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from scripts.client_report_v2 import synthetic_workspace
from src.main import app
from src.modules.calibration_dashboard import service as dashboard_service
from src.modules.calibration_dashboard.models import CalibrationWorkflowMeasurement
from src.modules.calibration_dashboard.schemas import (
    CreateWorkflowMeasurementRequest,
    UpsertCalibrationCaseRequest,
)
from src.modules.finding_reviews import service as review_service
from src.modules.finding_reviews import service_commands, service_core
from src.modules.finding_reviews.schemas import (
    CreateFindingAdjudicationRequest,
    CreateFindingReviewRequest,
    CreateHumanFindingRequest,
)
from src.shared.db.repository import db_session
from src.shared.errors import AppError

REVIEWER_A = {
    "user_id": "cal-reviewer-a",
    "role": "analyst",
    "display_name": "Calibration Reviewer A",
    "is_active": True,
}
REVIEWER_B = {
    "user_id": "cal-reviewer-b",
    "role": "analyst",
    "display_name": "Calibration Reviewer B",
    "is_active": True,
}
ADJUDICATOR = {
    "user_id": "cal-adjudicator",
    "role": "manager",
    "display_name": "Calibration Adjudicator",
    "is_active": True,
}
SYSTEM_USER = {
    "user_id": "cal-system",
    "role": "admin",
    "display_name": "Calibration System",
    "is_active": True,
}


def _install_workspace(monkeypatch, project_id: str) -> dict:
    workspace = deepcopy(synthetic_workspace())
    workspace["project_id"] = project_id
    workspace["project_name"] = f"Synthetic calibration {project_id}"

    def loader(requested_project_id: str):
        if requested_project_id != project_id:
            raise AppError("project_not_found", "Project not found", 404)
        return deepcopy(workspace)

    monkeypatch.setattr(service_core, "_workspace_dict", loader)
    monkeypatch.setattr(service_commands, "_workspace_dict", loader)
    monkeypatch.setattr(dashboard_service, "get_campaign_evidence_workspace", loader)
    return workspace


def _review_body(
    sha256: str,
    *,
    decision: str = "supported",
    correctness: int = 5,
    actionability: int = 5,
    traceability: int = 5,
    severity_correctness: str = "correct",
) -> CreateFindingReviewRequest:
    return CreateFindingReviewRequest(
        expected_system_finding_sha256=sha256,
        reviewer_role="synthetic reviewer",
        decision=decision,
        correctness=correctness,
        relevance=5,
        actionability=actionability,
        traceability=traceability,
        severity_correctness=severity_correctness,
        reviewer_confidence=0.9,
        rationale="Synthetic CTA-CAL-003 acceptance evidence.",
    )


def _seed_dashboard(monkeypatch, project_id: str):
    workspace = _install_workspace(monkeypatch, project_id)
    findings = review_service.list_reviewable_findings(project_id, campaign_id="OZON-007")
    assert len(findings) == 2

    review_service.create_system_review(
        project_id,
        findings[0].finding_id,
        _review_body(findings[0].snapshot_sha256, correctness=5, actionability=5),
        user=REVIEWER_A,
    )
    review_service.create_system_review(
        project_id,
        findings[0].finding_id,
        _review_body(findings[0].snapshot_sha256, correctness=4, actionability=4),
        user=REVIEWER_B,
    )

    review_service.create_system_review(
        project_id,
        findings[1].finding_id,
        _review_body(findings[1].snapshot_sha256, decision="supported", correctness=5),
        user=REVIEWER_A,
    )
    review_service.create_system_review(
        project_id,
        findings[1].finding_id,
        _review_body(
            findings[1].snapshot_sha256,
            decision="harmful_false_positive",
            correctness=1,
            actionability=2,
            traceability=3,
            severity_correctness="overstated",
        ),
        user=REVIEWER_B,
    )
    disagreement = review_service.get_finding_disagreement(project_id, findings[1].finding_id)
    review_service.create_finding_adjudication(
        project_id,
        findings[1].finding_id,
        CreateFindingAdjudicationRequest(
            expected_basis_fingerprint_sha256=disagreement.basis_fingerprint_sha256,
            adjudicator_role="methodology owner",
            decision="harmful_false_positive",
            correctness=1,
            relevance=4,
            actionability=2,
            traceability=4,
            severity_correctness="overstated",
            adjudicator_confidence=0.9,
            rationale="Synthetic immutable adjudication for dashboard acceptance.",
        ),
        user=ADJUDICATOR,
    )

    campaign = workspace["campaigns"][0]
    asset = campaign["assets"][0]
    review_service.create_human_finding(
        project_id,
        CreateHumanFindingRequest(
            campaign_id=campaign["campaign_id"],
            creative_record_id=asset["creative_record_id"],
            creative_asset_id=asset["creative_asset_id"],
            criterion="proof_support",
            title="Missing proof qualifier",
            text="A human reviewer added a material omission separately from system findings.",
            proposed_severity="medium",
            reviewer_role="synthetic reviewer",
            relevance=5,
            actionability=4,
            traceability=4,
            reviewer_confidence=0.85,
            rationale="Synthetic human-added finding for calibration coverage.",
        ),
        user=REVIEWER_A,
    )

    dashboard_service.upsert_case_evidence(
        project_id,
        "OZON-007",
        UpsertCalibrationCaseRequest(
            evidence_class="real_client",
            inclusion_status="included",
            source_reference="synthetic:test-real-boundary",
        ),
        user=SYSTEM_USER,
    )
    dashboard_service.upsert_case_evidence(
        project_id,
        "OZON-003",
        UpsertCalibrationCaseRequest(
            evidence_class="synthetic",
            inclusion_status="included",
            source_reference="synthetic:test-fixture",
        ),
        user=SYSTEM_USER,
    )
    measurement = dashboard_service.create_workflow_measurement(
        project_id,
        CreateWorkflowMeasurementRequest(
            case_id="OZON-007",
            stage="intake_to_report",
            status="completed",
            wall_clock_seconds=600,
            operator_touch_seconds=180,
            manual_action_count=4,
            report_version="v2",
        ),
        user=SYSTEM_USER,
    )
    return workspace, measurement


def _metrics(dashboard):
    return {item.key: item for item in dashboard.metrics}


def test_workflow_measurement_rejects_touch_time_above_wall_clock():
    with pytest.raises(ValidationError, match="cannot exceed"):
        CreateWorkflowMeasurementRequest(
            case_id="C001",
            stage="report",
            wall_clock_seconds=10,
            operator_touch_seconds=11,
            manual_action_count=1,
        )


def test_dashboard_separates_evidence_and_computes_resolved_metrics(monkeypatch):
    project_id = f"cal-dashboard-{uuid4()}"
    _, measurement = _seed_dashboard(monkeypatch, project_id)

    dashboard = dashboard_service.compose_dashboard(project_id, evidence_filter="real_client")
    metrics = _metrics(dashboard)

    assert [item.case_id for item in dashboard.cases] == ["OZON-007"]
    assert dashboard.evidence_split["real_client"]["case_count"] == 1
    assert dashboard.evidence_split["synthetic"]["case_count"] == 1
    assert metrics["expert_supported_finding_rate"].value == 0.5
    assert metrics["finding_actionability_rate"].value == 0.5
    assert metrics["evidence_traceability_rate"].value == 1.0
    assert metrics["human_added_finding_count"].value == 1
    assert metrics["harmful_false_positive_count"].value == 1
    assert metrics["reviewer_disagreement_rate"].value == 0.5
    assert metrics["operator_touch_time_minutes"].value == 3.0
    assert metrics["manual_action_count"].value == 4.0
    assert metrics["historical_metric_coverage"].value == 1.0
    assert dashboard.claim_boundary["validated_model_accuracy_claimed"] is False
    assert dashboard.claim_boundary["real_and_synthetic_evidence_merged"] is False
    assert "validated model accuracy" in " ".join(dashboard.limitations)

    synthetic = dashboard_service.compose_dashboard(project_id, evidence_filter="synthetic")
    synthetic_metrics = _metrics(synthetic)
    assert [item.case_id for item in synthetic.cases] == ["OZON-003"]
    assert synthetic_metrics["expert_supported_finding_rate"].value is None
    assert synthetic_metrics["operator_touch_time_minutes"].value is None
    assert synthetic_metrics["historical_metric_coverage"].value == 1.0

    first_json = dashboard_service.dashboard_json_bytes(project_id, evidence_filter="real_client")
    second_json = dashboard_service.dashboard_json_bytes(project_id, evidence_filter="real_client")
    first_xlsx = dashboard_service.dashboard_xlsx_bytes(project_id, evidence_filter="real_client")
    second_xlsx = dashboard_service.dashboard_xlsx_bytes(project_id, evidence_filter="real_client")
    assert first_json == second_json
    assert first_xlsx == second_xlsx
    assert first_xlsx.startswith(b"PK")

    import zipfile

    with zipfile.ZipFile(io.BytesIO(first_xlsx)) as archive:
        core_xml = archive.read("docProps/core.xml").decode("utf-8")
    assert "dcterms:modified" in core_xml
    assert "1970-01-01T00:00:00Z" in core_xml
    assert "2026-" not in core_xml

    with pytest.raises(RuntimeError, match="append-only"):
        with db_session() as db:
            row = db.query(CalibrationWorkflowMeasurement).filter(
                CalibrationWorkflowMeasurement.id == measurement.id
            ).one()
            row.manual_action_count = 99


def test_dashboard_api_ui_exports_and_project_isolation(monkeypatch):
    project_id = f"cal-api-{uuid4()}"
    _seed_dashboard(monkeypatch, project_id)
    client = TestClient(app)

    response = client.get(
        f"/calibration-dashboard/projects/{project_id}",
        params={"evidence_filter": "real_client"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["evidence_filter"] == "real_client"
    assert payload["claim_boundary"]["validated_model_accuracy_claimed"] is False

    json_one = client.get(
        f"/calibration-dashboard/projects/{project_id}/export.json",
        params={"evidence_filter": "real_client"},
    )
    json_two = client.get(
        f"/calibration-dashboard/projects/{project_id}/export.json",
        params={"evidence_filter": "real_client"},
    )
    assert json_one.status_code == 200
    assert json_one.content == json_two.content
    assert json_one.headers["x-calibration-payload-sha256"]

    xlsx_one = client.get(
        f"/calibration-dashboard/projects/{project_id}/export.xlsx",
        params={"evidence_filter": "real_client"},
    )
    xlsx_two = client.get(
        f"/calibration-dashboard/projects/{project_id}/export.xlsx",
        params={"evidence_filter": "real_client"},
    )
    assert xlsx_one.status_code == 200
    assert xlsx_one.content == xlsx_two.content
    assert xlsx_one.content.startswith(b"PK")
    assert xlsx_one.headers["x-calibration-payload-sha256"]

    manifest = client.get(
        f"/calibration-dashboard/projects/{project_id}/manifest.json",
        params={"evidence_filter": "real_client"},
    )
    assert manifest.status_code == 200
    assert len(manifest.json()["files"]) == 2

    ui = client.get(
        f"/ui/projects/{project_id}/calibration",
        params={"evidence_filter": "real_client"},
    )
    assert ui.status_code == 200
    assert "Calibration Quality Dashboard" in ui.text
    assert "валидированной точностью модели" in ui.text
    assert "OZON-007" in ui.text
    assert "OZON-003" not in ui.text

    other = client.get(f"/calibration-dashboard/projects/other-{uuid4()}")
    assert other.status_code == 404
