from datetime import datetime, timezone
from pathlib import Path

from src.modules.import_sessions.models import ImportSession, ImportSessionStatus, ImportSourceFile
from src.modules.import_sessions.schemas import (
    CreateImportSessionRequest,
    ImportFileIntegrityResponse,
    ImportIntegrityReportResponse,
    ImportSessionResponse,
    ImportSourceFileResponse,
)
from src.modules.import_sessions.storage import ImmutableOriginalStorage
from src.modules.projects.models import Project
from src.shared.config.settings import get_settings
from src.shared.db.repository import db_session, json_dumps, json_loads
from src.shared.errors import AppError


def _session_response(model: ImportSession) -> ImportSessionResponse:
    return ImportSessionResponse(
        id=model.id,
        project_id=model.project_id,
        name=model.name,
        notes=model.notes,
        status=model.status,
        created_by_user_id=model.created_by_user_id,
        metadata=json_loads(model.metadata_json),
        file_count=model.file_count,
        total_bytes=model.total_bytes,
        created_at=model.created_at,
        completed_at=model.completed_at,
        updated_at=model.updated_at,
    )


def _file_response(model: ImportSourceFile) -> ImportSourceFileResponse:
    return ImportSourceFileResponse(
        id=model.id,
        import_session_id=model.import_session_id,
        project_id=model.project_id,
        original_filename=model.original_filename,
        extension=model.extension,
        declared_mime_type=model.declared_mime_type,
        file_size_bytes=model.file_size_bytes,
        sha256=model.sha256,
        uploaded_by_user_id=model.uploaded_by_user_id,
        metadata=json_loads(model.metadata_json),
        created_at=model.created_at,
    )


def create_import_session(
    req: CreateImportSessionRequest,
    created_by_user_id: str | None = None,
) -> ImportSessionResponse:
    with db_session() as db:
        project = db.query(Project).filter(Project.id == req.project_id).first()
        if project is None:
            raise AppError("project_not_found", "Project not found", 404)

        clean_name = req.name.strip()
        if not clean_name:
            raise AppError("invalid_import_session_name", "Import session name is required", 400)

        model = ImportSession(
            project_id=req.project_id,
            name=clean_name,
            notes=req.notes,
            status=ImportSessionStatus.open,
            created_by_user_id=created_by_user_id,
            metadata_json=json_dumps(req.metadata),
            file_count=0,
            total_bytes=0,
        )
        db.add(model)
        db.flush()
        db.refresh(model)
        return _session_response(model)


def list_import_sessions(
    project_id: str | None = None,
    status: str | None = None,
) -> list[ImportSessionResponse]:
    with db_session() as db:
        query = db.query(ImportSession)
        if project_id:
            query = query.filter(ImportSession.project_id == project_id)
        if status:
            query = query.filter(ImportSession.status == status)
        models = query.order_by(ImportSession.created_at.desc()).all()
        return [_session_response(model) for model in models]


def get_import_session(import_session_id: str) -> ImportSessionResponse | None:
    with db_session() as db:
        model = db.query(ImportSession).filter(ImportSession.id == import_session_id).first()
        return _session_response(model) if model else None


def add_source_file(
    import_session_id: str,
    filename: str,
    content: bytes,
    content_type: str | None = None,
    metadata: dict | None = None,
    uploaded_by_user_id: str | None = None,
    storage: ImmutableOriginalStorage | None = None,
) -> ImportSourceFileResponse:
    clean_filename = _validate_source_file(filename, content)
    immutable_storage = storage or ImmutableOriginalStorage()

    extension = Path(clean_filename).suffix.lower() or None
    if extension and len(extension) > 32:
        extension = extension[:32]
    declared_mime_type = (content_type or "").strip()[:255] or None

    with db_session() as db:
        session = (
            db.query(ImportSession)
            .filter(ImportSession.id == import_session_id)
            .first()
        )
        if session is None:
            raise AppError("import_session_not_found", "Import session not found", 404)
        if session.status != ImportSessionStatus.open:
            raise AppError(
                "import_session_closed",
                "Completed import sessions cannot accept additional files",
                409,
            )

        stored = immutable_storage.store(content)
        source = ImportSourceFile(
            import_session_id=session.id,
            project_id=session.project_id,
            original_filename=clean_filename,
            extension=extension,
            declared_mime_type=declared_mime_type,
            file_size_bytes=len(content),
            sha256=stored.sha256,
            storage_path=stored.storage_path,
            uploaded_by_user_id=uploaded_by_user_id,
            metadata_json=json_dumps(metadata or {}),
        )
        db.add(source)
        session.file_count += 1
        session.total_bytes += len(content)
        session.updated_at = datetime.now(timezone.utc)
        db.flush()
        db.refresh(source)
        return _file_response(source)


