"""Pilot workspace table mapping, normalization, and quality routes."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

from src.modules.data_quality.service import (
    generate_data_quality_report,
    get_latest_data_quality_report,
)
from src.modules.import_sessions.tabular_service import get_source_table_detail
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
from src.modules.pilot_workspace.helpers import require_project, table_redirect
from src.modules.ui.common import render, render_error
from src.shared.errors import AppError
from src.shared.security.auth import get_optional_user_id

router = APIRouter(prefix="/ui/pilot-workspaces", tags=["pilot-workspace"])


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
        project = require_project(project_id)
        detail = get_source_table_detail(
            session_id,
            file_id,
            table_id,
            preview_limit=25,
        )
        mapping = get_table_mapping(session_id, file_id, table_id)
        normalization = get_latest_normalization(session_id, file_id, table_id)
        quality = get_latest_data_quality_report(session_id, file_id, table_id)
    except AppError as exc:
        return render_error(request, exc.message)
    return render(
        request,
        "pilot_workspaces/table.html",
        project=project,
        session_id=session_id,
        file_id=file_id,
        table=detail,
        mapping=mapping,
        mapping_fields=list_mapping_fields(),
        normalization=normalization,
        quality=quality,
        notice=request.query_params.get("notice"),
        error=request.query_params.get("error"),
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
            created_by_user_id=get_optional_user_id(request),
        )
        return table_redirect(
            project_id,
            session_id,
            file_id,
            table_id,
            notice="Предложения по колонкам обновлены",
        )
    except (AppError, ValueError) as exc:
        return table_redirect(
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
        decided = await _apply_mapping_form(
            request,
            session_id=session_id,
            file_id=file_id,
            table_id=table_id,
        )
        return table_redirect(
            project_id,
            session_id,
            file_id,
            table_id,
            notice=f"Решения по колонкам сохранены: {decided}",
        )
    except (AppError, ValueError) as exc:
        return table_redirect(
            project_id,
            session_id,
            file_id,
            table_id,
            error=getattr(exc, "message", str(exc)),
        )


async def _apply_mapping_form(
    request: Request,
    *,
    session_id: str,
    file_id: str,
    table_id: str,
) -> int:
    form = await request.form()
    mapping = get_table_mapping(session_id, file_id, table_id)
    user_id = get_optional_user_id(request)
    decided = 0
    for column in mapping.columns:
        raw = str(form.get(f"mapping_{column.source_column_id}", "")).strip()
        if not raw:
            continue
        allow_duplicate = str(
            form.get(f"allow_duplicate_{column.source_column_id}", "")
        ).lower() in {"1", "true", "on", "yes"}
        body = _mapping_decision(column, raw, allow_duplicate=allow_duplicate)
        decide_column_mapping(
            session_id,
            file_id,
            table_id,
            column.source_column_id,
            body,
            decided_by_user_id=user_id,
        )
        decided += 1
    return decided


def _mapping_decision(column, raw: str, *, allow_duplicate: bool):
    if raw == "__rejected__":
        return ColumnMappingDecisionRequest(status="rejected")
    if raw == "__unmapped__":
        return ColumnMappingDecisionRequest(status="unmapped")
    selected = next(
        (item for item in column.suggestions if item.target_field == raw),
        None,
    )
    return ColumnMappingDecisionRequest(
        status="confirmed",
        target_field=raw,
        selected_suggestion_id=selected.id if selected else None,
        rationale={"source": "unified_pilot_workspace"},
        allow_duplicate=allow_duplicate,
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
            created_by_user_id=get_optional_user_id(request),
        )
        return table_redirect(
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
        return table_redirect(
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
            created_by_user_id=get_optional_user_id(request),
        )
        return RedirectResponse(
            url=f"/ui/pilot-workspaces/{project_id}/data-quality/{result.run.id}",
            status_code=303,
        )
    except (AppError, ValueError) as exc:
        return table_redirect(
            project_id,
            session_id,
            file_id,
            table_id,
            error=getattr(exc, "message", str(exc)),
        )
