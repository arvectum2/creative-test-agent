from __future__ import annotations

import csv
import io
import json
import zipfile
from copy import deepcopy
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from scripts.client_report_v2 import synthetic_workspace
from src.main import app
from src.modules.finding_reviews.models import FindingReview
from src.modules.finding_reviews.schemas import (
    CreateFindingReviewRequest,
    CreateHumanFindingRequest,
)
from src.modules.finding_reviews import service
from src.shared.db.repository import db_session
from src.shared.errors import AppError

USER = {
    "user_id": "reviewer-1",
    "role": "analyst",
    "display_name": "Synthetic Reviewer",
    "is_active": True,
}


def _workspace(project_id: str) -> dict:
    value = deepcopy(synthetic_workspace())
    value["project_id"] = project_id
    value["project_name"] = f"Synthetic {project_id}"
    return value


def _install_workspace(monkeypatch, project_id: str):
    workspace = _workspace(project_id)

    def loader(requested_project_id: str):
        if requested_project_id != project_id:
            raise AppError("project_not_found", "Project not found", 404)
        return deepcopy(workspace)

    monkeypatch.setattr(service, "_workspace_dict", loader)
    return workspace


def _review_body(snapshot_sha256: str, *, decision: str = "supported"):
    return CreateFindingReviewRequest(
        expected_system_finding_sha256=snapshot_sha256,
        reviewer_role="senior strategist",
        decision=decision,
        correctness=5,
        relevance=4,
        actionability=4,
        traceability=5,
        severity_correctness="correct",
        reviewer_confidence=0.9,
        rationale="Synthetic acceptance review.",
        comment="No client data.",
    )


def test_system_review_is_append_only_and_preserves_snapshot(monkeypatch):
    project_id = f"review-{uuid4()}"
    _install_workspace(monkeypatch, project_id)
    finding = service.list_reviewable_findings(project_id)[0]

    first = service.create_system_review(
        project_id,
        finding.finding_id,
        _review_body(finding.snapshot_sha256),
        user=USER,
    )
    second = service.create_system_review(
        project_id,
        finding.finding_id,
        _review_body(finding.snapshot_sha256, decision="needs_rewording"),
        user=USER,
    )

    assert first.revision_number == 1
    assert second.revision_number == 2
    assert second.supersedes_review_id == first.id
    assert first.system_finding_snapshot == finding.system_finding_snapshot
    assert first.system_finding_snapshot_sha256 == finding.snapshot_sha256

    history = service.list_project_reviews(project_id, finding_id=finding.finding_id)
    assert [item.decision for item in history] == ["supported", "needs_rewording"]
    assert history[0].system_finding_snapshot == history[1].system_finding_snapshot

    with pytest.raises(RuntimeError, match="append-only"):
        with db_session() as db:
            row = db.query(FindingReview).filter(FindingReview.id == first.id).one()
            row.rationale = "Forbidden mutation"


def test_stale_system_snapshot_is_rejected(monkeypatch):
    project_id = f"stale-{uuid4()}"
    _install_workspace(monkeypatch, project_id)
    finding = service.list_reviewable_findings(project_id)[0]
    body = _review_body("0" * 64)

    with pytest.raises(AppError) as exc_info:
        service.create_system_review(project_id, finding.finding_id, body, user=USER)

    assert exc_info.value.code == "finding_snapshot_changed"
    assert exc_info.value.status_code == 409
    assert service.list_project_reviews(project_id) == []