def list_source_files(import_session_id: str) -> list[ImportSourceFileResponse]:
    with db_session() as db:
        session_exists = (
            db.query(ImportSession.id)
            .filter(ImportSession.id == import_session_id)
            .first()
        )
        if session_exists is None:
            raise AppError("import_session_not_found", "Import session not found", 404)
        models = (
            db.query(ImportSourceFile)
            .filter(ImportSourceFile.import_session_id == import_session_id)
            .order_by(ImportSourceFile.created_at.asc(), ImportSourceFile.id.asc())
            .all()
        )
        return [_file_response(model) for model in models]


def complete_import_session(import_session_id: str) -> ImportSessionResponse:
    with db_session() as db:
        model = db.query(ImportSession).filter(ImportSession.id == import_session_id).first()
        if model is None:
            raise AppError("import_session_not_found", "Import session not found", 404)
        if model.status == ImportSessionStatus.completed:
            return _session_response(model)
        if model.file_count < 1:
            raise AppError(
                "empty_import_session",
                "An import session must contain at least one source file before completion",
                409,
            )
        now = datetime.now(timezone.utc)
        model.status = ImportSessionStatus.completed
        model.completed_at = now
        model.updated_at = now
        db.flush()
        db.refresh(model)
        return _session_response(model)


def verify_import_session(
    import_session_id: str,
    storage: ImmutableOriginalStorage | None = None,
) -> ImportIntegrityReportResponse:
    immutable_storage = storage or ImmutableOriginalStorage()
    with db_session() as db:
        session = db.query(ImportSession).filter(ImportSession.id == import_session_id).first()
        if session is None:
            raise AppError("import_session_not_found", "Import session not found", 404)
        files = (
            db.query(ImportSourceFile)
            .filter(ImportSourceFile.import_session_id == import_session_id)
            .order_by(ImportSourceFile.created_at.asc(), ImportSourceFile.id.asc())
            .all()
        )

        details: list[ImportFileIntegrityResponse] = []
        missing: list[str] = []
        corrupted: list[str] = []
        for source in files:
            try:
                exists, checksum_match = immutable_storage.verify(
                    source.storage_path, source.sha256
                )
            except ValueError:
                exists, checksum_match = False, False
            details.append(
                ImportFileIntegrityResponse(
                    file_id=source.id,
                    sha256=source.sha256,
                    exists=exists,
                    checksum_match=checksum_match,
                )
            )
            if not exists:
                missing.append(source.id)
            elif not checksum_match:
                corrupted.append(source.id)

        return ImportIntegrityReportResponse(
            import_session_id=import_session_id,
            ok=not missing and not corrupted,
            checked_files=len(files),
            missing_files=missing,
            corrupted_files=corrupted,
            files=details,
        )


def get_source_file_download(
    import_session_id: str,
    file_id: str,
    storage: ImmutableOriginalStorage | None = None,
) -> tuple[Path, ImportSourceFileResponse]:
    immutable_storage = storage or ImmutableOriginalStorage()
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
        try:
            exists, checksum_match = immutable_storage.verify(model.storage_path, model.sha256)
            path = immutable_storage.absolute_path(model.storage_path)
        except ValueError as exc:
            raise AppError("invalid_storage_path", str(exc), 500) from exc
        if not exists:
            raise AppError("import_source_file_missing", "Stored source file is missing", 409)
        if not checksum_match:
            raise AppError(
                "import_source_file_corrupted",
                "Stored source file failed checksum verification",
                409,
            )
        return path, _file_response(model)


def get_source_file_model(file_id: str) -> ImportSourceFile | None:
    with db_session() as db:
        model = db.query(ImportSourceFile).filter(ImportSourceFile.id == file_id).first()
        if model is None:
            return None
        db.expunge(model)
        return model


def _validate_source_file(filename: str, content: bytes) -> str:
    if not filename or filename in {".", ".."}:
        raise AppError("invalid_filename", "A source filename is required", 400)
    if "\x00" in filename or "/" in filename or "\\" in filename:
        raise AppError("unsafe_filename", "Source filename must not contain a path", 400)
    if len(filename) > 512:
        raise AppError("filename_too_long", "Source filename exceeds 512 characters", 400)
    if not content:
        raise AppError("empty_file", "Uploaded source file is empty", 400)

    max_bytes = get_settings().import_max_upload_size_mb * 1024 * 1024
    if len(content) > max_bytes:
        raise AppError(
            "file_too_large",
            f"Source file exceeds maximum size of {get_settings().import_max_upload_size_mb} MB",
            413,
        )
    return filename
