"""Pilot workspace source and creative intake routes."""

from __future__ import annotations

from fastapi import APIRouter, File, Form, Request, UploadFile

from src.modules.audit_log.service import write_audit_event
from src.modules.creative_assets.service import create_asset_from_file
from src.modules.creative_assets.upload import process_upload
from src.modules.import_sessions.schemas import CreateImportSessionRequest
from src.modules.import_sessions.service import (
    add_source_file,
    complete_import_session,
    create_import_session,
    list_source_files,
    verify_import_session,
)
from src.modules.import_sessions.tabular_service import inspect_source_file
from src.modules.pilot_workspace.helpers import (
    is_tabular,
    require_project,
    workspace_redirect,
)
from src.shared.errors import AppError
from src.shared.security.auth import get_optional_user_id

router = APIRouter(prefix="/ui/pilot-workspaces", tags=["pilot-workspace"])


@router.post("/{project_id}/intake", include_in_schema=False)
async def pilot_workspace_intake(
    request: Request,
    project_id: str,
    name: str = Form(...),
    notes: str | None = Form(None),
    files: list[UploadFile] = File(...),
):
    try:
        require_project(project_id)
        session = create_import_session(
            CreateImportSessionRequest(
                project_id=project_id,
                name=name.strip(),
                notes=(notes or "").strip() or None,
                metadata={
                    "source": "unified_pilot_workspace",
                    "as_is_intake": True,
                },
            ),
            created_by_user_id=get_optional_user_id(request),
        )
        uploaded = await _add_source_files(request, session.id, files)
        if not uploaded:
            raise AppError("pilot_intake_empty", "Select at least one file", 400)

        completed = complete_import_session(session.id)
        integrity = verify_import_session(completed.id)
        if not integrity.ok:
            raise AppError(
                "pilot_intake_integrity_failed",
                "The uploaded source files failed integrity verification",
                409,
            )
        inspected = _inspect_tabular_sources(completed.id, uploaded)
        write_audit_event(
            "pilot_intake_completed",
            "import_session",
            completed.id,
            {
                "project_id": project_id,
                "file_count": len(uploaded),
                "inspected_tabular_files": inspected,
                "integrity_ok": True,
                "operator_ui": True,
            },
        )
        return workspace_redirect(
            project_id,
            notice=(
                f"Поставка сохранена: {len(uploaded)} файлов, "
                f"таблиц проверено: {inspected}"
            ),
        )
    except (AppError, ValueError) as exc:
        return workspace_redirect(
            project_id,
            error=getattr(exc, "message", str(exc)),
        )


async def _add_source_files(
    request: Request,
    session_id: str,
    files: list[UploadFile],
) -> list:
    uploaded = []
    user_id = get_optional_user_id(request)
    for file in files:
        if not file.filename:
            continue
        uploaded.append(
            add_source_file(
                session_id,
                file.filename,
                await file.read(),
                content_type=file.content_type,
                metadata={"operator_ui": True, "as_is": True},
                uploaded_by_user_id=user_id,
            )
        )
    return uploaded


def _inspect_tabular_sources(session_id: str, sources: list) -> int:
    inspected = 0
    for source in sources:
        if is_tabular(source.original_filename):
            inspect_source_file(session_id, source.id)
            inspected += 1
    return inspected


@router.post("/{project_id}/creative-assets", include_in_schema=False)
async def pilot_workspace_creatives(
    request: Request,
    project_id: str,
    files: list[UploadFile] = File(...),
):
    del request
    try:
        require_project(project_id)
        created = await _create_creatives(project_id, files)
        if not created:
            raise AppError(
                "pilot_creatives_empty",
                "Select at least one creative file",
                400,
            )
        write_audit_event(
            "pilot_creatives_uploaded",
            "project",
            project_id,
            {"creative_count": created, "operator_ui": True},
        )
        return workspace_redirect(
            project_id,
            notice=f"Креативы добавлены: {created}",
        )
    except (AppError, ValueError) as exc:
        return workspace_redirect(
            project_id,
            error=getattr(exc, "message", str(exc)),
        )


async def _create_creatives(project_id: str, files: list[UploadFile]) -> int:
    created = 0
    for file in files:
        if not file.filename:
            continue
        result = process_upload(
            filename=file.filename,
            content=await file.read(),
            content_type=file.content_type or "application/octet-stream",
        )
        create_asset_from_file(
            title=result["original_filename"],
            asset_type=result["asset_type"],
            file_path=result["file_path"],
            original_filename=result["original_filename"],
            mime_type=result["mime_type"],
            file_size_bytes=result["file_size_bytes"],
            extracted_text=result["extracted_text"],
            project_id=project_id,
            metadata={
                **result.get("parser_metadata", {}),
                "warnings": result.get("warnings", []),
                "operator_ui": True,
            },
        )
        created += 1
    return created


@router.post(
    "/{project_id}/sessions/{session_id}/inspect",
    include_in_schema=False,
)
def pilot_workspace_inspect_session(
    request: Request,
    project_id: str,
    session_id: str,
):
    del request
    try:
        require_project(project_id)
        inspected = 0
        for source in list_source_files(session_id):
            if source.project_id != project_id:
                continue
            if is_tabular(source.original_filename):
                inspect_source_file(session_id, source.id, force=True)
                inspected += 1
        return workspace_redirect(
            project_id,
            notice=f"Повторно проверено табличных файлов: {inspected}",
        )
    except (AppError, ValueError) as exc:
        return workspace_redirect(
            project_id,
            error=getattr(exc, "message", str(exc)),
        )
