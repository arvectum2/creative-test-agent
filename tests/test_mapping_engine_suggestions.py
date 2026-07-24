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
from src.modules.projects.models import Project
from src.shared.config.settings import get_settings
from src.shared.db.repository import db_session
from src.shared.errors import AppError


@pytest.fixture
def isolated_mapping_storage(tmp_path):
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
                name=f"Mapping project {uuid4()}",
            )
        )
    return project_id


def _create_table(project_id: str, filename: str, content: bytes):
    session = create_import_session(
        CreateImportSessionRequest(
            project_id=project_id,
            name=f"Source delivery {uuid4()}",
        ),
        created_by_user_id="mapping-test-user",
    )
    source = add_source_file(session.id, filename, content, "text/csv")
    inspection = inspect_source_file(session.id, source.id)
    assert inspection.status == "completed"
    table = list_source_tables(session.id, source.id)[0]
    return session, source, table


def _column_by_header(mapping, normalized_header: str):
    return next(
        column for column in mapping.columns if column.normalized_header == normalized_header
    )


def test_mapping_engine_suggests_explainable_ru_and_en_fields(isolated_mapping_storage):
    project_id = _create_project()
    session, source, table = _create_table(
        project_id,
        "history.csv",
        (
            "Название РК;Макет;Площадка;Показы;Клики;CTR %;Дата;Размер;Служебный комментарий\n"
            "Alpha;banner_300x250.png;Ozon;1000;21;2,1%;2026-06-01;300x250;ok\n"
            "Beta;banner_728x90.jpg;Yandex;500;7;1,4%;2026-06-02;728x90;check\n"
        ).encode("utf-8"),
    )

    result = generate_mapping_suggestions(session.id, source.id, table.id)
    assert result.run is not None
    assert result.run.engine_version == "1.0.0"

    expected = {
        "название_рк": "campaign_reference",
        "макет": "creative_reference",
        "площадка": "platform",
        "показы": "impressions",
        "клики": "clicks",
        "ctr": "ctr",
        "дата": "date",
        "размер": "format",
    }
    for header, target in expected.items():
        column = _column_by_header(result, header)
        assert column.status == "suggested"
        assert column.target_field == target
        assert column.suggestions[0].target_field == target
        assert column.suggestions[0].confidence >= 0.55
        explanation = column.suggestions[0].explanation
        assert "lexical_score" in explanation or "profile_match" in explanation

    unknown = _column_by_header(result, "служебный_комментарий")
    assert unknown.status == "unmapped"
    assert unknown.target_field is None

    same = generate_mapping_suggestions(session.id, source.id, table.id)
    assert same.run.id == result.run.id
    forced = generate_mapping_suggestions(session.id, source.id, table.id, force=True)
    assert forced.run.id != result.run.id
    assert forced.run.run_number == result.run.run_number + 1


def test_analyst_decisions_are_preserved_and_duplicate_targets_are_guarded(
    isolated_mapping_storage,
):
    project_id = _create_project()
    session, source, table = _create_table(
        project_id,
        "metrics.csv",
        b"Campaign,Impressions,Clicks,CTR,Notes\nAlpha,1000,21,0.021,ok\n",
    )
    mapping = generate_mapping_suggestions(session.id, source.id, table.id)

    clicks = _column_by_header(mapping, "clicks")
    confirmed = decide_column_mapping(
        session.id,
        source.id,
        table.id,
        clicks.source_column_id,
        ColumnMappingDecisionRequest(
            status="confirmed",
            selected_suggestion_id=clicks.suggestions[0].id,
            rationale={"checked": True},
        ),
        decided_by_user_id="mapping-test-user",
    )
    assert confirmed.status == "confirmed"
    assert confirmed.target_field == "clicks"
    assert confirmed.decision_source == "analyst"

    impressions = _column_by_header(mapping, "impressions")
    with pytest.raises(AppError) as exc:
        decide_column_mapping(
            session.id,
            source.id,
            table.id,
            impressions.source_column_id,
            ColumnMappingDecisionRequest(status="confirmed", target_field="clicks"),
        )
    assert exc.value.code == "mapping_target_already_confirmed"

    notes = _column_by_header(mapping, "notes")
    rejected = decide_column_mapping(
        session.id,
        source.id,
        table.id,
        notes.source_column_id,
        ColumnMappingDecisionRequest(
            status="rejected",
            rationale={"reason": "service column"},
        ),
    )
    assert rejected.status == "rejected"
    assert rejected.target_field is None

    generate_mapping_suggestions(session.id, source.id, table.id, force=True)
    refreshed = get_table_mapping(session.id, source.id, table.id)
    assert _column_by_header(refreshed, "clicks").status == "confirmed"
    assert _column_by_header(refreshed, "notes").status == "rejected"
