from io import BytesIO
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from openpyxl import Workbook

from src.main import app
from src.modules.import_sessions.schemas import CreateImportSessionRequest
from src.modules.import_sessions.service import add_source_file, create_import_session
from src.modules.import_sessions.tabular_service import (
    get_source_table_detail,
    inspect_source_file,
    list_source_rows,
    list_source_tables,
)
from src.modules.projects.models import Project
from src.shared.config.settings import get_settings
from src.shared.db.repository import db_session
from src.shared.errors import AppError


@pytest.fixture
def isolated_tabular_storage(tmp_path):
    settings = get_settings()
    previous = {
        "storage_root": settings.storage_root,
        "import_max_upload_size_mb": settings.import_max_upload_size_mb,
        "tabular_inspection_max_rows_per_table": settings.tabular_inspection_max_rows_per_table,
        "tabular_inspection_preview_rows": settings.tabular_inspection_preview_rows,
        "tabular_inspection_header_scan_rows": settings.tabular_inspection_header_scan_rows,
        "tabular_inspection_max_columns": settings.tabular_inspection_max_columns,
        "tabular_inspection_max_cell_chars": settings.tabular_inspection_max_cell_chars,
        "tabular_inspection_blank_row_stop": settings.tabular_inspection_blank_row_stop,
    }
    settings.storage_root = str(tmp_path)
    settings.import_max_upload_size_mb = 10
    settings.tabular_inspection_max_rows_per_table = 100
    settings.tabular_inspection_preview_rows = 20
    settings.tabular_inspection_header_scan_rows = 25
    settings.tabular_inspection_max_columns = 50
    settings.tabular_inspection_max_cell_chars = 1000
    settings.tabular_inspection_blank_row_stop = 20
    try:
        yield tmp_path
    finally:
        for key, value in previous.items():
            setattr(settings, key, value)


def _create_project_and_session():
    project_id = str(uuid4())
    project = Project(
        id=project_id,
        client_id=f"client-{uuid4()}",
        name=f"Tabular inspection {uuid4()}",
    )
    with db_session() as db:
        db.add(project)
        db.flush()
    session = create_import_session(
        CreateImportSessionRequest(
            project_id=project_id,
            name="Client source delivery",
        ),
        created_by_user_id="test-user",
    )
    return project_id, session


def _xlsx_bytes() -> bytes:
    workbook = Workbook()
    campaign = workbook.active
    campaign.title = "Campaigns"
    campaign.append(["Historical campaign export"])
    campaign.append([])
    campaign.append(["Campaign", "Impressions", "Clicks", "CTR"])
    campaign.append(["Alpha", 1000, 21, "=C4/B4"])
    campaign.append(["Beta", 500, 7, "=C5/B5"])

    empty = workbook.create_sheet("Empty")
    empty["A1"] = None

    output = BytesIO()
    workbook.save(output)
    workbook.close()
    return output.getvalue()


def test_csv_inspector_detects_header_duplicates_empty_columns_and_types(
    isolated_tabular_storage,
):
    _, session = _create_project_and_session()
    content = (
        "Campaign export;;;\n"
        "Campaign;CTR;CTR;Notes\n"
        "Alpha;1,2;1,3;\n"
        "Beta;0,9;1,0;\n"
    ).encode("utf-8")
    source = add_source_file(session.id, "history.csv", content, "text/csv")

    inspection = inspect_source_file(session.id, source.id)
    assert inspection.status == "completed"
    assert inspection.file_format == "csv"
    assert inspection.delimiter == ";"
    assert inspection.table_count == 1

    tables = list_source_tables(session.id, source.id)
    assert len(tables) == 1
    table = tables[0]
    assert table.header_row_number == 2
    assert table.source_row_count == 4
    assert table.data_row_count == 2

    detail = get_source_table_detail(
        session.id,
        source.id,
        table.id,
        preview_limit=20,
    )
    assert [column.normalized_header for column in detail.columns] == [
        "campaign",
        "ctr",
        "ctr__2",
        "notes",
    ]
    assert detail.columns[1].inferred_type == "number"
    assert detail.columns[1].duplicate_group == "ctr"
    assert detail.columns[2].duplicate_index == 2
    assert detail.columns[3].is_empty is True
    assert [row.row_kind for row in detail.preview_rows] == [
        "preamble",
        "header",
        "data",
        "data",
    ]
    warning_codes = {warning["code"] for warning in table.warnings}
    assert {"duplicate_headers", "empty_columns"} <= warning_codes


