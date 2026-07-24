from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from src.main import app
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
def isolated_data_quality_api_storage(tmp_path):
    settings = get_settings()
    previous_root = settings.storage_root
    settings.storage_root = str(tmp_path)
    try:
        yield tmp_path
    finally:
        settings.storage_root = previous_root


def _create_context():
    project_id = str(uuid4())
    with db_session() as db:
        db.add(
            Project(
                id=project_id,
                client_id=f"client-{uuid4()}",
                name=f"DQ API {uuid4()}",
            )
        )
    session = create_import_session(
        CreateImportSessionRequest(project_id=project_id, name="API quality delivery")
    )
    source = add_source_file(
        session.id,
        "api-history.csv",
        (
            "Campaign,Creative,Platform,Impressions,Clicks\n"
            "Alpha,banner.png,Ozon,1000,21\n"
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
    }.items():
        decide_column_mapping(
            session.id,
            source.id,
            table.id,
            by_header[header].source_column_id,
            ColumnMappingDecisionRequest(status="confirmed", target_field=target),
        )
    normalize_source_table(session.id, source.id, table.id)
    return session, source, table


async def test_data_quality_api_flow(isolated_data_quality_api_storage):
    session, source, table = _create_context()
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        created = await client.post(
            f"/import-sessions/{session.id}/files/{source.id}/tables/{table.id}/data-quality",
            json={"force": False},
        )
        assert created.status_code == 200
        body = created.json()
        run_id = body["run"]["id"]
        assert body["run"]["source_table_id"] == table.id
        assert body["run"]["total_issue_count"] == len(body["issues"])
        assert body["run"]["summary"]["assessment_scope"] == "preliminary_data_quality"

        latest = await client.get(
            f"/import-sessions/{session.id}/files/{source.id}/tables/{table.id}/data-quality"
        )
        assert latest.status_code == 200
        assert latest.json()["run"]["id"] == run_id

        loaded = await client.get(f"/data-quality-runs/{run_id}")
        assert loaded.status_code == 200
        assert loaded.json()["run"]["id"] == run_id

        warnings = await client.get(
            f"/data-quality-runs/{run_id}/issues",
            params={"severity": "warning", "offset": 0, "limit": 10},
        )
        assert warnings.status_code == 200
        assert warnings.json()["data_quality_run_id"] == run_id
        assert all(item["severity"] == "warning" for item in warnings.json()["issues"])

        creative_issues = await client.get(
            f"/data-quality-runs/{run_id}/issues",
            params={"category": "creative_linking"},
        )
        assert creative_issues.status_code == 200
        assert any(
            item["code"] == "creative_assets_unlinked"
            for item in creative_issues.json()["issues"]
        )

        invalid = await client.get(
            f"/data-quality-runs/{run_id}/issues",
            params={"category": "not-a-category"},
        )
        assert invalid.status_code == 400
