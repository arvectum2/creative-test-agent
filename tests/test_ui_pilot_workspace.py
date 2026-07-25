from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from src.main import app
from src.modules.clarifications.service import get_latest_clarifications
from src.modules.client_one_page_reports.service import get_latest_client_one_page_report
from src.modules.data_review_reports.service import get_latest_data_review_report
from src.modules.import_sessions.service import list_import_sessions, list_source_files
from src.modules.import_sessions.tabular_service import list_source_tables
from src.modules.mapping_engine.service import get_table_mapping
from src.shared.config.settings import get_settings


@pytest.fixture
def isolated_pilot_workspace(tmp_path):
    settings = get_settings()
    names = (
        "storage_root",
        "exports_root",
        "backup_root",
        "import_max_upload_size_mb",
        "max_upload_size_mb",
    )
    original = {name: getattr(settings, name) for name in names}
    settings.storage_root = str(tmp_path / "storage")
    settings.exports_root = str(tmp_path / "exports")
    settings.backup_root = str(tmp_path / "backups")
    settings.import_max_upload_size_mb = 10
    settings.max_upload_size_mb = 10
    for path in (settings.storage_root, settings.exports_root, settings.backup_root):
        from pathlib import Path

        Path(path).mkdir(parents=True, exist_ok=True)
    try:
        yield tmp_path
    finally:
        for name, value in original.items():
            setattr(settings, name, value)


def _assert_redirect(response, step: str) -> None:
    assert response.status_code == 303, f"{step}: {response.status_code} {response.text}"


def _project_id_from_redirect(response) -> str:
    return response.headers["location"].split("/ui/pilot-workspaces/", 1)[1].split("?", 1)[0]


