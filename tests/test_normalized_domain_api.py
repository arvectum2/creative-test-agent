from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from src.main import app
from src.modules.import_sessions.schemas import CreateImportSessionRequest
from src.modules.import_sessions.service import add_source_file, create_import_session
from src.modules.import_sessions.tabular_service import inspect_source_file, list_source_tables
from src.modules.mapping_engine.schemas import ColumnMappingDecisionRequest
from src.modules.mapping_engine.service import decide_column_mapping, generate_mapping_suggestions
from src.modules.projects.models import Project
from src.shared.config.settings import get_settings
from src.shared.db.repository import db_session


@pytest.fixture
def isolated_normalized_api_storage(tmp_path):
    settings = get_settings()
    previous_root = settings.storage_root
    settings.storage_root = str(tmp_path)
    try:
        yield tmp_path
    finally:
        settings.storage_root = previous_root


def _create_context(*, confirm: bool):
    project_id = str(uuid4())
    with db_session() as db:
        db.add(
            Project(
                id=project_id,
                client_id=f"client-{uuid4()}",
                name=f"Normalized API {uuid4()}",
            )
        )
    session = create_import_session(
        CreateImportSessionRequest(project_id=project_id, name="API normalization")
    )
    source = add_source_file(
        session.id,
        "api-normalization.csv",
        b"Campaign,Clicks,Comment\nAlpha,7,keep me\n",
        "text/csv",
    )
    assert inspect_source_file(session.id, source.id).status == "completed"
    table = list_source_tables(session.id, source.id)[0]
    if confirm:
        mapping = generate_mapping_suggestions(session.id, source.id, table.id)
        by_header = {item.normalized_header: item for item in mapping.columns}
        for header, target in {
            "campaign": "campaign_reference",
            "clicks": "clicks",
        }.items():
            decide_column_mapping(
                session.id,
                source.id,
                table.id,
                by_header[header].source_column_id,
                ColumnMappingDecisionRequest(status="confirmed", target_field=target),
            )
    return session, source, table


async def test_normalized_domain_api_flow(isolated_normalized_api_storage):
    session, source, table = _create_context(confirm=True)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        normalized = await client.post(
            f"/import-sessions/{session.id}/files/{source.id}/tables/{table.id}/normalize",
            json={"force": False},
        )
        assert normalized.status_code == 200
        result = normalized.json()
        run_id = result["run"]["id"]
        assert result["run"]["campaign_count"] == 1
        assert result["run"]["performance_observation_count"] == 1

        latest = await client.get(
            f"/import-sessions/{session.id}/files/{source.id}/tables/{table.id}/normalization"
        )
        assert latest.status_code == 200
        assert latest.json()["run"]["id"] == run_id

        run = await client.get(f"/normalization-runs/{run_id}")
        assert run.status_code == 200
        assert run.json()["mapping_snapshot"]

        rows = await client.get(
            f"/normalization-runs/{run_id}/rows", params={"offset": 0, "limit": 10}
        )
        assert rows.status_code == 200
        rows_body = rows.json()
        assert rows_body["total"] == 1
        assert rows_body["rows"][0]["custom_fields"] == {"comment": "keep me"}
        assert {item["field_name"] for item in rows_body["rows"][0]["field_values"]} == {
            "campaign_reference",
            "clicks",
        }

        campaigns = await client.get(f"/normalization-runs/{run_id}/campaigns")
        observations = await client.get(
            f"/normalization-runs/{run_id}/performance-observations"
        )
        placements = await client.get(f"/normalization-runs/{run_id}/placements")
        assert campaigns.status_code == 200
        assert observations.status_code == 200
        assert placements.status_code == 200
        assert campaigns.json()[0]["reference_key"] == "Alpha"
        assert observations.json()[0]["clicks"] == 7
        assert len(placements.json()) == 1


async def test_normalization_requires_at_least_one_confirmed_mapping(
    isolated_normalized_api_storage,
):
    session, source, table = _create_context(confirm=False)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            f"/import-sessions/{session.id}/files/{source.id}/tables/{table.id}/normalize",
            json={"force": False},
        )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "normalization_requires_confirmed_mapping"
