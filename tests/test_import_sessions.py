import json
from hashlib import sha256
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from src.main import app
from src.modules.import_sessions.models import ImportSourceFile
from src.modules.import_sessions.schemas import CreateImportSessionRequest
from src.modules.import_sessions.service import (
    add_source_file,
    complete_import_session,
    create_import_session,
    get_import_session,
    get_source_file_model,
    verify_import_session,
)
from src.modules.import_sessions.storage import ImmutableOriginalStorage
from src.modules.projects.models import Project
from src.shared.config.settings import get_settings
from src.shared.db.repository import db_session
from src.shared.errors import AppError
from src.shared.storage.local_storage import LocalStorage


@pytest.fixture
def isolated_import_storage(tmp_path):
    settings = get_settings()
    old_root = settings.storage_root
    old_limit = settings.import_max_upload_size_mb
    settings.storage_root = str(tmp_path)
    settings.import_max_upload_size_mb = 5
    try:
        yield tmp_path
    finally:
        settings.storage_root = old_root
        settings.import_max_upload_size_mb = old_limit


def _create_project() -> Project:
    project = Project(
        id=str(uuid4()),
        client_id=f"client-{uuid4()}",
        name=f"Import project {uuid4()}",
    )
    with db_session() as db:
        db.add(project)
        db.flush()
        db.refresh(project)
        db.expunge(project)
    return project


def _create_session(project: Project, name: str = "Historical campaign data"):
    return create_import_session(
        CreateImportSessionRequest(project_id=project.id, name=name),
        created_by_user_id="test-user",
    )


def test_source_file_is_stored_verbatim_and_session_can_be_completed(
    isolated_import_storage,
):
    project = _create_project()
    session = _create_session(project)
    content = b"campaign,impressions,clicks\nalpha,1000,21\n"

    source = add_source_file(
        session.id,
        "history.csv",
        content,
        "text/csv",
        metadata={"received_from": "client"},
        uploaded_by_user_id="test-user",
    )

    assert source.sha256 == sha256(content).hexdigest()
    assert source.original_filename == "history.csv"
    assert source.metadata["received_from"] == "client"

    model = get_source_file_model(source.id)
    assert model is not None
    stored_path = ImmutableOriginalStorage().absolute_path(model.storage_path)
    assert stored_path.read_bytes() == content

    report = verify_import_session(session.id)
    assert report.ok is True
    assert report.checked_files == 1

    completed = complete_import_session(session.id)
    assert completed.status == "completed"
    assert completed.file_count == 1
    assert completed.total_bytes == len(content)

    with pytest.raises(AppError) as exc:
        add_source_file(session.id, "late.csv", b"late", "text/csv")
    assert exc.value.code == "import_session_closed"


def test_content_addressing_deduplicates_blobs_but_preserves_upload_records(
    isolated_import_storage,
):
    project = _create_project()
    first_session = _create_session(project, "First delivery")
    second_session = _create_session(project, "Second delivery")
    content = f"same-{uuid4()}".encode()

    first = add_source_file(first_session.id, "first.xlsx", content)
    second = add_source_file(second_session.id, "renamed.xlsx", content)

    assert first.id != second.id
    assert first.sha256 == second.sha256
    first_model = get_source_file_model(first.id)
    second_model = get_source_file_model(second.id)
    assert first_model is not None and second_model is not None
    assert first_model.storage_path == second_model.storage_path


def test_local_storage_never_overwrites_an_immutable_path(isolated_import_storage):
    storage = LocalStorage(root=str(isolated_import_storage))
    storage.store_immutable("immutable/item", b"original")
    storage.store_immutable("immutable/item", b"original")

    with pytest.raises(ValueError):
        storage.store_immutable("immutable/item", b"replacement")
    assert storage.absolute_path("immutable/item").read_bytes() == b"original"


def test_database_source_file_records_reject_update_and_delete(isolated_import_storage):
    project = _create_project()
    session = _create_session(project)
    source = add_source_file(session.id, "immutable.json", b'{"value": 1}')

    with pytest.raises(RuntimeError, match="immutable"):
        with db_session() as db:
            model = db.query(ImportSourceFile).filter(ImportSourceFile.id == source.id).one()
            model.original_filename = "changed.json"

    with pytest.raises(RuntimeError, match="immutable"):
        with db_session() as db:
            model = db.query(ImportSourceFile).filter(ImportSourceFile.id == source.id).one()
            db.delete(model)


def test_integrity_report_detects_external_tampering(isolated_import_storage):
    project = _create_project()
    session = _create_session(project)
    source = add_source_file(session.id, "tamper.csv", b"trusted-content")
    model = get_source_file_model(source.id)
    assert model is not None

    path = ImmutableOriginalStorage().absolute_path(model.storage_path)
    path.write_bytes(b"tampered-content")

    report = verify_import_session(session.id)
    assert report.ok is False
    assert report.corrupted_files == [source.id]


def test_unsafe_filename_and_empty_session_are_rejected(isolated_import_storage):
    project = _create_project()
    session = _create_session(project)

    with pytest.raises(AppError) as exc:
        add_source_file(session.id, "../unsafe.csv", b"data")
    assert exc.value.code == "unsafe_filename"

    with pytest.raises(AppError) as exc:
        complete_import_session(session.id)
    assert exc.value.code == "empty_import_session"


async def test_import_session_api_flow(isolated_import_storage):
    project = _create_project()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        create_response = await client.post(
            "/import-sessions",
            json={
                "project_id": project.id,
                "name": "Client source delivery",
                "metadata": {"delivery": "initial"},
            },
        )
        assert create_response.status_code == 201
        session_id = create_response.json()["id"]

        content = b"placement\timpressions\tclicks\nfeed\t500\t11\n"
        upload_response = await client.post(
            f"/import-sessions/{session_id}/files",
            files={"file": ("media.tsv", content, "text/tab-separated-values")},
            data={"metadata": json.dumps({"sheet_role": "media_history"})},
        )
        assert upload_response.status_code == 201
        uploaded = upload_response.json()
        assert uploaded["sha256"] == sha256(content).hexdigest()
        assert "storage_path" not in uploaded

        verify_response = await client.get(f"/import-sessions/{session_id}/verify")
        assert verify_response.status_code == 200
        assert verify_response.json()["ok"] is True

        complete_response = await client.post(f"/import-sessions/{session_id}/complete")
        assert complete_response.status_code == 200
        assert complete_response.json()["status"] == "completed"

        download_response = await client.get(
            f"/import-sessions/{session_id}/files/{uploaded['id']}/download"
        )
        assert download_response.status_code == 200
        assert download_response.content == content
        assert download_response.headers["x-content-type-options"] == "nosniff"

    persisted = get_import_session(session_id)
    assert persisted is not None
    assert persisted.file_count == 1
