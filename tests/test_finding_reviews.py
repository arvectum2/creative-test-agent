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
from src.modules.finding_reviews import service
from src.modules.finding_reviews import service_core, service_commands
from src.modules.finding_reviews.models import FindingAdjudication, FindingReview
from src.modules.finding_reviews.schemas import (
    CreateFindingAdjudicationRequest,
    CreateFindingReviewRequest,
    CreateHumanFindingRequest,
)
from src.shared.db.repository import db_session
from src.shared.errors import AppError

REVIEWER_A = {
    "user_id": "reviewer-a",
    "role": "analyst",
    "display_name": "Synthetic Reviewer A",
    "is_active": True,
}
REVIEWER_B = {
    "user_id": "reviewer-b",
    "role": "analyst",
    "display_name": "Synthetic Reviewer B",
    "is_active": True,
}
ADJUDICATOR = {
    "user_id": "adjudicator-1",
    "role": "manager",
    "display_name": "Synthetic Adjudicator",
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

    monkeypatch.setattr(service_core, "_workspace_dict", loader)
    monkeypatch.setattr(service_commands, "_workspace_dict", loader)
    return workspace


def _review_body(
    snapshot_sha256: str,
    *,
    decision: str = "supported",
    correctness: int = 5,
    relevance: int = 4,
    actionability: int = 4,
    traceability: int = 5,
    severity_correctness: str = "correct",
):
    return CreateFindingReviewRequest(
        expected_system_finding_sha256=snapshot_sha256,
        reviewer_role="senior strategist",
        decision=decision,
        correctness=correctness,
        relevance=relevance,
        actionability=actionability,
        traceability=traceability,
        severity_correctness=severity_correctness,
        reviewer_confidence=0.9,
        rationale="Synthetic acceptance review.",
        comment="No client data.",
    )


def _adjudication_body(basis_fingerprint: str, *, decision: str = "partially_supported"):
    return CreateFindingAdjudicationRequest(
        expected_basis_fingerprint_sha256=basis_fingerprint,
        adjudicator_role="methodology owner",
        decision=decision,
        correctness=4,
        relevance=4,
        actionability=4,
        traceability=4,
        severity_correctness="correct",
        adjudicator_confidence=0.85,
        rationale="The adjudicator resolved the synthetic disagreement from the immutable basis reviews.",
        comment="Synthetic only.",
    )


def _make_disagreement(monkeypatch, project_id: str):
    _install_workspace(monkeypatch, project_id)
    finding = service.list_reviewable_findings(project_id)[0]
    first = service.create_system_review(
        project_id,
        finding.finding_id,
        _review_body(finding.snapshot_sha256, decision="supported", correctness=5),
        user=REVIEWER_A,
    )
    second = service.create_system_review(
        project_id,
        finding.finding_id,
        _review_body(
            finding.snapshot_sha256,
            decision="unsupported",
            correctness=1,
            relevance=2,
            actionability=2,
            traceability=2,
            severity_correctness="overstated",
        ),
        user=REVIEWER_B,
    )
    return finding, first, second


def test_independent_reviewer_streams_are_append_only(monkeypatch):
    project_id = f"review-{uuid4()}"
    _install_workspace(monkeypatch, project_id)
    finding = service.list_reviewable_findings(project_id)[0]

    first_a = service.create_system_review(
        project_id,
        finding.finding_id,
        _review_body(finding.snapshot_sha256),
        user=REVIEWER_A,
    )
    first_b = service.create_system_review(
        project_id,
        finding.finding_id,
        _review_body(finding.snapshot_sha256, decision="needs_rewording"),
        user=REVIEWER_B,
    )
    second_a = service.create_system_review(
        project_id,
        finding.finding_id,
        _review_body(finding.snapshot_sha256, decision="partially_supported"),
        user=REVIEWER_A,
    )

    assert (first_a.revision_number, first_b.revision_number, second_a.revision_number) == (1, 2, 3)
    assert first_a.reviewer_revision_number == 1
    assert first_b.reviewer_revision_number == 1
    assert second_a.reviewer_revision_number == 2
    assert second_a.supersedes_review_id == first_a.id
    assert first_b.supersedes_review_id is None
    assert first_a.reviewer_subject_id == "user:reviewer-a"
    assert first_b.reviewer_subject_id == "user:reviewer-b"
    assert first_a.system_finding_snapshot == first_b.system_finding_snapshot

    detail = service.get_reviewable_finding(project_id, finding.finding_id)
    assert detail.review_count == 3
    assert detail.reviewer_count == 2
    assert {item.reviewer_subject_id for item in detail.latest_reviews} == {
        "user:reviewer-a",
        "user:reviewer-b",
    }

    with pytest.raises(RuntimeError, match="append-only"):
        with db_session() as db:
            row = db.query(FindingReview).filter(FindingReview.id == first_a.id).one()
            row.rationale = "Forbidden mutation"


def test_stale_system_snapshot_is_rejected(monkeypatch):
    project_id = f"stale-{uuid4()}"
    _install_workspace(monkeypatch, project_id)
    finding = service.list_reviewable_findings(project_id)[0]

    with pytest.raises(AppError) as exc_info:
        service.create_system_review(
            project_id,
            finding.finding_id,
            _review_body("0" * 64),
            user=REVIEWER_A,
        )

    assert exc_info.value.code == "finding_snapshot_changed"
    assert exc_info.value.status_code == 409
    assert service.list_project_reviews(project_id) == []


def test_disagreement_is_computed_from_latest_independent_reviews(monkeypatch):
    project_id = f"disagreement-{uuid4()}"
    finding, first, second = _make_disagreement(monkeypatch, project_id)

    state = service.get_finding_disagreement(project_id, finding.finding_id)
    assert state.status == "disagreement"
    assert state.reviewer_count == 2
    assert state.basis_review_ids == [first.id, second.id]
    assert state.basis_fingerprint_sha256
    assert "decision_mismatch" in state.disagreement_reasons
    assert state.dimension_spreads["correctness"] == 4
    assert "severity_correctness_mismatch" in state.disagreement_reasons


def test_adjudication_is_append_only_and_bound_to_current_basis(monkeypatch):
    project_id = f"adjudication-{uuid4()}"
    finding, first, second = _make_disagreement(monkeypatch, project_id)
    state = service.get_finding_disagreement(project_id, finding.finding_id)

    adjudication = service.create_finding_adjudication(
        project_id,
        finding.finding_id,
        _adjudication_body(state.basis_fingerprint_sha256),
        user=ADJUDICATOR,
    )

    assert adjudication.adjudication_round == 1
    assert adjudication.basis_review_ids == [first.id, second.id]
    assert adjudication.policy_id == service.ADJUDICATION_POLICY_ID
    assert adjudication.adjudicator_subject_id == "user:adjudicator-1"
    after = service.get_finding_disagreement(project_id, finding.finding_id)
    assert after.status == "adjudicated"
    assert after.adjudication_current is True
    assert after.latest_adjudication.id == adjudication.id

    with pytest.raises(RuntimeError, match="append-only"):
        with db_session() as db:
            row = db.query(FindingAdjudication).filter(FindingAdjudication.id == adjudication.id).one()
            row.rationale = "Forbidden mutation"


def test_adjudication_requires_manager_or_admin(monkeypatch):
    project_id = f"adjudicator-role-{uuid4()}"
    finding, _, _ = _make_disagreement(monkeypatch, project_id)
    state = service.get_finding_disagreement(project_id, finding.finding_id)
    unauthorized = {
        "user_id": "adjudicator-analyst",
        "role": "analyst",
        "display_name": "Unauthorized Adjudicator",
        "is_active": True,
    }

    with pytest.raises(AppError) as exc_info:
        service.create_finding_adjudication(
            project_id,
            finding.finding_id,
            _adjudication_body(state.basis_fingerprint_sha256),
            user=unauthorized,
        )

    assert exc_info.value.code == "adjudicator_permission_denied"
    assert exc_info.value.status_code == 403


def test_adjudicator_must_be_distinct_from_basis_reviewers(monkeypatch):
    project_id = f"independent-{uuid4()}"
    finding, _, _ = _make_disagreement(monkeypatch, project_id)
    state = service.get_finding_disagreement(project_id, finding.finding_id)

    reviewer_as_manager = dict(REVIEWER_A, role="manager")
    with pytest.raises(AppError) as exc_info:
        service.create_finding_adjudication(
            project_id,
            finding.finding_id,
            _adjudication_body(state.basis_fingerprint_sha256),
            user=reviewer_as_manager,
        )

    assert exc_info.value.code == "adjudicator_not_independent"


def test_new_review_makes_prior_adjudication_stale_and_old_basis_is_rejected(monkeypatch):
    project_id = f"stale-adj-{uuid4()}"
    finding, _, _ = _make_disagreement(monkeypatch, project_id)
    initial = service.get_finding_disagreement(project_id, finding.finding_id)
    service.create_finding_adjudication(
        project_id,
        finding.finding_id,
        _adjudication_body(initial.basis_fingerprint_sha256),
        user=ADJUDICATOR,
    )

    service.create_system_review(
        project_id,
        finding.finding_id,
        _review_body(finding.snapshot_sha256, decision="partially_supported", correctness=3),
        user=REVIEWER_A,
    )
    changed = service.get_finding_disagreement(project_id, finding.finding_id)
    assert changed.status == "stale_adjudication"
    assert changed.adjudication_current is False
    assert changed.basis_fingerprint_sha256 != initial.basis_fingerprint_sha256

    with pytest.raises(AppError) as exc_info:
        service.create_finding_adjudication(
            project_id,
            finding.finding_id,
            _adjudication_body(initial.basis_fingerprint_sha256),
            user=ADJUDICATOR,
        )
    assert exc_info.value.code == "adjudication_basis_changed"


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
        user=REVIEWER_A,
    )

    assert review.source_kind == "human"
    assert review.decision == "missed_by_system"
    assert review.system_finding_snapshot is None
    assert review.system_finding_snapshot_sha256 is None
    assert review.human_finding_snapshot["system_finding_fabricated"] is False
    assert review.human_finding_snapshot_sha256
    assert review.reviewer_subject_id == "user:reviewer-a"


