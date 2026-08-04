from __future__ import annotations

import hashlib
import json
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from src.main import app
from src.modules.data_quality.models import DataQualityRun
from src.modules.import_sessions.models import ImportSession, ImportSourceFile
from src.modules.pilot_intake.models import PilotCase, PilotCaseDecision
from src.modules.projects.models import Project
from src.shared.db.repository import db_session

FIXTURES = json.loads(
    (Path(__file__).parent / "fixtures" / "pilot_intake" / "packages.json").read_text(
        encoding="utf-8"
    )
)


def _create_project(project_id: str) -> None:
    with db_session() as db:
        db.add(
            Project(
                id=project_id,
                client_id=f"client-{project_id}",
                name=f"Synthetic pilot {project_id}",
                status="active",
            )
        )


def _seed_import(project_id: str, fixture: dict) -> tuple[str, str]:
    session_id = f"session-{fixture['name']}-{uuid4()}"
    run_id = f"dq-{fixture['name']}-{uuid4()}"
    source_file_ids: list[str] = []
    total_bytes = sum(item["size"] for item in fixture["source_files"])
    with db_session() as db:
        db.add(
            ImportSession(
                id=session_id,
                project_id=project_id,
                name=f"Synthetic {fixture['name']}",
                status="completed",
                file_count=len(fixture["source_files"]),
                total_bytes=total_bytes,
            )
        )
        for index, source in enumerate(fixture["source_files"], start=1):
            file_id = f"file-{fixture['name']}-{index}-{uuid4()}"
            source_file_ids.append(file_id)
            db.add(
                ImportSourceFile(
                    id=file_id,
                    import_session_id=session_id,
                    project_id=project_id,
                    original_filename=source["filename"],
                    extension=Path(source["filename"]).suffix.lstrip("."),
                    declared_mime_type="application/octet-stream",
                    file_size_bytes=source["size"],
                    sha256=source["sha256"],
                    storage_path=f"synthetic/{fixture['name']}/{source['filename']}",
                )
            )
        dq = fixture["dq"]
        db.add(
            DataQualityRun(
                id=run_id,
                source_table_id=f"table-{fixture['name']}-{uuid4()}",
                source_file_id=source_file_ids[0],
                import_session_id=session_id,
                project_id=project_id,
                run_number=1,
                engine_name="synthetic-pilot-dq",
                engine_version="1.0.0",
                input_fingerprint=hashlib.sha256(fixture["name"].encode()).hexdigest(),
                status="completed",
                overall_status=dq["overall_status"],
                confirmed_mapping_count=dq.get("confirmed_mapping_count", 0),
                suggested_mapping_count=dq.get("suggested_mapping_count", 0),
                rejected_mapping_count=dq.get("rejected_mapping_count", 0),
                unmapped_mapping_count=dq.get("unmapped_mapping_count", 0),
                warning_issue_count=dq["warning_issue_count"],
                blocking_issue_count=dq["blocking_issue_count"],
                total_issue_count=dq["total_issue_count"],
            )
        )
    return session_id, run_id


def _register_payload(fixture: dict, session_id: str, run_id: str) -> dict:
    return {
        "case_key": fixture["case_key"],
        "import_session_id": session_id,
        "initial_state": fixture["initial_state"],
        "source_linkage_confidence": fixture["source_linkage_confidence"],
        "asset_references": fixture["asset_references"],
        "metrics": fixture["metrics"],
        "data_quality_run_ids": [run_id],
        "provenance": {"fixture": fixture["name"], "synthetic": True},
        "decision_reason": f"synthetic_{fixture['name']}_registered",
    }


def _register(client: TestClient, project_id: str, fixture: dict) -> dict:
    session_id, run_id = _seed_import(project_id, fixture)
    response = client.post(
        f"/pilot-intake/projects/{project_id}/cases",
        json=_register_payload(fixture, session_id, run_id),
    )
    assert response.status_code == 201, response.text
    return response.json()


def _fixture(name: str) -> dict:
    return next(item for item in FIXTURES if item["name"] == name)


def test_synthetic_case_register_summary_ui_and_deterministic_export():
    project_id = f"pilot-prep-{uuid4()}"
    _create_project(project_id)
    client = TestClient(app)

    created = {item["name"]: _register(client, project_id, item) for item in FIXTURES}

    assert created["valid"]["state"] == "included"
    assert created["invalid"]["state"] == "excluded"
    assert created["rate_only"]["state"] == "deferred"
    assert created["missing_linkage"]["state"] == "needs_clarification"
    assert created["multi_asset"]["linkage_confidence"] == "probable"
    assert created["multi_asset"]["asset_count"] == 2
    assert created["rate_only"]["metrics"] == {
        "impressions": None,
        "clicks": None,
        "rate": 0.034,
    }

    summary_response = client.get(
        f"/pilot-intake/projects/{project_id}/data-quality-summary"
    )
    assert summary_response.status_code == 200
    summary = summary_response.json()
    assert summary["total_cases"] == 5
    assert summary["state_counts"] == {
        "included": 2,
        "excluded": 1,
        "deferred": 1,
        "needs_clarification": 1,
    }
    assert summary["data_quality_status_counts"] == {
        "passed": 1,
        "review_required": 3,
        "blocked": 1,
        "unavailable": 0,
    }
    assert summary["rate_only_case_count"] == 1
    assert summary["multi_asset_case_count"] == 1
    assert summary["confirmed_mapping_count"] == 5
    assert summary["suggested_mapping_count"] == 2
    assert summary["unmapped_mapping_count"] == 1
    assert summary["reported_impressions_total"] == 2700
    assert summary["reported_clicks_total"] == 105
    assert summary["non_exact_to_exact_promotion_count"] == 0
    assert summary["counts_reconstructed_from_rates"] is False

    first = client.get(f"/pilot-intake/projects/{project_id}/export.json")
    second = client.get(f"/pilot-intake/projects/{project_id}/export.json")
    assert first.status_code == 200
    assert first.content == second.content
    assert first.headers["x-pilot-intake-sha256"] == hashlib.sha256(
        first.content
    ).hexdigest()
    payload = first.json()
    assert [item["case_key"] for item in payload["cases"]] == sorted(
        item["case_key"] for item in FIXTURES
    )
    assert len(payload["decision_history"]) == 5
    assert payload["data_quality_summary"]["counts_reconstructed_from_rates"] is False

    ui = client.get(f"/ui/projects/{project_id}/pilot-intake")
    assert ui.status_code == 200
    assert "Controlled Pilot Intake" in ui.text
    assert "SYN-VALID-001" in ui.text
    assert "Missing counts stay missing" in ui.text


