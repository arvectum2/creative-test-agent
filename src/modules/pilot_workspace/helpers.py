"""Shared navigation and validation helpers for pilot workspace routes."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import quote

from fastapi.responses import RedirectResponse

from src.modules.projects.service import get_project
from src.shared.errors import AppError

_TABULAR_EXTENSIONS = {".csv", ".tsv", ".xlsx"}


def require_project(project_id: str):
    project = get_project(project_id)
    if project is None:
        raise AppError("project_not_found", "Project not found", 404)
    return project


def is_tabular(filename: str) -> bool:
    return Path(filename).suffix.lower() in _TABULAR_EXTENSIONS


def workspace_redirect(
    project_id: str,
    *,
    notice: str | None = None,
    error: str | None = None,
):
    query = _query(notice=notice, error=error)
    return RedirectResponse(
        url=f"/ui/pilot-workspaces/{project_id}{query}",
        status_code=303,
    )


def table_redirect(
    project_id: str,
    session_id: str,
    file_id: str,
    table_id: str,
    *,
    notice: str | None = None,
    error: str | None = None,
):
    query = _query(notice=notice, error=error)
    return RedirectResponse(
        url=(
            f"/ui/pilot-workspaces/{project_id}/sessions/{session_id}/files/"
            f"{file_id}/tables/{table_id}{query}"
        ),
        status_code=303,
    )


def quality_redirect(
    project_id: str,
    run_id: str,
    *,
    notice: object | None = None,
    error: object | None = None,
):
    query = _query(
        notice=str(notice) if notice is not None else None,
        error=str(error) if error is not None else None,
    )
    return RedirectResponse(
        url=f"/ui/pilot-workspaces/{project_id}/data-quality/{run_id}{query}",
        status_code=303,
    )


def _query(*, notice: str | None, error: str | None) -> str:
    if notice:
        return f"?notice={quote(notice)}"
    if error:
        return f"?error={quote(error)}"
    return ""
