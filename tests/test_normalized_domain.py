from uuid import uuid4

import pytest

from src.modules.creative_assets.models import CreativeAsset
from src.modules.import_sessions.schemas import CreateImportSessionRequest
from src.modules.import_sessions.service import add_source_file, create_import_session
from src.modules.import_sessions.tabular_service import inspect_source_file, list_source_tables
from src.modules.mapping_engine.schemas import ColumnMappingDecisionRequest
from src.modules.mapping_engine.service import (
    decide_column_mapping,
    generate_mapping_suggestions,
)
from src.modules.normalized_data.service import (
    list_creatives,
    list_normalized_rows,
    normalize_source_table,
)
from src.modules.projects.models import Project
from src.shared.config.settings import get_settings
from src.shared.db.repository import db_session


@pytest.fixture
def isolated_normalized_storage(tmp_path):
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


def _create_project() -> str:
    project_id = str(uuid4())
    with db_session() as db:
        db.add(
            Project(
                id=project_id,
                client_id=f"client-{uuid4()}",
                name=f"Normalization project {uuid4()}",
            )
        )
    return project_id


def _create_table(project_id: str, content: bytes):
    session = create_import_session(
        CreateImportSessionRequest(project_id=project_id, name="Historical delivery")
    )
    source = add_source_file(session.id, "history.csv", content, "text/csv")
    inspection = inspect_source_file(session.id, source.id)
    assert inspection.status == "completed"
    table = list_source_tables(session.id, source.id)[0]
    return session, source, table


def _confirm_mappings(session, source, table, expected: dict[str, str]):
    generated = generate_mapping_suggestions(session.id, source.id, table.id)
    by_header = {item.normalized_header: item for item in generated.columns}
    for header, target in expected.items():
        column = by_header[header]
        decide_column_mapping(
            session.id,
            source.id,
            table.id,
            column.source_column_id,
            ColumnMappingDecisionRequest(status="confirmed", target_field=target),
            decided_by_user_id="normalization-test-user",
        )


def test_nullable_domain_normalization_preserves_unknowns_and_field_provenance(
    isolated_normalized_storage,
):
    project_id = _create_project()
    with db_session() as db:
        asset = CreativeAsset(
            id=str(uuid4()),
            title="Primary banner",
            asset_type="image",
            original_filename="banner.png",
            project_id=project_id,
        )
        db.add(asset)
        asset_id = asset.id

    session, source, table = _create_table(
        project_id,
        (
            "Campaign,Creative,Platform,Placement,Format,Audience,Brand,Product,Date,Impressions,Clicks,CTR,Notes\n"
            "Alpha,banner.png,Ozon,search,300x250,Women,Brand X,Drug A,2026-06-01,1000,21,2.1%,private\n"
            "Alpha,banner.png,Ozon,search,300x250,Women,Brand X,Drug A,02.06.2026,bad,7,0.014,check\n"
        ).encode("utf-8"),
    )
    _confirm_mappings(
        session,
        source,
        table,
        {
            "campaign": "campaign_reference",
            "creative": "creative_reference",
            "platform": "platform",
            "placement": "placement_type",
            "format": "format",
            "audience": "audience",
            "brand": "brand",
            "product": "product",
            "date": "date",
            "impressions": "impressions",
            "clicks": "clicks",
            "ctr": "ctr",
        },
    )

    result = normalize_source_table(session.id, source.id, table.id)
    assert result.run.status == "completed"
    assert result.run.source_row_count == 2
    assert result.run.normalized_row_count == 1
    assert result.run.partial_row_count == 1
    assert result.run.campaign_count == 1
    assert result.run.creative_count == 1
    assert result.run.platform_count == 1
    assert result.run.audience_segment_count == 1
    assert result.run.placement_count == 2
    assert result.run.performance_observation_count == 2

    total, rows = list_normalized_rows(result.run.id, offset=0, limit=10)
    assert total == 2
    first, second = rows
    assert first.status == "normalized"
    assert first.custom_fields == {"notes": "private"}
    assert first.source_payload["campaign"] == "Alpha"

    field_values = {item.field_name: item for item in first.field_values}
    assert field_values["impressions"].raw_value == "1000"
    assert field_values["impressions"].normalized_value == 1000
    assert field_values["impressions"].source_file_id == source.id
    assert field_values["impressions"].source_table_id == table.id
    assert field_values["impressions"].source_row_number == first.source_row_number
    assert field_values["impressions"].normalization_version == "1.0.0"
    assert field_values["ctr"].normalized_value == pytest.approx(0.021)
    assert field_values["ctr"].transformation == "percent_text_to_ratio"

    assert second.status == "partial"
    parse_issue = next(item for item in second.issues if item["code"] == "value_parse_failed")
    assert parse_issue["context"]["target_field"] == "impressions"
    second_values = {item.field_name: item for item in second.field_values}
    assert second_values["impressions"].raw_value == "bad"
    assert second_values["impressions"].normalized_value is None

    creatives = list_creatives(result.run.id)
    assert len(creatives) == 1
    assert creatives[0].creative_asset_id == asset_id
    assert creatives[0].display_reference == "banner.png"
