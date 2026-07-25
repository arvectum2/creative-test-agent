from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import RedirectResponse

from src.modules.audit_log.service import write_audit_event
from src.modules.clarifications.lifecycle import record_clarification_response
from src.modules.clarifications.schemas import SubmitClarificationResponseRequest
from src.modules.clarifications.service import (
    generate_clarifications,
    get_latest_clarifications,
)
from src.modules.client_one_page_reports.service import (
    generate_client_one_page_report,
    get_latest_client_one_page_report,
)
from src.modules.clients.schemas import CreateClientRequest
from src.modules.clients.service import create_client, get_client, list_clients
from src.modules.creative_assets.service import create_asset_from_file, list_assets
from src.modules.creative_assets.upload import process_upload
from src.modules.data_quality.service import (
    generate_data_quality_report,
    get_data_quality_report,
    get_latest_data_quality_report,
)
from src.modules.data_review_reports.service import (
    generate_data_review_report,
    get_latest_data_review_report,
)
from src.modules.import_sessions.schemas import CreateImportSessionRequest
from src.modules.import_sessions.service import (
    add_source_file,
    complete_import_session,
    create_import_session,
    list_import_sessions,
    list_source_files,
    verify_import_session,
)
from src.modules.import_sessions.tabular_service import (
    get_latest_source_inspection,
    get_source_table_detail,
    inspect_source_file,
    list_source_tables,
)
from src.modules.mapping_engine.schemas import ColumnMappingDecisionRequest
from src.modules.mapping_engine.service import (
    decide_column_mapping,
    generate_mapping_suggestions,
    get_table_mapping,
    list_mapping_fields,
)
from src.modules.normalized_data.service import (
    get_latest_normalization,
    normalize_source_table,
)
from src.modules.prediction_readiness.service import (
    evaluate_prediction_readiness,
    get_latest_prediction_readiness,
)
from src.modules.projects.schemas import CreateProjectRequest
from src.modules.projects.service import create_project, get_project, list_projects
from src.modules.ui.router import _error, _render
from src.shared.errors import AppError
from src.shared.security.auth import get_current_user_from_request

router = APIRouter(prefix="/ui/pilot-workspaces", tags=["pilot-workspace"])

_TABULAR_EXTENSIONS = {".csv", ".tsv", ".xlsx"}


def _user_id(request: Request) -> str | None:
    try:
        user = get_current_user_from_request(request)
    except Exception:
        return None
    return user.get("user_id") or user.get("id")


def _require_project(project_id: str):
    project = get_project(project_id)
    if project is None:
        raise AppError("project_not_found", "Project not found", 404)
    return project


def _redirect(project_id: str, *, notice: str | None = None, error: str | None = None):
    query = ""
    if notice:
        from urllib.parse import quote

        query = f"?notice={quote(notice)}"
    elif error:
        from urllib.parse import quote

        query = f"?error={quote(error)}"
    return RedirectResponse(url=f"/ui/pilot-workspaces/{project_id}{query}", status_code=303)


def _is_tabular(filename: str) -> bool:
    return Path(filename).suffix.lower() in _TABULAR_EXTENSIONS


def _load_workspace(project_id: str) -> dict[str, Any]:
    project = _require_project(project_id)
    client = get_client(project.client_id)
    sessions = list_import_sessions(project_id=project_id)
    project_assets = [item for item in list_assets() if getattr(item, "project_id", None) == project_id]

    session_cards: list[dict[str, Any]] = []
    table_count = 0
    mapped_table_count = 0
    normalized_table_count = 0
    quality_table_count = 0
    ready_table_count = 0

    for session in sorted(sessions, key=lambda item: item.created_at or "", reverse=True):
        files = list_source_files(session.id)
        file_cards: list[dict[str, Any]] = []
        integrity = verify_import_session(session.id) if session.status == "completed" else None
        for source in files:
            inspection = get_latest_source_inspection(session.id, source.id)
            tables = []
            if inspection is not None and inspection.status == "completed":
                tables = list_source_tables(session.id, source.id)
            table_cards = []
            for table in tables:
                table_count += 1
                mapping = get_table_mapping(session.id, source.id, table.id)
                normalization = get_latest_normalization(session.id, source.id, table.id)
                quality = get_latest_data_quality_report(session.id, source.id, table.id)
                readiness = (
                    get_latest_prediction_readiness(quality.run.id)
                    if quality is not None
                    else None
                )
                if mapping.confirmed_columns:
                    mapped_table_count += 1
                if normalization is not None:
                    normalized_table_count += 1
                if quality is not None:
                    quality_table_count += 1
                if readiness is not None:
                    ready_table_count += 1
                table_cards.append(
                    {
                        "table": table,
                        "mapping": mapping,
                        "normalization": normalization,
                        "quality": quality,
                        "readiness": readiness,
                    }
                )
            file_cards.append(
                {
                    "source": source,
                    "inspection": inspection,
                    "tables": table_cards,
                    "tabular": _is_tabular(source.original_filename),
                }
            )
        session_cards.append(
            {
                "session": session,
                "files": file_cards,
                "integrity": integrity,
            }
        )

    progress = {
        "project": True,
        "materials": bool(sessions or project_assets),
        "inspection": table_count > 0,
        "mapping": table_count > 0 and mapped_table_count == table_count,
        "normalization": table_count > 0 and normalized_table_count == table_count,
        "quality": table_count > 0 and quality_table_count == table_count,
        "readiness": table_count > 0 and ready_table_count == table_count,
    }
    return {
        "project": project,
        "client": client,
        "sessions": session_cards,
        "assets": project_assets,
        "progress": progress,
        "counts": {
            "sessions": len(sessions),
            "assets": len(project_assets),
            "tables": table_count,
            "mapped_tables": mapped_table_count,
            "normalized_tables": normalized_table_count,
            "quality_tables": quality_table_count,
            "ready_tables": ready_table_count,
        },
    }