def test_project_scope_does_not_leak_reviews_or_adjudications(monkeypatch):
    project_id = f"scope-{uuid4()}"
    finding, _, _ = _make_disagreement(monkeypatch, project_id)
    state = service.get_finding_disagreement(project_id, finding.finding_id)
    service.create_finding_adjudication(
        project_id,
        finding.finding_id,
        _adjudication_body(state.basis_fingerprint_sha256),
        user=ADJUDICATOR,
    )

    other_project = f"other-{uuid4()}"
    with pytest.raises(AppError) as exc_info:
        service.list_project_reviews(other_project)
    assert exc_info.value.code == "project_not_found"
    with pytest.raises(AppError):
        service.list_project_adjudications(other_project)


def test_evidence_and_calibration_exports_include_adjudication_and_are_deterministic(monkeypatch):
    project_id = f"export-{uuid4()}"
    finding, _, _ = _make_disagreement(monkeypatch, project_id)
    state = service.get_finding_disagreement(project_id, finding.finding_id)
    service.create_finding_adjudication(
        project_id,
        finding.finding_id,
        _adjudication_body(state.basis_fingerprint_sha256),
        user=ADJUDICATOR,
    )

    evidence = service.export_review_evidence(project_id).model_dump(mode="json")
    assert evidence["review_count"] == 2
    assert evidence["adjudication_count"] == 1
    assert evidence["disagreements"][0]["status"] == "adjudicated"
    assert evidence["claim_boundary"]["independent_reviews_mutated"] is False

    first, filename = service.build_calibration_package(project_id)
    second, _ = service.build_calibration_package(project_id)
    assert first == second
    assert filename.endswith(".zip")

    with zipfile.ZipFile(io.BytesIO(first)) as archive:
        assert set(archive.namelist()) == {
            "adjudications.csv",
            "expert_review.csv",
            "finding_reviews_evidence.json",
            "package_manifest.json",
        }
        manifest = json.loads(archive.read("package_manifest.json"))
        assert manifest["review_count"] == 2
        assert manifest["adjudication_count"] == 1
        review_rows = list(csv.DictReader(io.StringIO(archive.read("expert_review.csv").decode())))
        assert {row["reviewer_id"] for row in review_rows} == {
            "user:reviewer-a",
            "user:reviewer-b",
        }
        adjudication_rows = list(
            csv.DictReader(io.StringIO(archive.read("adjudications.csv").decode()))
        )
        assert adjudication_rows[0]["adjudicator_id"] == "user:adjudicator-1"