def test_linkage_promotion_is_rejected_and_rate_only_counts_remain_missing():
    project_id = f"pilot-guard-{uuid4()}"
    _create_project(project_id)
    client = TestClient(app)

    probable = _fixture("multi_asset")
    session_id, run_id = _seed_import(project_id, probable)
    body = _register_payload(probable, session_id, run_id)
    body["requested_linkage_confidence"] = "exact"
    rejected = client.post(
        f"/pilot-intake/projects/{project_id}/cases",
        json=body,
    )
    assert rejected.status_code == 409
    assert "cannot be promoted to exact" in rejected.text

    rate_only = _register(client, project_id, _fixture("rate_only"))
    assert rate_only["metrics"]["impressions"] is None
    assert rate_only["metrics"]["clicks"] is None
    assert rate_only["metrics"]["rate"] == 0.034

    with db_session() as db:
        row = db.query(PilotCase).filter(PilotCase.id == rate_only["id"]).one()
        assert row.reported_impressions is None
        assert row.reported_clicks is None
        assert row.reported_rate == 0.034

    summary = client.get(
        f"/pilot-intake/projects/{project_id}/data-quality-summary"
    ).json()
    assert summary["rate_only_case_count"] == 1
    assert summary["reported_impressions_total"] == 0
    assert summary["reported_clicks_total"] == 0
    assert summary["counts_reconstructed_from_rates"] is False


def test_state_decisions_are_append_only_and_provenance_is_immutable():
    project_id = f"pilot-history-{uuid4()}"
    _create_project(project_id)
    client = TestClient(app)
    created = _register(client, project_id, _fixture("valid"))

    for state, reason in (
        ("deferred", "waiting_for_second_asset"),
        ("needs_clarification", "source_linkage_question"),
    ):
        response = client.post(
            f"/pilot-intake/projects/{project_id}/cases/{created['id']}/decisions",
            json={"state": state, "reason": reason},
        )
        assert response.status_code == 201, response.text

    history = client.get(
        f"/pilot-intake/projects/{project_id}/cases/{created['id']}/history"
    )
    assert history.status_code == 200
    items = history.json()
    assert [item["sequence"] for item in items] == [1, 2, 3]
    assert [item["to_state"] for item in items] == [
        "included",
        "deferred",
        "needs_clarification",
    ]
    assert items[1]["from_state"] == "included"
    assert items[2]["from_state"] == "deferred"

    with pytest.raises(RuntimeError, match="append-only"):
        with db_session() as db:
            decision = (
                db.query(PilotCaseDecision)
                .filter(PilotCaseDecision.id == items[0]["id"])
                .one()
            )
            decision.reason = "mutated"

    with pytest.raises(RuntimeError, match="provenance is immutable"):
        with db_session() as db:
            case = db.query(PilotCase).filter(PilotCase.id == created["id"]).one()
            case.source_package_sha256 = "0" * 64

    with pytest.raises(RuntimeError, match="append-only decision"):
        with db_session() as db:
            case = db.query(PilotCase).filter(PilotCase.id == created["id"]).one()
            case.state = "excluded"

    current = client.get(
        f"/pilot-intake/projects/{project_id}/cases/{created['id']}"
    ).json()
    assert current["state"] == "needs_clarification"
    assert current["source_package_sha256"] == created["source_package_sha256"]


def test_project_scoping_rejects_cross_project_case_and_evidence_access():
    project_a = f"pilot-project-a-{uuid4()}"
    project_b = f"pilot-project-b-{uuid4()}"
    _create_project(project_a)
    _create_project(project_b)
    client = TestClient(app)

    fixture = _fixture("valid")
    session_id, run_id = _seed_import(project_a, fixture)
    response = client.post(
        f"/pilot-intake/projects/{project_a}/cases",
        json=_register_payload(fixture, session_id, run_id),
    )
    assert response.status_code == 201
    case_id = response.json()["id"]

    assert (
        client.get(f"/pilot-intake/projects/{project_b}/cases/{case_id}").status_code
        == 404
    )
    assert (
        client.get(
            f"/pilot-intake/projects/{project_b}/cases/{case_id}/history"
        ).status_code
        == 404
    )
    assert (
        client.post(
            f"/pilot-intake/projects/{project_b}/cases/{case_id}/decisions",
            json={"state": "excluded", "reason": "cross-project-attempt"},
        ).status_code
        == 404
    )

    cross_project_body = _register_payload(fixture, session_id, run_id)
    cross_project_body["case_key"] = "SYN-CROSS-PROJECT-001"
    cross_project = client.post(
        f"/pilot-intake/projects/{project_b}/cases",
        json=cross_project_body,
    )
    assert cross_project.status_code == 404
    assert client.get(f"/pilot-intake/projects/{project_b}/cases").json() == []