@router.get("", include_in_schema=False)
def pilot_workspaces_list(request: Request):
    clients = {item.id: item.name for item in list_clients()}
    projects = list_projects()
    return _render(
        request,
        "pilot_workspaces/list.html",
        projects=projects,
        client_names=clients,
    )


@router.get("/new", include_in_schema=False)
def pilot_workspace_new(request: Request):
    return _render(request, "pilot_workspaces/new.html", clients=list_clients())


@router.post("/new", include_in_schema=False)
def pilot_workspace_create(
    request: Request,
    project_name: str = Form(...),
    project_description: str | None = Form(None),
    existing_client_id: str | None = Form(None),
    new_client_name: str | None = Form(None),
    new_client_industry: str | None = Form(None),
):
    try:
        client_id = (existing_client_id or "").strip()
        if not client_id:
            client_name = (new_client_name or "").strip()
            if not client_name:
                raise AppError(
                    "pilot_client_required",
                    "Select an existing client or enter a new client name",
                    400,
                )
            client = create_client(
                CreateClientRequest(
                    name=client_name,
                    industry=(new_client_industry or "").strip() or None,
                    description="Created from Unified Pilot Workspace",
                )
            )
            client_id = client.id
        project = create_project(
            CreateProjectRequest(
                client_id=client_id,
                name=project_name.strip(),
                description=(project_description or "").strip() or None,
            )
        )
        write_audit_event(
            "pilot_workspace_created",
            "project",
            project.id,
            {"client_id": client_id, "operator_ui": True},
        )
        return RedirectResponse(
            url=f"/ui/pilot-workspaces/{project.id}?notice=Пилот создан",
            status_code=303,
        )
    except (AppError, ValueError) as exc:
        message = getattr(exc, "message", str(exc))
        return _render(
            request,
            "pilot_workspaces/new.html",
            clients=list_clients(),
            error=message,
        )


@router.get("/{project_id}", include_in_schema=False)
def pilot_workspace_detail(request: Request, project_id: str):
    try:
        context = _load_workspace(project_id)
    except AppError as exc:
        return _error(request, exc.message)
    return _render(
        request,
        "pilot_workspaces/detail.html",
        **context,
        notice=request.query_params.get("notice"),
        error=request.query_params.get("error"),
    )