def test_report_payload_blocks_unresolved_disagreement_and_uses_current_adjudication(monkeypatch):
    project_id = f"report-{uuid4()}"
    finding, _, _ = _make_disagreement(monkeypatch, project_id)

    pending, _ = service.report_review_payload(project_id)
    item = next(row for row in pending if row["finding_id"] == finding.finding_id)
    assert item["verdict"] == "not_reviewed"
    assert item["review_status"] == "pending_adjudication"

    state = service.get_finding_disagreement(project_id, finding.finding_id)
    adjudication = service.create_finding_adjudication(
        project_id,
        finding.finding_id,
        _adjudication_body(state.basis_fingerprint_sha256, decision="partially_supported"),
        user=ADJUDICATOR,
    )
    resolved, _ = service.report_review_payload(project_id)
    item = next(row for row in resolved if row["finding_id"] == finding.finding_id)
    assert item["verdict"] == "partially_supported"
    assert item["review_status"] == "adjudicated"
    assert item["adjudication_id"] == adjudication.id


def test_report_blocks_single_review_until_second_independent_reviewer(monkeypatch):
    project_id = f"single-{uuid4()}"
    _install_workspace(monkeypatch, project_id)
    finding = service.list_reviewable_findings(project_id)[0]
    service.create_system_review(
        project_id,
        finding.finding_id,
        _review_body(finding.snapshot_sha256, decision="supported"),
        user=REVIEWER_A,
    )

    state = service.get_finding_disagreement(project_id, finding.finding_id)
    assert state.status == "insufficient_reviews"

    payload, _ = service.report_review_payload(project_id)
    item = next(row for row in payload if row["finding_id"] == finding.finding_id)
    assert item["review_status"] == "single_review"


def test_browser_review_and_adjudication_pages_open_without_uuid_or_json_entry(monkeypatch):
    project_id = f"ui-{uuid4()}"
    finding, _, _ = _make_disagreement(monkeypatch, project_id)
    workspace = _workspace(project_id)
    campaign_id = workspace["campaigns"][0]["campaign_id"]

    client = TestClient(app)
    review_response = client.get(
        f"/ui/projects/{project_id}/campaign-evidence/{campaign_id}/"
        f"findings/{finding.finding_id}/review"
    )
    assert review_response.status_code == 200
    assert "Immutable system finding" in review_response.text
    assert "Expert ID" in review_response.text
    assert "Independent-review state" in review_response.text

    state = service.get_finding_disagreement(project_id, finding.finding_id)
    adjudication_response = client.get(
        f"/ui/projects/{project_id}/campaign-evidence/{campaign_id}/"
        f"findings/{finding.finding_id}/adjudicate"
    )
    assert adjudication_response.status_code == 200
    assert "Independent review adjudication" in adjudication_response.text
    assert state.basis_fingerprint_sha256 in adjudication_response.text
    assert "Synthetic Reviewer A" in adjudication_response.text
    assert "Synthetic Reviewer B" in adjudication_response.text