def test_xlsx_inspector_preserves_sheets_formulas_and_empty_sheet(
    isolated_tabular_storage,
):
    _, session = _create_project_and_session()
    source = add_source_file(
        session.id,
        "campaigns.xlsx",
        _xlsx_bytes(),
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

    inspection = inspect_source_file(session.id, source.id)
    assert inspection.status == "completed"
    assert inspection.table_count == 2
    assert inspection.encoding is None

    tables = list_source_tables(session.id, source.id)
    assert [table.sheet_name for table in tables] == ["Campaigns", "Empty"]

    campaign = get_source_table_detail(
        session.id,
        source.id,
        tables[0].id,
        preview_limit=20,
    )
    assert campaign.header_row_number == 3
    assert campaign.columns[3].normalized_header == "ctr"
    assert campaign.columns[3].inferred_type == "formula"
    formula_rows = [row for row in campaign.preview_rows if row.row_kind == "data"]
    assert formula_rows[0].values[3] == "=C4/B4"
    assert formula_rows[0].cell_types[3] == "formula"

    empty = get_source_table_detail(
        session.id,
        source.id,
        tables[1].id,
        preview_limit=20,
    )
    assert empty.column_count == 0
    assert empty.preview_rows == []
    assert "empty_table" in {warning["code"] for warning in empty.warnings}


def test_corrupt_xlsx_is_recorded_as_failed_without_losing_source(
    isolated_tabular_storage,
):
    _, session = _create_project_and_session()
    source = add_source_file(
        session.id,
        "broken.xlsx",
        b"this is not an xlsx archive",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

    inspection = inspect_source_file(session.id, source.id)
    assert inspection.status == "failed"
    assert inspection.error_code == "xlsx_parse_failed"
    assert inspection.table_count == 0

    same = inspect_source_file(session.id, source.id)
    assert same.id == inspection.id

    forced = inspect_source_file(session.id, source.id, force=True)
    assert forced.id != inspection.id
    assert forced.inspection_number == 2
    assert forced.status == "failed"

    with pytest.raises(AppError) as exc:
        list_source_tables(session.id, source.id)
    assert exc.value.code == "source_inspection_not_completed"


def test_row_limit_is_non_blocking_and_rows_are_paginated(
    isolated_tabular_storage,
):
    settings = get_settings()
    settings.tabular_inspection_max_rows_per_table = 4
    _, session = _create_project_and_session()
    content = b"name,clicks\nA,1\nB,2\nC,3\nD,4\nE,5\n"
    source = add_source_file(session.id, "limited.csv", content, "text/csv")

    inspection = inspect_source_file(session.id, source.id)
    assert inspection.status == "completed"
    table = list_source_tables(session.id, source.id)[0]
    assert table.truncated is True
    assert table.source_row_count == 4
    assert "row_limit_reached" in {warning["code"] for warning in table.warnings}

    first_page = list_source_rows(
        session.id,
        source.id,
        table.id,
        offset=0,
        limit=2,
    )
    second_page = list_source_rows(
        session.id,
        source.id,
        table.id,
        offset=2,
        limit=2,
    )
    assert first_page.total == 4
    assert [row.source_row_number for row in first_page.rows] == [1, 2]
    assert [row.source_row_number for row in second_page.rows] == [3, 4]


async def test_tabular_inspection_api_flow(isolated_tabular_storage):
    _, session = _create_project_and_session()
    source = add_source_file(
        session.id,
        "media.tsv",
        b"placement\timpressions\tclicks\nfeed\t500\t11\nsearch\t1000\t17\n",
        "text/tab-separated-values",
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        inspect_response = await client.post(
            f"/import-sessions/{session.id}/files/{source.id}/inspect"
        )
        assert inspect_response.status_code == 200
        body = inspect_response.json()
        assert body["status"] == "completed"
        assert body["delimiter"] == "\t"

        latest_response = await client.get(
            f"/import-sessions/{session.id}/files/{source.id}/inspection"
        )
        assert latest_response.status_code == 200
        assert latest_response.json()["id"] == body["id"]

        tables_response = await client.get(
            f"/import-sessions/{session.id}/files/{source.id}/tables"
        )
        assert tables_response.status_code == 200
        table_id = tables_response.json()[0]["id"]

        detail_response = await client.get(
            f"/import-sessions/{session.id}/files/{source.id}/tables/{table_id}",
            params={"preview_limit": 2},
        )
        assert detail_response.status_code == 200
        assert len(detail_response.json()["columns"]) == 3
        assert len(detail_response.json()["preview_rows"]) == 2

        rows_response = await client.get(
            f"/import-sessions/{session.id}/files/{source.id}/tables/{table_id}/rows",
            params={"offset": 1, "limit": 2},
        )
        assert rows_response.status_code == 200
        assert rows_response.json()["total"] == 3
        assert len(rows_response.json()["rows"]) == 2
