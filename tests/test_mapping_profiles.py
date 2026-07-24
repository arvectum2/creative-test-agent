from uuid import uuid4

import pytest

from src.modules.import_sessions.schemas import CreateImportSessionRequest
from src.modules.import_sessions.service import add_source_file, create_import_session
from src.modules.import_sessions.tabular_service import inspect_source_file, list_source_tables
from src.modules.mapping_engine.schemas import (
    ColumnMappingDecisionRequest,
    CreateMappingProfileRequest,
)
from src.modules.mapping_engine.service import (
    create_mapping_profile,
    decide_column_mapping,
    generate_mapping_suggestions,
)
from src.modules.projects.models import Project
from src.shared.config.settings import get_settings
from src.shared.db.repository import db_session
from src.shared.errors import AppError


@pytest.fixture
def isolated_mapping_profile_storage(tmp_path):
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
                name=f"Profile project {uuid4()}",
            )
        )
    return project_id


def _create_table(project_id: str, filename: str, content: bytes):
    session = create_import_session(
        CreateImportSessionRequest(project_id=project_id, name=f"Delivery {uuid4()}"),
        created_by_user_id="profile-test-user",
    )
    source = add_source_file(session.id, filename, content, "text/csv")
    inspection = inspect_source_file(session.id, source.id)
    assert inspection.status == "completed"
    table = list_source_tables(session.id, source.id)[0]
    return session, source, table


def _column(mapping, normalized_header: str):
    return next(item for item in mapping.columns if item.normalized_header == normalized_header)


def test_confirmed_mapping_profile_is_reused_without_auto_confirmation(
    isolated_mapping_profile_storage,
):
    project_id = _create_project()
    session, source, table = _create_table(
        project_id,
        "first.csv",
        "Название РК;Площадка;Показы;Клики\nAlpha;Ozon;1000;21\n".encode("utf-8"),
    )
    mapping = generate_mapping_suggestions(session.id, source.id, table.id)
    for header in ("название_рк", "площадка", "показы", "клики"):
        item = _column(mapping, header)
        decide_column_mapping(
            session.id,
            source.id,
            table.id,
            item.source_column_id,
            ColumnMappingDecisionRequest(
                status="confirmed",
                selected_suggestion_id=item.suggestions[0].id,
            ),
            decided_by_user_id="profile-test-user",
        )

    profile = create_mapping_profile(
        CreateMappingProfileRequest(
            project_id=project_id,
            source_table_id=table.id,
            name="Marketplace export",
            source_label="client marketplace report",
        ),
        created_by_user_id="profile-test-user",
    )
    assert profile.version == 1
    assert len(profile.rules) == 4

    second_session, second_source, second_table = _create_table(
        project_id,
        "second.csv",
        "Название РК;Площадка;Показы;Клики\nBeta;Yandex;500;7\n".encode("utf-8"),
    )
    applied = generate_mapping_suggestions(
        second_session.id,
        second_source.id,
        second_table.id,
        mapping_profile_id=profile.id,
        force=True,
    )
    assert applied.run is not None
    assert applied.run.mapping_profile_id == profile.id
    for item in applied.columns:
        assert item.status == "suggested"
        assert item.decision_source == "profile"
        assert item.mapping_profile_id == profile.id
        assert item.confidence is not None and item.confidence >= 0.99
        assert item.suggestions[0].method == "profile_exact"


def test_mapping_profile_cannot_cross_project_boundary(
    isolated_mapping_profile_storage,
):
    project_id = _create_project()
    session, source, table = _create_table(
        project_id,
        "base.csv",
        b"Campaign,Clicks\nAlpha,21\n",
    )
    mapping = generate_mapping_suggestions(session.id, source.id, table.id)
    clicks = _column(mapping, "clicks")
    decide_column_mapping(
        session.id,
        source.id,
        table.id,
        clicks.source_column_id,
        ColumnMappingDecisionRequest(
            status="confirmed",
            selected_suggestion_id=clicks.suggestions[0].id,
        ),
    )
    profile = create_mapping_profile(
        CreateMappingProfileRequest(
            project_id=project_id,
            source_table_id=table.id,
            name="Restricted profile",
        )
    )

    other_project = _create_project()
    other_session, other_source, other_table = _create_table(
        other_project,
        "other.csv",
        b"Campaign,Clicks\nOther,1\n",
    )
    with pytest.raises(AppError) as exc:
        generate_mapping_suggestions(
            other_session.id,
            other_source.id,
            other_table.id,
            mapping_profile_id=profile.id,
            force=True,
        )
    assert exc.value.code == "mapping_profile_project_mismatch"