def test_missed_by_system_creates_human_finding_without_system_snapshot(monkeypatch):
    project_id = f"human-{uuid4()}"
    workspace = _install_workspace(monkeypatch, project_id)
    campaign = workspace["campaigns"][0]
    asset = campaign["assets"][0]

    review = service.create_human_finding(
        project_id,
        CreateHumanFindingRequest(
            campaign_id=campaign["campaign_id"],
            creative_record_id=asset["creative_record_id"],
            creative_asset_id=asset["creative_asset_id"],
            criterion="missing_claim_risk",
            title="A material omission",
            text="The system did not identify this synthetic issue.",
            proposed_severity="high",
            reviewer_role="medical reviewer",
            relevance=5,
            actionability=5,
            traceability=4,
            reviewer_confidence=0.85,
            rationale="Human-added omission for acceptance.",
        ),
        user=USER,
    )

    assert review.source_kind == "human"
    assert review.decision == "missed_by_system"
    assert review.system_finding_snapshot is None
    assert review.system_finding_snapshot_sha256 is None
    assert review.human_finding_snapshot["system_finding_fabricated"] is False
    assert review.human_finding_snapshot_sha256


def test_project_scope_does_not_leak_reviews(monkeypatch):
    project_id = f"scope-{uuid4()}"
    _install_workspace(monkeypatch, project_id)
    finding = service.list_reviewable_findings(project_id)[0]
    service.create_system_review(
        project_id,
        finding.finding_id,
        _review_body(finding.snapshot_sha256),
        user=USER,
    )

    other_project = f"other-{uuid4()}"
    with pytest.raises(AppError) as exc_info:
        service.list_project_reviews(other_project)
    assert exc_info.value.code == "project_not_found"


def test_evidence_and_calibration_exports_are_complete_and_deterministic(monkeypatch):
    project_id = f"export-{uuid4()}"
    workspace = _install_workspace(monkeypatch, project_id)
    finding = service.list_reviewable_findings(project_id)[0]
    service.create_system_review(
        project_id,
        finding.finding_id,
        _review_body(finding.snapshot_sha256),
        user=USER,
    )
    campaign = workspace["campaigns"][0]
    service.create_human_finding(
        project_id,
        CreateHumanFindingRequest(
            campaign_id=campaign["campaign_id"],
            criterion="human_omission",
            title="Synthetic omission",
            text="Human-added finding.",
            proposed_severity="medium",
            reviewer_role="strategist",
            relevance=5,
            actionability=4,
            traceability=3,
            reviewer_confidence=0.75,
            rationale="Needed for calibration export.",
        ),
        user=USER,
    )

    evidence = service.export_review_evidence(project_id).model_dump(mode="json")
    assert evidence["review_count"] == 2
    assert evidence["system_review_count"] == 1
    assert evidence["human_finding_count"] == 1
    assert evidence["claim_boundary"]["system_findings_mutated"] is False

    first, filename = service.build_calibration_package(project_id)
    second, _ = service.build_calibration_package(project_id)
    assert first == second
    assert filename.endswith(".zip")

    with zipfile.ZipFile(io.BytesIO(first)) as archive:
        assert set(archive.namelist()) == {
            "expert_review.csv",
            "finding_reviews_evidence.json",
            "package_manifest.json",
        }
        manifest = json.loads(archive.read("package_manifest.json"))
        assert manifest["review_count"] == 2
        rows = list(csv.DictReader(io.StringIO(archive.read("expert_review.csv").decode())))
        assert {row["finding_origin"] for row in rows} == {"system", "human_added"}
        human = next(row for row in rows if row["finding_origin"] == "human_added")
        assert human["recommended_action"] == "missed_by_system"


def test_browser_review_page_opens_without_uuid_or_json_entry(monkeypatch):
    project_id = f"ui-{uuid4()}"
    workspace = _install_workspace(monkeypatch, project_id)
    finding = service.list_reviewable_findings(project_id)[0]
    campaign_id = workspace["campaigns"][0]["campaign_id"]

    client = TestClient(app)
    response = client.get(
        f"/ui/projects/{project_id}/campaign-evidence/{campaign_id}/"
        f"findings/{finding.finding_id}/review"
    )

    assert response.status_code == 200
    assert "Immutable system finding" in response.text
    assert finding.snapshot_sha256 in response.text
    assert "expected_system_finding_sha256" in response.text
    assert "rationale" in response.text
