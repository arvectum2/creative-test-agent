import json

from fastapi import APIRouter, File, Form, Query, Request, UploadFile
from fastapi.responses import FileResponse

from src.modules.audit_log.service import write_audit_event
from src.modules.import_sessions.schemas import (
    CreateImportSessionRequest,
    ImportIntegrityReportResponse,
    ImportSessionResponse,
    ImportSourceFileResponse,
)
from src.modules.import_sessions.service import (
    add_source_file,
    complete_import_session,
    create_import_session,
    get_import_session,
    get_source_file_download,
    list_import_sessions,
    list_source_files,
    verify_import_session,
)
from src.shared.errors import AppError
from src.shared.security.auth import get_optional_user_id
from src.shared.security.hardening import safe_download_name

router = APIRouter(prefix="/import-sessions", tags=["import-sessions"])


@router.post("", response_model=ImportSessionResponse, status_code=201)
def post_create_import_session(body: CreateImportSessionRequest, request: Request):
    session = create_import_session(body, created_by_user_id=get_optional_user_id(request))
    write_audit_event(
        "import_session_created",
        "import_session",
        session.id,
        {"project_id": session.project_id, "name": session.name},
    )
    return session


@router.get("", response_model=list[ImportSessionResponse])
def get_import_sessions(
    project_id: str | None = Query(None),
    status: str | None = Query(None),
):
    return list_import_sessions(project_id=project_id, status=status)


@router.get("/{import_session_id}", response_model=ImportSessionResponse)
def get_import_session_by_id(import_session_id: str):
    session = get_import_session(import_session_id)
    if session is None:
        raise AppError("import_session_not_found", "Import session not found", 404)
    return session


@router.post(
    "/{import_session_id}/files",
    response_model=ImportSourceFileResponse,
    status_code=201,
)
async def post_import_source_file(
    import_session_id: str,
    request: Request,
    file: UploadFile = File(...),
    metadata: str | None = Form(None),
):
    content = await file.read()
    try:
        parsed_metadata = json.loads(metadata) if metadata else {}
    except json.JSONDecodeError as exc:
        raise AppError("invalid_metadata", "metadata must be a JSON object", 400) from exc
    if not isinstance(parsed_metadata, dict):
        raise AppError("invalid_metadata", "metadata must be a JSON object", 400)

    source = add_source_file(
        import_session_id=import_session_id,
        filename=file.filename or "",
        content=content,
        content_type=file.content_type,
        metadata=parsed_metadata,
        uploaded_by_user_id=get_optional_user_id(request),
    )
    write_audit_event(
        "import_source_file_stored",
        "import_source_file",
        source.id,
        {
            "import_session_id": source.import_session_id,
            "project_id": source.project_id,
            "original_filename": source.original_filename,
            "file_size_bytes": source.file_size_bytes,
            "sha256": source.sha256,
        },
    )
    return source


@router.get(
    "/{import_session_id}/files",
    response_model=list[ImportSourceFileResponse],
)
def get_import_source_files(import_session_id: str):
    return list_source_files(import_session_id)


@router.get("/{import_session_id}/files/{file_id}/download")
def download_import_source_file(import_session_id: str, file_id: str):
    path, source = get_source_file_download(import_session_id, file_id)
    return FileResponse(
        str(path),
        filename=safe_download_name(source.original_filename, "source-file.bin"),
        media_type="application/octet-stream",
        headers={
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.post("/{import_session_id}/complete", response_model=ImportSessionResponse)
def post_complete_import_session(import_session_id: str):
    session = complete_import_session(import_session_id)
    write_audit_event(
        "import_session_completed",
        "import_session",
        session.id,
        {"file_count": session.file_count, "total_bytes": session.total_bytes},
    )
    return session


@router.get(
    "/{import_session_id}/verify",
    response_model=ImportIntegrityReportResponse,
)
def get_import_integrity_report(import_session_id: str):
    report = verify_import_session(import_session_id)
    write_audit_event(
        "import_session_integrity_verified",
        "import_session",
        import_session_id,
        {
            "ok": report.ok,
            "checked_files": report.checked_files,
            "missing_files": report.missing_files,
            "corrupted_files": report.corrupted_files,
        },
    )
    return report
