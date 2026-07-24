from fastapi import APIRouter, Query

from src.modules.audit_log.service import write_audit_event
from src.modules.import_sessions.schemas import (
    SourceInspectionResponse,
    SourceRowPageResponse,
    SourceTableDetailResponse,
    SourceTableSummaryResponse,
)
from src.modules.import_sessions.tabular_service import (
    get_latest_source_inspection,
    get_source_table_detail,
    inspect_source_file,
    list_source_rows,
    list_source_tables,
)
from src.shared.config.settings import get_settings
from src.shared.errors import AppError

router = APIRouter(prefix="/import-sessions", tags=["tabular-inspection"])


@router.post(
    "/{import_session_id}/files/{file_id}/inspect",
    response_model=SourceInspectionResponse,
)
def post_inspect_source_file(
    import_session_id: str,
    file_id: str,
    force: bool = Query(False),
):
    inspection = inspect_source_file(import_session_id, file_id, force=force)
    write_audit_event(
        "import_source_file_inspected",
        "source_inspection",
        inspection.id,
        {
            "import_session_id": import_session_id,
            "source_file_id": file_id,
            "status": inspection.status,
            "parser_version": inspection.parser_version,
            "table_count": inspection.table_count,
            "row_count": inspection.row_count,
            "error_code": inspection.error_code,
            "force": force,
        },
    )
    return inspection


@router.get(
    "/{import_session_id}/files/{file_id}/inspection",
    response_model=SourceInspectionResponse,
)
def get_source_file_inspection(import_session_id: str, file_id: str):
    inspection = get_latest_source_inspection(import_session_id, file_id)
    if inspection is None:
        raise AppError(
            "source_inspection_not_found",
            "The source file has not been inspected",
            404,
        )
    return inspection


@router.get(
    "/{import_session_id}/files/{file_id}/tables",
    response_model=list[SourceTableSummaryResponse],
)
def get_source_file_tables(import_session_id: str, file_id: str):
    return list_source_tables(import_session_id, file_id)


@router.get(
    "/{import_session_id}/files/{file_id}/tables/{table_id}",
    response_model=SourceTableDetailResponse,
)
def get_source_file_table(
    import_session_id: str,
    file_id: str,
    table_id: str,
    preview_limit: int | None = Query(None, ge=1, le=200),
):
    if preview_limit is None:
        preview_limit = max(
            1,
            min(get_settings().tabular_inspection_preview_rows, 200),
        )
    return get_source_table_detail(
        import_session_id,
        file_id,
        table_id,
        preview_limit=preview_limit,
    )


@router.get(
    "/{import_session_id}/files/{file_id}/tables/{table_id}/rows",
    response_model=SourceRowPageResponse,
)
def get_source_file_table_rows(
    import_session_id: str,
    file_id: str,
    table_id: str,
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
):
    return list_source_rows(
        import_session_id,
        file_id,
        table_id,
        offset=offset,
        limit=limit,
    )
