from uuid import uuid4

import pytest

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
def isolated_data_quality_idempotency_storage(tmp_path):
    settings = get_settings()
    previous_root = settings.storage_root
    settings.storage_root = str(tmp_path)
    try:
        yield tmp_path
    finally:
        settings.storage_root = previous_root


def _context():
    project_id = str(uuid4())
    with db_session() as db:
        db.add(
            Project(
                id=project_id,
                client_id=f"client-{uuid4()}",
                name=f"DQ idempotency {uuid4()}",
            )
        )
    session = create_import_session(
        CreateImportSessionRequest(project_id=project_id, name="Idempotency delivery")
    )
    source = add_source_file(
        session.id,
        "stable.csv",
        (
            "Campaign,Creative,Platform,Impressions,Clicks,Audience\n"
            "Alpha,banner-a.png,Ozon,1000,20,Adults\n"
            "Beta,banner-b.png,Yandex,900,18,Parents\n"
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
    return session, source, table, by_header


def test_data_quality_reuses_identical_inputs_and_versions_changes(
    isolated_data_quality_idempotency_storage,
):
    session, source, table, by_header = _context()
    first_normalization = normalize_source_table(session.id, source.id, table.id)

    first = generate_data_quality_report(session.id, source.id, table.id)
    repeated = generate_data_quality_report(session.id, source.id, table.id)
    assert repeated.run.id == first.run.id
    assert repeated.run.input_fingerprint == first.run.input_fingerprint

    forced = generate_data_quality_report(session.id, source.id, table.id, force=True)
    assert forced.run.id != first.run.id
    assert forced.run.run_number == first.run.run_number + 1
    assert forced.run.input_fingerprint == first.run.input_fingerprint

    decide_column_mapping(
        session.id,
        source.id,
        table.id,
        by_header["audience"].source_column_id,
        ColumnMappingDecisionRequest(status="confirmed", target_field="audience"),
    )
    second_normalization = normalize_source_table(session.id, source.id, table.id)
    assert second_normalization.run.id != first_normalization.run.id

    changed = generate_data_quality_report(session.id, source.id, table.id)
    assert changed.run.id != forced.run.id
    assert changed.run.input_fingerprint != first.run.input_fingerprint
    assert changed.run.normalization_run_id == second_normalization.run.id
