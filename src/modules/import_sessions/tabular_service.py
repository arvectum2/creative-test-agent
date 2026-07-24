from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import func

from src.modules.import_sessions.models import (
    ImportSourceFile,
    SourceColumn,
    SourceInspection,
    SourceInspectionStatus,
    SourceRow,
    SourceTable,
)
from src.modules.import_sessions.schemas import (
    SourceColumnResponse,
    SourceInspectionResponse,
    SourceRowPageResponse,
    SourceRowResponse,
    SourceTableDetailResponse,
    SourceTableSummaryResponse,
)
from src.modules.import_sessions.service import get_source_file_download
from src.modules.import_sessions.tabular_inspector import (
    PARSER_NAME,
    PARSER_VERSION,
    TabularInspectionError,
    inspect_tabular_file,
)
from src.shared.db.repository import db_session, json_dumps, json_loads
from src.shared.errors import AppError


def inspect_source_file(
    import_session_id: str,
    file_id: str,
    *,
    force: bool = False,
) -> SourceInspectionResponse:
    path, source = get_source_file_download(import_session_id, file_id)

    if not force:
        existing = _get_latest_inspection_model(
            import_session_id,
            file_id,
            parser_version=PARSER_VERSION,
        )
        if existing is not None:
            return _inspection_response(existing)

    inspection_id = str(uuid4())
    with db_session() as db:
        max_number = (
            db.query(func.max(SourceInspection.inspection_number))
            .filter(SourceInspection.source_file_id == file_id)
            .scalar()
            or 0
        )
        model = SourceInspection(
            id=inspection_id,
            source_file_id=file_id,
            import_session_id=import_session_id,
            project_id=source.project_id,
            inspection_number=max_number + 1,
            status=SourceInspectionStatus.running,
            parser_name=PARSER_NAME,
            parser_version=PARSER_VERSION,
            file_format=(source.extension or "").lstrip(".") or None,
            warnings_json=json_dumps([]),
        )
        db.add(model)
        db.flush()

    try:
        result = inspect_tabular_file(path, source.extension)
        _persist_result(inspection_id, result)
    except TabularInspectionError as exc:
        _mark_failed(inspection_id, exc.code, exc.message)
    except Exception as exc:
        _mark_failed(
            inspection_id,
            "tabular_inspection_failed",
            f"Tabular inspection failed: {exc}",
        )

    inspection = get_inspection(inspection_id)
    if inspection is None:
        raise AppError(
            "source_inspection_not_found",
            "Source inspection could not be loaded after processing",
            500,
        )
    return inspection


def get_latest_source_inspection(
    import_session_id: str,
    file_id: str,
) -> SourceInspectionResponse | None:
    _require_source_file(import_session_id, file_id)
    model = _get_latest_inspection_model(import_session_id, file_id)
    return _inspection_response(model) if model else None


def get_inspection(inspection_id: str) -> SourceInspectionResponse | None:
    with db_session() as db:
        model = db.query(SourceInspection).filter(SourceInspection.id == inspection_id).first()
        return _inspection_response(model) if model else None


def list_source_tables(
    import_session_id: str,
    file_id: str,
) -> list[SourceTableSummaryResponse]:
    inspection = _require_completed_inspection(import_session_id, file_id)
    with db_session() as db:
        models = (
            db.query(SourceTable)
            .filter(SourceTable.inspection_id == inspection.id)
            .order_by(SourceTable.sheet_index.asc(), SourceTable.id.asc())
            .all()
        )
        return [_table_summary_response(model) for model in models]


def get_source_table_detail(
    import_session_id: str,
    file_id: str,
    table_id: str,
    *,
    preview_limit: int,
) -> SourceTableDetailResponse:
    inspection = _require_completed_inspection(import_session_id, file_id)
    with db_session() as db:
        table = (
            db.query(SourceTable)
            .filter(
                SourceTable.id == table_id,
                SourceTable.inspection_id == inspection.id,
                SourceTable.source_file_id == file_id,
            )
            .first()
        )
        if table is None:
            raise AppError("source_table_not_found", "Source table not found", 404)

        columns = (
            db.query(SourceColumn)
            .filter(SourceColumn.source_table_id == table.id)
            .order_by(SourceColumn.position.asc())
            .all()
        )
        rows = (
            db.query(SourceRow)
            .filter(SourceRow.source_table_id == table.id)
            .order_by(SourceRow.source_row_number.asc(), SourceRow.id.asc())
            .limit(preview_limit)
            .all()
        )
        summary = _table_summary_response(table)
        return SourceTableDetailResponse(
            **summary.model_dump(),
            columns=[_column_response(model) for model in columns],
            preview_rows=[_row_response(model) for model in rows],
        )


