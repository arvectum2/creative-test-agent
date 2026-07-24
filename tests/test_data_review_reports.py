import hashlib
import zipfile
from pathlib import Path
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from src.main import app
from src.modules.data_quality.models import DataQualityIssue, DataQualityRun
from src.modules.data_review_reports.service import (
    data_review_report_path,
    generate_data_review_report,
)
from src.modules.import_sessions.models import (
    ImportSourceFile,
    SourceColumn,
    SourceInspection,
    SourceTable,
)
from src.shared.config.settings import get_settings
from src.shared.db.repository import db_session, json_dumps
from src.shared.errors import AppError


@pytest.fixture
def isolated_report_storage(tmp_path):
    settings = get_settings()
    previous_root = settings.storage_root
    settings.storage_root = str(tmp_path)
    try:
        yield tmp_path
    finally:
        settings.storage_root = previous_root


def _context(root: Path) -> str:
    project_id = str(uuid4())
    import_session_id = str(uuid4())
    source_file_id = str(uuid4())
    inspection_id = str(uuid4())
    table_id = str(uuid4())
    quality_id = str(uuid4())
    original = root / "immutable" / "history.csv"
    original.parent.mkdir(parents=True, exist_ok=True)
    content = b"Campaign,Creative,Impressions,Clicks\nA,banner.png,1000,20\n"
    original.write_bytes(content)
    digest = hashlib.sha256(content).hexdigest()

    with db_session() as db:
        db.add(
            ImportSourceFile(
                id=source_file_id,
                import_session_id=import_session_id,
                project_id=project_id,
                original_filename="history.csv",
                extension="csv",
                declared_mime_type="text/csv",
                file_size_bytes=len(content),
                sha256=digest,
                storage_path=str(original),
            )
        )
        db.add(
            SourceInspection(
                id=inspection_id,
                source_file_id=source_file_id,
                import_session_id=import_session_id,
                project_id=project_id,
                inspection_number=1,
                status="completed",
                parser_name="test-parser",
                parser_version="1.0",
                file_format="csv",
                encoding="utf-8",
                delimiter=",",
                table_count=1,
                row_count=2,
                column_count=4,
                warnings_json=json_dumps([]),
            )
        )
        db.add(
            SourceTable(
                id=table_id,
                inspection_id=inspection_id,
                source_file_id=source_file_id,
                sheet_index=0,
                sheet_name="CSV",
                header_row_number=1,
                header_confidence=0.99,
                source_row_count=2,
                data_row_count=1,
                column_count=4,
                truncated=False,
                warnings_json=json_dumps([]),
            )
        )
        for position, header in enumerate(
            ("Campaign", "Creative", "Impressions", "Clicks"), start=1
        ):
            db.add(
                SourceColumn(
                    source_table_id=table_id,
                    position=position,
                    source_header=header,
                    normalized_header=header.casefold(),
                    inferred_type="text" if position < 3 else "integer",
                    is_empty=False,
                    non_empty_count=1,
                    sample_values_json=json_dumps(["A" if position == 1 else "banner.png" if position == 2 else 1000 if position == 3 else 20]),
                )
            )
        db.add(
            DataQualityRun(
                id=quality_id,
                source_table_id=table_id,
                source_file_id=source_file_id,
                import_session_id=import_session_id,
                project_id=project_id,
                normalization_run_id=None,
                run_number=1,
                engine_name="test",
                engine_version="1.0",
                input_fingerprint=uuid4().hex + uuid4().hex,
                status="completed",
                overall_status="review_required",
                source_file_count=1,
                source_table_count=1,
                source_row_count=1,
                source_column_count=4,
                confirmed_mapping_count=0,
                suggested_mapping_count=4,
                rejected_mapping_count=0,
                unmapped_mapping_count=0,
                normalized_row_count=0,
                partial_row_count=0,
                skipped_row_count=0,
                failed_row_count=0,
                creative_record_count=0,
                linked_creative_count=0,
                unlinked_creative_count=0,
                ambiguous_creative_count=0,
                performance_observation_count=0,
                info_issue_count=0,
                warning_issue_count=1,
                blocking_issue_count=0,
                total_issue_count=1,
                category_counts_json=json_dumps({}),
                summary_json=json_dumps({"readiness_indicators": {"file_integrity_ok": True}}),
            )
        )
        db.add(
            DataQualityIssue(
                data_quality_run_id=quality_id,
                category="mapping",
                code="mapping_confirmation_required",
                severity="warning",
                scope_type="source_table",
                scope_id=table_id,
                source_file_id=source_file_id,
                source_table_id=table_id,
                affected_count=4,
                message="Mappings need analyst confirmation.",
                remediation_hint="Confirm intended fields.",
                details_json=json_dumps({"columns": 4}),
            )
        )
    return quality_id


def test_xlsx_data_review_report_is_valid_versioned_and_verified(isolated_report_storage):
    quality_id = _context(isolated_report_storage)
    first = generate_data_review_report(quality_id)
    repeated = generate_data_review_report(quality_id)
    forced = generate_data_review_report(quality_id, force=True)

    assert repeated.id == first.id
    assert forced.id != first.id
    assert forced.input_fingerprint == first.input_fingerprint
    assert first.filename.endswith(".xlsx")
    assert first.sheet_count == 10
    path, filename = data_review_report_path(first.id)
    assert filename == first.filename
    assert path.read_bytes().startswith(b"PK")
    assert hashlib.sha256(path.read_bytes()).hexdigest() == first.sha256

    with zipfile.ZipFile(path) as archive:
        names = set(archive.namelist())
        assert "xl/workbook.xml" in names
        assert "xl/styles.xml" in names
        assert len([name for name in names if name.startswith("xl/worksheets/sheet")]) == 10
        workbook = archive.read("xl/workbook.xml").decode("utf-8")
        assert "Summary" in workbook
        assert "Data Quality Issues" in workbook
        assert "Prediction Readiness" in workbook
        summary_sheet = archive.read("xl/worksheets/sheet1.xml").decode("utf-8")
        assert "ARVECTUM — DATA REVIEW REPORT" in summary_sheet
        assert "does not fabricate CTR" in summary_sheet

    path.write_bytes(b"corrupted")
    with pytest.raises(AppError) as error:
        data_review_report_path(first.id)
    assert error.value.code == "data_review_report_corrupted"


async def test_xlsx_data_review_report_api(isolated_report_storage):
    quality_id = _context(isolated_report_storage)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        created = await client.post(
            f"/data-quality-runs/{quality_id}/data-review-report",
            json={"force": False},
        )
        assert created.status_code == 200
        report_id = created.json()["id"]
        assert created.json()["sheet_count"] == 10

        latest = await client.get(
            f"/data-quality-runs/{quality_id}/data-review-report/latest"
        )
        assert latest.status_code == 200
        assert latest.json()["id"] == report_id

        download = await client.get(f"/data-review-reports/{report_id}/download")
        assert download.status_code == 200
        assert download.headers["content-type"].startswith(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        assert download.content.startswith(b"PK")