def test_operator_can_complete_unified_pilot_workspace_flow(isolated_pilot_workspace):
    suffix = uuid4().hex[:8]

    with TestClient(app) as client:
        created = client.post(
            "/ui/pilot-workspaces/new",
            data={
                "new_client_name": f"Pilot Client {suffix}",
                "new_client_industry": "synthetic",
                "project_name": f"Pilot Project {suffix}",
                "project_description": "Unified browser workflow regression",
            },
            follow_redirects=False,
        )
        _assert_redirect(created, "create pilot")
        project_id = _project_id_from_redirect(created)

        creative_upload = client.post(
            f"/ui/pilot-workspaces/{project_id}/creative-assets",
            files=[
                (
                    "files",
                    ("banner_A.txt", b"Clear synthetic offer and neutral CTA", "text/plain"),
                )
            ],
            follow_redirects=False,
        )
        _assert_redirect(creative_upload, "upload creative")

        csv_bytes = (
            b"Campaign,Creative,Impressions,Clicks\n"
            b"Alpha,banner_A.txt,1000,20\n"
            b"Beta,banner_A.txt,800,12\n"
        )
        intake = client.post(
            f"/ui/pilot-workspaces/{project_id}/intake",
            data={"name": "Synthetic client delivery", "notes": "No real client data"},
            files=[("files", ("campaign_export.csv", csv_bytes, "text/csv"))],
            follow_redirects=False,
        )
        _assert_redirect(intake, "upload intake")

        sessions = list_import_sessions(project_id=project_id)
        assert len(sessions) == 1
        session = sessions[0]
        sources = list_source_files(session.id)
        assert len(sources) == 1
        source = sources[0]
        tables = list_source_tables(session.id, source.id)
        assert len(tables) == 1
        table = tables[0]

        table_url = (
            f"/ui/pilot-workspaces/{project_id}/sessions/{session.id}/files/"
            f"{source.id}/tables/{table.id}"
        )
        table_page = client.get(table_url)
        assert table_page.status_code == 200, table_page.text
        assert "Campaign" in table_page.text

        other = client.post(
            "/ui/pilot-workspaces/new",
            data={
                "new_client_name": f"Other Client {suffix}",
                "new_client_industry": "synthetic",
                "project_name": f"Other Project {suffix}",
            },
            follow_redirects=False,
        )
        _assert_redirect(other, "create second pilot")
        other_project_id = _project_id_from_redirect(other)
        cross_project_url = table_url.replace(project_id, other_project_id, 1)
        cross_project = client.get(cross_project_url)
        assert cross_project.status_code == 404
        assert cross_project.json()["detail"] == "Pilot workspace resource not found"

        suggested = client.post(f"{table_url}/mapping/suggest", follow_redirects=False)
        _assert_redirect(suggested, "suggest mappings")
        mapping = get_table_mapping(session.id, source.id, table.id)
        by_header = {column.normalized_header: column for column in mapping.columns}
        assert {"campaign", "creative", "impressions", "clicks"} <= set(by_header)
        mapping_form = {
            f"mapping_{by_header['campaign'].source_column_id}": "campaign_reference",
            f"mapping_{by_header['creative'].source_column_id}": "creative_reference",
            f"mapping_{by_header['impressions'].source_column_id}": "impressions",
            f"mapping_{by_header['clicks'].source_column_id}": "clicks",
        }
        saved = client.post(f"{table_url}/mapping", data=mapping_form, follow_redirects=False)
        _assert_redirect(saved, "save mappings")

        normalized = client.post(f"{table_url}/normalize", follow_redirects=False)
        _assert_redirect(normalized, "normalize")

        quality = client.post(f"{table_url}/data-quality", follow_redirects=False)
        _assert_redirect(quality, "data quality")
        quality_location = quality.headers["location"]
        quality_run_id = quality_location.rsplit("/", 1)[-1]

        questions = client.post(
            f"/ui/pilot-workspaces/{project_id}/data-quality/{quality_run_id}/clarifications",
            data={"audience": "client"},
            follow_redirects=False,
        )
        _assert_redirect(questions, "generate clarifications")
        question_result = get_latest_clarifications(quality_run_id, audience="client")
        assert question_result is not None
        if question_result.questions:
            first = question_result.questions[0]
            answered = client.post(
                f"/ui/pilot-workspaces/{project_id}/data-quality/{quality_run_id}/questions/{first.id}",
                data={
                    "resolution": "answered",
                    "answer": "Synthetic operator answer",
                    "note": "UI regression",
                },
                follow_redirects=False,
            )
            _assert_redirect(answered, "answer clarification")

        readiness = client.post(
            f"/ui/pilot-workspaces/{project_id}/data-quality/{quality_run_id}/readiness",
            follow_redirects=False,
        )
        _assert_redirect(readiness, "prediction readiness")

        xlsx = client.post(
            f"/ui/pilot-workspaces/{project_id}/data-quality/{quality_run_id}/reports/data-review",
            follow_redirects=False,
        )
        _assert_redirect(xlsx, "data review report")
        data_review = get_latest_data_review_report(quality_run_id)
        assert data_review is not None
        xlsx_download = client.get(f"/data-review-reports/{data_review.id}/download")
        assert xlsx_download.status_code == 200, xlsx_download.text
        assert xlsx_download.content[:2] == b"PK"

        one_page_created = client.post(
            f"/ui/pilot-workspaces/{project_id}/data-quality/{quality_run_id}/reports/one-page",
            data={"locale": "ru"},
            follow_redirects=False,
        )
        _assert_redirect(one_page_created, "one-page report")
        one_page = get_latest_client_one_page_report(quality_run_id)
        assert one_page is not None
        pptx_download = client.get(
            f"/client-one-page-reports/{one_page.id}/download?artifact=pptx"
        )
        assert pptx_download.status_code == 200, pptx_download.text
        assert pptx_download.content[:2] == b"PK"

        final_page = client.get(
            f"/ui/pilot-workspaces/{project_id}/data-quality/{quality_run_id}"
        )
        assert final_page.status_code == 200, final_page.text
        assert "Prediction Readiness" in final_page.text
        assert "Data Review XLSX" in final_page.text
