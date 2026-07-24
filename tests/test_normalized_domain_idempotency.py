from uuid import uuid4

import pytest

from src.modules.import_sessions.schemas import CreateImportSessionRequest
from src.modules.import_sessions.service import add_source_file, create_import_session
from src.modules.import_sessions.tabular_service import inspect_source_file, list_source_tables
from src.modules.mapping_engine.schemas import ColumnMappingDecisionRequest
from src.modules.mapping_engine.service import (
    decide_column_mapping,
    generate_mapping_suggestions,
    get_table_mapping,
)
from src.modules.normalized_data.models import NormalizedSourceRow
from src.modules.normalized_data.service import normalize_source_table
from src.modules.projects.models import Project
from src.shared.config.settings import get_settings
from src.shared.db.repository import db_session


@pytest.fixture
def isolated_normalization_idempotency_storage(tmp_path):
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
                name=f"Idempotency {uuid4()}",
            )
        )
    session = create_import_session(
        CreateImportSessionRequest(project_id=project_id, name="Idempotency delivery")
    )
    source = add_source_file(
        session.id,
        "idempotency.csv",
        b"Campaign,Impressions,Extra\nAlpha,1000,foo\nBeta,,bar\n",
        "text/csv",
    )
    assert inspect_source_file(session.id, source.id).status == "completed"
    table = list_source_tables(session.id, source.id)[0]
    mapping = generate_mapping_suggestions(session.id, source.id, table.id)
    by_header = {item.normalized_header: item for item in mapping.columns}
    for header, target in {
        "campaign": "campaign_reference",
        "impressions": "impressions",
    }.items():
        decide_column_mapping(
            session.id,
            source.id,
            table.id,
            by_header[header].source_column_id,
            ColumnMappingDecisionRequest(status="confirmed", target_field=target),
        )
    return session, source, table


def test_normalization_is_idempotent_and_mapping_changes_create_a_new_snapshot(
    isolated_normalization_idempotency_storage,
):
    session, source, table = _context()

    first = normalize_source_table(session.id, source.id, table.id)
    repeated = normalize_source_table(session.id, source.id, table.id)
    assert repeated.run.id == first.run.id
    assert repeated.run.run_number == 1

    with db_session() as db:
        assert (
            db.query(NormalizedSourceRow)
            .filter(NormalizedSourceRow.normalization_run_id == first.run.id)
            .count()
            == 2
        )

    forced = normalize_source_table(session.id, source.id, table.id, force=True)
    assert forced.run.id != first.run.id
    assert forced.run.run_number == 2
    assert forced.run.mapping_fingerprint == first.run.mapping_fingerprint

    mapping = get_table_mapping(session.id, source.id, table.id)
    extra = next(item for item in mapping.columns if item.normalized_header == "extra")
    decide_column_mapping(
        session.id,
        source.id,
        table.id,
        extra.source_column_id,
        ColumnMappingDecisionRequest(status="confirmed", target_field="product"),
    )

    changed = normalize_source_table(session.id, source.id, table.id)
    assert changed.run.id != forced.run.id
    assert changed.run.run_number == 3
    assert changed.run.mapping_fingerprint != forced.run.mapping_fingerprint
    assert any(item["target_field"] == "product" for item in changed.run.mapping_snapshot)
    assert changed.run.source_row_count == 2
    assert changed.run.failed_row_count == 0

    repeated_changed = normalize_source_table(session.id, source.id, table.id)
    assert repeated_changed.run.id == changed.run.id