@router.post("/{project_id}/intake", include_in_schema=False)
async def pilot_workspace_intake(
    request: Request,
    project_id: str,
    name: str = Form(...),
    notes: str | None = Form(None),
    files: list[UploadFile] = File(...),
):
    try:
        _require_project(project_id)
        session = create_import_session(
            CreateImportSessionRequest(
                project_id=project_id,
                name=name.strip(),
                notes=(notes or "").strip() or None,
                metadata={"source": "unified_pilot_workspace", "as_is_intake": True},
            ),
            created_by_user_id=_user_id(request),
        )
        uploaded = []
        for file in files:
            if not file.filename:
                continue
            content = await file.read()
            source = add_source_file(
                session.id,
                file.filename,
                content,
                content_type=file.content_type,
                metadata={"operator_ui": True, "as_is": True},
                uploaded_by_user_id=_user_id(request),
            )
            uploaded.append(source)
        if not uploaded:
            raise AppError("pilot_intake_empty", "Select at least one file", 400)
        complete_import_session(session.id)
        integrity = verify_import_session(session.id)
        if not integrity.ok:
            raise AppError(
                "pilot_intake_integrity_failed",
                "The uploaded source files failed integrity verification",
                409,
            )
        inspected = 0
        for source in uploaded:
            if _is_tabular(source.original_filename):
                inspect_source_file(session.id, source.id)
                inspected += 1
        write_audit_event(
            "pilot_intake_completed",
            "import_session",
            session.id,
            {
                "project_id": project_id,
                "file_count": len(uploaded),
                "inspected_tabular_files": inspected,
                "integrity_ok": True,
                "operator_ui": True,
            },
        )
        return _redirect(
            project_id,
            notice=f"Поставка сохранена: {len(uploaded)} файлов, таблиц проверено: {inspected}",
        )
    except (AppError, ValueError) as exc:
        return _redirect(project_id, error=getattr(exc, "message", str(exc)))


