from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from src.main import app
from src.modules.import_sessions.schemas import CreateImportSessionRequest
from src.modules.import_sessions.service import add_source_file, create_import_session
from src.modules.import_sessions.tabular_service import inspect_source_file, list_source_tables
from src.modules.projects.models import Project
from src.shared.config.settings import get_settings
from src.shared.db.repository import db_session


@pytest.fixture
def isolated_mapping_api_storage(tmp_path):
    settings = get_settings()
    previous_root = settings.storage_root
    previous_limit = settings.import_max_upload_size_mb
    settings.storage_root = str(tmp_path)
    settings.import_max_upload_size_mb = 10
    try:
        yield tmp_path
    finally:
        settings.storage_root = previous_root
        settings.import_max_upload_size_mb = previous_limit


def _create_context():
    project_id = str(uuid4())
    with db_session() as db:
        db.add(
            Project(
                id=project_id,
                client_id=f"client-{uuid4()}",
                name=f"Mapping API {uuid4()}",
            )
        )
    session = create_import_session(
        CreateImportSessionRequest(project_id=project_id, name="API delivery")
    )
    source = add_source_file(
        session.id,
        "api.csv",
        b"Campaign,Impressions,Clicks\nAlpha,1000,21\n",
        "text/csv",
    )
    inspection = inspect_source_file(session.id, source.id)
    assert inspection.status == "completed"
    table = list_source_tables(session.id, source.id)[0]
    return project_id, session, source, table


async def test_mapping_engine_api_flow(isolated_mapping_api_storage):
    project_id, session, source, table = _create_context()
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        fields = await client.get("/mapping-fields")
        assert fields.status_code == 200
        assert "clicks" in {item["key"] for item in fields.json()}

        generated = await client.post(
            f"/import-sessions/{session.id}/files/{source.id}/tables/{table.id}/mapping/suggest",
            json={"force": False},
        )
        assert generated.status_code == 200
        body = generated.json()
        clicks = next(
            item for item in body["columns"] if item["normalized_header"] == "clicks"
        )
        suggestion = clicks["suggestions"][0]

        confirmed = await client.patch(
            f"/import-sessions/{session.id}/files/{source.id}/tables/{table.id}/mapping/columns/{clicks['source_column_id']}",
            json={
                "status": "confirmed",
                "selected_suggestion_id": suggestion["id"],
                "rationale": {"checked": True},
            },
        )
        assert confirmed.status_code == 200
        assert confirmed.json()["status"] == "confirmed"
        assert confirmed.json()["target_field"] == "clicks"

        profile = await client.post(
            "/mapping-profiles",
            json={
                "project_id": project_id,
                "source_table_id": table.id,
                "name": "API profile",
            },
        )
        assert profile.status_code == 201
        assert len(profile.json()["rules"]) == 1

        profiles = await client.get(
            "/mapping-profiles", params={"project_id": project_id}
        )
        assert profiles.status_code == 200
        assert any(item["name"] == "API profile" for item in profiles.json())

        loaded = await client.get(f"/mapping-profiles/{profile.json()['id']}")
        assert loaded.status_code == 200
        assert loaded.json()["rules"][0]["target_field"] == "clicks"
