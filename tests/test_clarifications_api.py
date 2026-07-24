from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from src.main import app
from src.modules.data_quality.service import generate_data_quality_report
from src.modules.import_sessions.schemas import CreateImportSessionRequest
from src.modules.import_sessions.service import add_source_file, create_import_session
from src.modules.import_sessions.tabular_service import inspect_source_file, list_source_tables
from src.modules.mapping_engine.schemas import ColumnMappingDecisionRequest
from src.modules.mapping_engine.service import decide_column_mapping, generate_mapping_suggestions
from src.modules.normalized_data.service import normalize_source_table
from src.modules.projects.models import Project
from src.shared.config.settings import get_settings
from src.shared.db.repository import db_session


@pytest.fixture
def isolated_clarification_api_storage(tmp_path):
    settings = get_settings()
    previous_root = settings.storage_root
    settings.storage_root = str(tmp_path)
    try:
        yield tmp_path
    finally:
        settings.storage_root = previous_root


def _quality_run_id() -> str:
    project_id = str(uuid4())
    with db_session() as db:
        db.add(
            Project(
                id=project_id,
                client_id=f"client-{uuid4()}",
                name=f"Clarification API {uuid4()}",
            )
        )
    session = create_import_session(
        CreateImportSessionRequest(project_id=project_id, name="API clarification delivery")
    )
    source = add_source_file(
        session.id,
        "api-history.csv",
        (
            "Campaign,Creative,Platform,Impressions,Clicks,CTR\n"
            "Alpha,missing.png,Ozon,0,2,2%\n"
            "Alpha,missing.png,Ozon,0,2,2%\n"
        ).encode("utf-8"),
        "text/csv",
    )
    inspection = inspect_source_file(session.id, source.id)
    assert inspection.status == "completed"
    table = list_source_tables(session.id, source.id)[0]
    mapping = generate_mapping_suggestions(session.id, source.id, table.id)
    by_header = {item.normalized_header: item for item in mapping.columns}
    for header, target in {
        "campaign": "campaign_reference",
        "creative": "creative_reference",
        "platform": "platform",
        "impressions": "impressions",
        "clicks": "clicks",
        "ctr": "ctr",
    }.items():
        decide_column_mapping(
            session.id,
            source.id,
            table.id,
            by_header[header].source_column_id,
            ColumnMappingDecisionRequest(status="confirmed", target_field=target),
        )
    normalize_source_table(session.id, source.id, table.id)
    quality = generate_data_quality_report(session.id, source.id, table.id)
    return quality.run.id


async def test_clarification_api_generation_response_and_history(
    isolated_clarification_api_storage,
):
    quality_run_id = _quality_run_id()
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        created = await client.post(
            f"/data-quality-runs/{quality_run_id}/clarifications",
            json={"audience": "client", "max_questions": 3, "force": False},
        )
        assert created.status_code == 200
        body = created.json()
        run_id = body["run"]["id"]
        assert 1 <= body["run"]["question_count"] <= 3
        assert body["run"]["audience"] == "client"
        question = body["questions"][0]
        assert question["evidence"]["data_quality_run_id"] == quality_run_id

        latest = await client.get(
            f"/data-quality-runs/{quality_run_id}/clarifications/latest",
            params={"audience": "client"},
        )
        assert latest.status_code == 200
        assert latest.json()["run"]["id"] == run_id

        open_questions = await client.get(
            f"/clarification-runs/{run_id}/questions",
            params={"status": "open", "offset": 0, "limit": 10},
        )
        assert open_questions.status_code == 200
        assert open_questions.json()["total"] == body["run"]["question_count"]

        invalid_answer = await client.post(
            f"/clarification-questions/{question['id']}/responses",
            json={"resolution": "answered", "answer": "not-an-option"},
        )
        assert invalid_answer.status_code == 400

        answer = question["options"][0]["value"]
        submitted = await client.post(
            f"/clarification-questions/{question['id']}/responses",
            json={
                "resolution": "answered",
                "answer": answer,
                "note": "Confirmed through the client data owner.",
            },
        )
        assert submitted.status_code == 200
        submitted_body = submitted.json()
        assert submitted_body["status"] == "answered"
        assert submitted_body["latest_response"]["response_number"] == 1
        assert submitted_body["latest_response"]["answer"] == answer

        history = await client.get(
            f"/clarification-questions/{question['id']}/responses"
        )
        assert history.status_code == 200
        assert history.json()["total"] == 1
        assert history.json()["responses"][0]["resolution"] == "answered"

        loaded_run = await client.get(f"/clarification-runs/{run_id}")
        assert loaded_run.status_code == 200
        assert loaded_run.json()["run"]["answered_question_count"] == 1
        assert loaded_run.json()["run"]["open_question_count"] == (
            body["run"]["question_count"] - 1
        )

        invalid_status = await client.get(
            f"/clarification-runs/{run_id}/questions",
            params={"status": "invalid"},
        )
        assert invalid_status.status_code == 400

        invalid_limit = await client.post(
            f"/data-quality-runs/{quality_run_id}/clarifications",
            json={"audience": "client", "max_questions": 2},
        )
        assert invalid_limit.status_code == 422