@router.post("/{project_id}/creative-assets", include_in_schema=False)
async def pilot_workspace_creatives(
    request: Request,
    project_id: str,
    files: list[UploadFile] = File(...),
):
    try:
        _require_project(project_id)
        created = 0
        for file in files:
            if not file.filename:
                continue
            content = await file.read()
            result = process_upload(
                filename=file.filename,
                content=content,
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
        if not created:
            raise AppError("pilot_creatives_empty", "Select at least one creative file", 400)
        write_audit_event(
            "pilot_creatives_uploaded",
            "project",
            project_id,
            {"creative_count": created, "operator_ui": True},
        )
        return _redirect(project_id, notice=f"Креативы добавлены: {created}")
    except (AppError, ValueError) as exc:
        return _redirect(project_id, error=getattr(exc, "message", str(exc)))


@router.post("/{project_id}/sessions/{session_id}/inspect", include_in_schema=False)
def pilot_workspace_inspect_session(request: Request, project_id: str, session_id: str):
    try:
        _require_project(project_id)
        inspected = 0
        for source in list_source_files(session_id):
            if source.project_id != project_id:
                continue
            if _is_tabular(source.original_filename):
                inspect_source_file(session_id, source.id, force=True)
                inspected += 1
        return _redirect(project_id, notice=f"Повторно проверено табличных файлов: {inspected}")
    except (AppError, ValueError) as exc:
        return _redirect(project_id, error=getattr(exc, "message", str(exc)))


@router.get(
    "/{project_id}/sessions/{session_id}/files/{file_id}/tables/{table_id}",
    include_in_schema=False,
)
def pilot_workspace_table(
    request: Request,
    project_id: str,
    session_id: str,
    file_id: str,
    table_id: str,
):
    try:
        project = _require_project(project_id)
        detail = get_source_table_detail(
            session_id,
            file_id,
            table_id,
            preview_limit=25,
        )
        mapping = get_table_mapping(session_id, file_id, table_id)
        fields = list_mapping_fields()
        normalization = get_latest_normalization(session_id, file_id, table_id)
        quality = get_latest_data_quality_report(session_id, file_id, table_id)
    except AppError as exc:
        return _error(request, exc.message)
    return _render(
        request,
        "pilot_workspaces/table.html",
        project=project,
        session_id=session_id,
        file_id=file_id,
        table=detail,
        mapping=mapping,
        mapping_fields=fields,
        normalization=normalization,
        quality=quality,
        notice=request.query_params.get("notice"),
        error=request.query_params.get("error"),
    )


def _table_redirect(
    project_id: str,
    session_id: str,
    file_id: str,
    table_id: str,
    *,
    notice: str | None = None,
    error: str | None = None,
):
    from urllib.parse import quote

    query = ""
    if notice:
        query = f"?notice={quote(notice)}"
    elif error:
        query = f"?error={quote(error)}"
    return RedirectResponse(
        url=(
            f"/ui/pilot-workspaces/{project_id}/sessions/{session_id}/files/"
            f"{file_id}/tables/{table_id}{query}"
        ),
        status_code=303,
    )


@router.post(
    "/{project_id}/sessions/{session_id}/files/{file_id}/tables/{table_id}/mapping/suggest",
    include_in_schema=False,
)
def pilot_workspace_mapping_suggest(
    request: Request,
    project_id: str,
    session_id: str,
    file_id: str,
    table_id: str,
):
    try:
        generate_mapping_suggestions(
            session_id,
            file_id,
            table_id,
            force=True,
            created_by_user_id=_user_id(request),
        )
        return _table_redirect(
            project_id,
            session_id,
            file_id,
            table_id,
            notice="Предложения по колонкам обновлены",
        )
    except (AppError, ValueError) as exc:
        return _table_redirect(
            project_id,
            session_id,
            file_id,
            table_id,
            error=getattr(exc, "message", str(exc)),
        )


@router.post(
    "/{project_id}/sessions/{session_id}/files/{file_id}/tables/{table_id}/mapping",
    include_in_schema=False,
)
async def pilot_workspace_mapping_save(
    request: Request,
    project_id: str,
    session_id: str,
    file_id: str,
    table_id: str,
):
    try:
        form = await request.form()
        mapping = get_table_mapping(session_id, file_id, table_id)
        decided = 0
        for column in mapping.columns:
            raw = str(form.get(f"mapping_{column.source_column_id}", "")).strip()
            if not raw:
                continue
            allow_duplicate = str(
                form.get(f"allow_duplicate_{column.source_column_id}", "")
            ).lower() in {"1", "true", "on", "yes"}
            if raw == "__rejected__":
                body = ColumnMappingDecisionRequest(status="rejected")
            elif raw == "__unmapped__":
                body = ColumnMappingDecisionRequest(status="unmapped")
            else:
                selected = next(
                    (item for item in column.suggestions if item.target_field == raw),
                    None,
                )
                body = ColumnMappingDecisionRequest(
                    status="confirmed",
                    target_field=raw,
                    selected_suggestion_id=selected.id if selected else None,
                    rationale={"source": "unified_pilot_workspace"},
                    allow_duplicate=allow_duplicate,
                )
            decide_column_mapping(
                session_id,
                file_id,
                table_id,
                column.source_column_id,
                body,
                decided_by_user_id=_user_id(request),
            )
            decided += 1
        return _table_redirect(
            project_id,
            session_id,
            file_id,
            table_id,
            notice=f"Решения по колонкам сохранены: {decided}",
        )
    except (AppError, ValueError) as exc:
        return _table_redirect(
            project_id,
            session_id,
            file_id,
            table_id,
            error=getattr(exc, "message", str(exc)),
        )


@router.post(
    "/{project_id}/sessions/{session_id}/files/{file_id}/tables/{table_id}/normalize",
    include_in_schema=False,
)
def pilot_workspace_normalize(
    request: Request,
    project_id: str,
    session_id: str,
    file_id: str,
    table_id: str,
):
    try:
        result = normalize_source_table(
            session_id,
            file_id,
            table_id,
            force=True,
            created_by_user_id=_user_id(request),
        )
        return _table_redirect(
            project_id,
            session_id,
            file_id,
            table_id,
            notice=(
                f"Нормализация завершена: {result.run.normalized_row_count} готово, "
                f"{result.run.partial_row_count} требуют проверки"
            ),
        )
    except (AppError, ValueError) as exc:
        return _table_redirect(
            project_id,
            session_id,
            file_id,
            table_id,
            error=getattr(exc, "message", str(exc)),
        )


@router.post(
    "/{project_id}/sessions/{session_id}/files/{file_id}/tables/{table_id}/data-quality",
    include_in_schema=False,
)
def pilot_workspace_data_quality(
    request: Request,
    project_id: str,
    session_id: str,
    file_id: str,
    table_id: str,
):
    try:
        result = generate_data_quality_report(
            session_id,
            file_id,
            table_id,
            force=True,
            created_by_user_id=_user_id(request),
        )
        return RedirectResponse(
            url=f"/ui/pilot-workspaces/{project_id}/data-quality/{result.run.id}",
            status_code=303,
        )
    except (AppError, ValueError) as exc:
        return _table_redirect(
            project_id,
            session_id,
            file_id,
            table_id,
            error=getattr(exc, "message", str(exc)),
        )


@router.get("/{project_id}/data-quality/{run_id}", include_in_schema=False)
def pilot_workspace_quality(request: Request, project_id: str, run_id: str):
    try:
        project = _require_project(project_id)
        quality = get_data_quality_report(run_id)
        if quality is None or quality.run.project_id != project_id:
            raise AppError("data_quality_run_not_found", "Data-quality run not found", 404)
        client_questions = get_latest_clarifications(run_id, audience="client")
        analyst_questions = get_latest_clarifications(run_id, audience="analyst")
        readiness = get_latest_prediction_readiness(run_id)
        data_review = get_latest_data_review_report(run_id)
        one_page = get_latest_client_one_page_report(run_id)
    except AppError as exc:
        return _error(request, exc.message)
    return _render(
        request,
        "pilot_workspaces/data_quality.html",
        project=project,
        quality=quality,
        client_questions=client_questions,
        analyst_questions=analyst_questions,
        readiness=readiness,
        data_review=data_review,
        one_page=one_page,
        notice=request.query_params.get("notice"),
        error=request.query_params.get("error"),
    )


def _quality_redirect(project_id: str, run_id: str, *, notice=None, error=None):
    from urllib.parse import quote

    query = ""
    if notice:
        query = f"?notice={quote(str(notice))}"
    elif error:
        query = f"?error={quote(str(error))}"
    return RedirectResponse(
        url=f"/ui/pilot-workspaces/{project_id}/data-quality/{run_id}{query}",
        status_code=303,
    )


@router.post(
    "/{project_id}/data-quality/{run_id}/clarifications",
    include_in_schema=False,
)
def pilot_workspace_clarifications(
    request: Request,
    project_id: str,
    run_id: str,
    audience: str = Form("client"),
):
    try:
        result = generate_clarifications(
            run_id,
            audience=audience,
            max_questions=5,
            force=True,
            created_by_user_id=_user_id(request),
        )
        return _quality_redirect(
            project_id,
            run_id,
            notice=f"Сформировано вопросов: {result.run.question_count}",
        )
    except (AppError, ValueError) as exc:
        return _quality_redirect(
            project_id,
            run_id,
            error=getattr(exc, "message", str(exc)),
        )


@router.post(
    "/{project_id}/data-quality/{run_id}/questions/{question_id}",
    include_in_schema=False,
)
def pilot_workspace_answer_question(
    request: Request,
    project_id: str,
    run_id: str,
    question_id: str,
    resolution: str = Form("answered"),
    answer: str | None = Form(None),
    note: str | None = Form(None),
):
    try:
        record_clarification_response(
            question_id,
            SubmitClarificationResponseRequest(
                resolution=resolution,
                answer=(answer or "").strip() or None,
                note=(note or "").strip() or None,
            ),
            responded_by_user_id=_user_id(request),
        )
        return _quality_redirect(project_id, run_id, notice="Ответ сохранён")
    except (AppError, ValueError) as exc:
        return _quality_redirect(
            project_id,
            run_id,
            error=getattr(exc, "message", str(exc)),
        )


@router.post(
    "/{project_id}/data-quality/{run_id}/readiness",
    include_in_schema=False,
)
def pilot_workspace_readiness(request: Request, project_id: str, run_id: str):
    try:
        result = evaluate_prediction_readiness(
            run_id,
            force=True,
            created_by_user_id=_user_id(request),
        )
        return _quality_redirect(
            project_id,
            run_id,
            notice=f"Готовность обновлена: {result.run.overall_status}",
        )
    except (AppError, ValueError) as exc:
        return _quality_redirect(
            project_id,
            run_id,
            error=getattr(exc, "message", str(exc)),
        )


@router.post(
    "/{project_id}/data-quality/{run_id}/reports/data-review",
    include_in_schema=False,
)
def pilot_workspace_data_review_report(
    request: Request,
    project_id: str,
    run_id: str,
):
    try:
        readiness = get_latest_prediction_readiness(run_id)
        result = generate_data_review_report(
            run_id,
            prediction_readiness_run_id=readiness.run.id if readiness else None,
            quantitative_study_id=None,
            force=True,
            created_by_user_id=_user_id(request),
        )
        return _quality_redirect(
            project_id,
            run_id,
            notice=f"XLSX-отчёт сформирован: {result.filename}",
        )
    except (AppError, ValueError) as exc:
        return _quality_redirect(
            project_id,
            run_id,
            error=getattr(exc, "message", str(exc)),
        )


@router.post(
    "/{project_id}/data-quality/{run_id}/reports/one-page",
    include_in_schema=False,
)
def pilot_workspace_one_page_report(
    request: Request,
    project_id: str,
    run_id: str,
    locale: str = Form("ru"),
):
    try:
        readiness = get_latest_prediction_readiness(run_id)
        result = generate_client_one_page_report(
            run_id,
            prediction_readiness_run_id=readiness.run.id if readiness else None,
            quantitative_study_id=None,
            locale=locale if locale in {"ru", "en"} else "ru",
            force=True,
            created_by_user_id=_user_id(request),
        )
        return _quality_redirect(
            project_id,
            run_id,
            notice=f"Одностраничный отчёт сформирован: {result.verdict}",
        )
    except (AppError, ValueError) as exc:
        return _quality_redirect(
            project_id,
            run_id,
            error=getattr(exc, "message", str(exc)),
        )