def list_source_rows(
    import_session_id: str,
    file_id: str,
    table_id: str,
    *,
    offset: int,
    limit: int,
) -> SourceRowPageResponse:
    inspection = _require_completed_inspection(import_session_id, file_id)
    with db_session() as db:
        table = (
            db.query(SourceTable)
            .filter(
                SourceTable.id == table_id,
                SourceTable.inspection_id == inspection.id,
                SourceTable.source_file_id == file_id,
            )
            .first()
        )
        if table is None:
            raise AppError("source_table_not_found", "Source table not found", 404)

        query = db.query(SourceRow).filter(SourceRow.source_table_id == table.id)
        total = query.count()
        rows = (
            query.order_by(SourceRow.source_row_number.asc(), SourceRow.id.asc())
            .offset(offset)
            .limit(limit)
            .all()
        )
        return SourceRowPageResponse(
            source_table_id=table.id,
            offset=offset,
            limit=limit,
            total=total,
            rows=[_row_response(model) for model in rows],
        )


def _persist_result(inspection_id: str, result) -> None:
    now = datetime.now(timezone.utc)
    table_count = 0
    row_count = 0
    column_count = 0

    with db_session() as db:
        inspection = (
            db.query(SourceInspection).filter(SourceInspection.id == inspection_id).first()
        )
        if inspection is None:
            raise AppError("source_inspection_not_found", "Source inspection not found", 404)

        for inspected_table in result.tables:
            table = SourceTable(
                inspection_id=inspection.id,
                source_file_id=inspection.source_file_id,
                sheet_index=inspected_table.sheet_index,
                sheet_name=inspected_table.sheet_name[:255],
                header_row_number=inspected_table.header_row_number,
                header_confidence=inspected_table.header_confidence,
                source_row_count=inspected_table.source_row_count,
                data_row_count=inspected_table.data_row_count,
                column_count=inspected_table.column_count,
                truncated=inspected_table.truncated,
                warnings_json=json_dumps(inspected_table.warnings),
            )
            db.add(table)
            db.flush()

            for inspected_column in inspected_table.columns:
                db.add(
                    SourceColumn(
                        source_table_id=table.id,
                        position=inspected_column.position,
                        source_header=inspected_column.source_header,
                        normalized_header=inspected_column.normalized_header[:255],
                        inferred_type=inspected_column.inferred_type,
                        is_empty=inspected_column.is_empty,
                        duplicate_index=inspected_column.duplicate_index,
                        duplicate_group=(
                            inspected_column.duplicate_group[:255]
                            if inspected_column.duplicate_group
                            else None
                        ),
                        non_empty_count=inspected_column.non_empty_count,
                        sample_values_json=json_dumps(inspected_column.sample_values),
                    )
                )

            row_batch: list[SourceRow] = []
            for inspected_row in inspected_table.rows:
                row_batch.append(
                    SourceRow(
                        source_table_id=table.id,
                        source_row_number=inspected_row.source_row_number,
                        row_kind=inspected_row.row_kind,
                        values_json=json_dumps(inspected_row.values) or "[]",
                        cell_types_json=json_dumps(inspected_row.cell_types) or "[]",
                    )
                )
                if len(row_batch) >= 1000:
                    db.add_all(row_batch)
                    db.flush()
                    for row_model in row_batch:
                        db.expunge(row_model)
                    row_batch = []
            if row_batch:
                db.add_all(row_batch)
                db.flush()

            table_count += 1
            row_count += inspected_table.source_row_count
            column_count += inspected_table.column_count

        inspection.status = SourceInspectionStatus.completed
        inspection.file_format = result.file_format
        inspection.encoding = result.encoding
        inspection.delimiter = result.delimiter
        inspection.table_count = table_count
        inspection.row_count = row_count
        inspection.column_count = column_count
        inspection.warnings_json = json_dumps(result.warnings)
        inspection.error_code = None
        inspection.error_message = None
        inspection.completed_at = now
        db.flush()


def _mark_failed(inspection_id: str, code: str, message: str) -> None:
    with db_session() as db:
        model = db.query(SourceInspection).filter(SourceInspection.id == inspection_id).first()
        if model is None:
            return
        model.status = SourceInspectionStatus.failed
        model.error_code = code[:100]
        model.error_message = message
        model.completed_at = datetime.now(timezone.utc)
        db.flush()


def _require_source_file(import_session_id: str, file_id: str) -> ImportSourceFile:
    with db_session() as db:
        model = (
            db.query(ImportSourceFile)
            .filter(
                ImportSourceFile.id == file_id,
                ImportSourceFile.import_session_id == import_session_id,
            )
            .first()
        )
        if model is None:
            raise AppError("import_source_file_not_found", "Import source file not found", 404)
        db.expunge(model)
        return model


def _get_latest_inspection_model(
    import_session_id: str,
    file_id: str,
    *,
    parser_version: str | None = None,
) -> SourceInspection | None:
    with db_session() as db:
        query = db.query(SourceInspection).filter(
            SourceInspection.import_session_id == import_session_id,
            SourceInspection.source_file_id == file_id,
        )
        if parser_version:
            query = query.filter(SourceInspection.parser_version == parser_version)
        model = query.order_by(
            SourceInspection.inspection_number.desc(),
            SourceInspection.created_at.desc(),
        ).first()
        if model is None:
            return None
        db.expunge(model)
        return model


def _require_completed_inspection(
    import_session_id: str,
    file_id: str,
) -> SourceInspectionResponse:
    _require_source_file(import_session_id, file_id)
    model = _get_latest_inspection_model(import_session_id, file_id)
    if model is None:
        raise AppError(
            "source_inspection_not_found",
            "The source file has not been inspected",
            404,
        )
    if model.status != SourceInspectionStatus.completed:
        raise AppError(
            "source_inspection_not_completed",
            "The latest source inspection is not completed",
            409,
        )
    return _inspection_response(model)


def _inspection_response(model: SourceInspection) -> SourceInspectionResponse:
    return SourceInspectionResponse(
        id=model.id,
        source_file_id=model.source_file_id,
        import_session_id=model.import_session_id,
        project_id=model.project_id,
        inspection_number=model.inspection_number,
        status=model.status,
        parser_name=model.parser_name,
        parser_version=model.parser_version,
        file_format=model.file_format,
        encoding=model.encoding,
        delimiter=model.delimiter,
        table_count=model.table_count,
        row_count=model.row_count,
        column_count=model.column_count,
        warnings=json_loads(model.warnings_json) or [],
        error_code=model.error_code,
        error_message=model.error_message,
        started_at=model.started_at,
        completed_at=model.completed_at,
        created_at=model.created_at,
    )


def _table_summary_response(model: SourceTable) -> SourceTableSummaryResponse:
    return SourceTableSummaryResponse(
        id=model.id,
        inspection_id=model.inspection_id,
        source_file_id=model.source_file_id,
        sheet_index=model.sheet_index,
        sheet_name=model.sheet_name,
        header_row_number=model.header_row_number,
        header_confidence=model.header_confidence,
        source_row_count=model.source_row_count,
        data_row_count=model.data_row_count,
        column_count=model.column_count,
        truncated=model.truncated,
        warnings=json_loads(model.warnings_json) or [],
    )


def _column_response(model: SourceColumn) -> SourceColumnResponse:
    return SourceColumnResponse(
        id=model.id,
        source_table_id=model.source_table_id,
        position=model.position,
        source_header=model.source_header,
        normalized_header=model.normalized_header,
        inferred_type=model.inferred_type,
        is_empty=model.is_empty,
        duplicate_index=model.duplicate_index,
        duplicate_group=model.duplicate_group,
        non_empty_count=model.non_empty_count,
        sample_values=json_loads(model.sample_values_json) or [],
    )


def _row_response(model: SourceRow) -> SourceRowResponse:
    return SourceRowResponse(
        id=model.id,
        source_table_id=model.source_table_id,
        source_row_number=model.source_row_number,
        row_kind=model.row_kind,
        values=json_loads(model.values_json) or [],
        cell_types=json_loads(model.cell_types_json) or [],
    )
