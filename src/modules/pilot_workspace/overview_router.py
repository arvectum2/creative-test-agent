"""Pilot workspace listing and project creation routes."""

from __future__ import annotations

from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse

from src.modules.audit_log.service import write_audit_event
from src.modules.clients.schemas import CreateClientRequest
from src.modules.clients.service import create_client, list_clients
from src.modules.pilot_workspace.state import load_workspace
from src.modules.projects.schemas import CreateProjectRequest
from src.modules.projects.service import create_project, list_projects
from src.modules.ui.common import render, render_error
from src.shared.errors import AppError

router = APIRouter(prefix="/ui/pilot-workspaces", tags=["pilot-workspace"])


@router.get("", include_in_schema=False)
def pilot_workspaces_list(request: Request):
    clients = {item.id: item.name for item in list_clients()}
    return render(
        request,
        "pilot_workspaces/list.html",
        projects=list_projects(),
        client_names=clients,
    )


@router.get("/new", include_in_schema=False)
def pilot_workspace_new(request: Request):
    return render(request, "pilot_workspaces/new.html", clients=list_clients())


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
        client_id = _resolve_client_id(
            existing_client_id=existing_client_id,
            new_client_name=new_client_name,
            new_client_industry=new_client_industry,
        )
        project = create_project(
            CreateProjectRequest(
                client_id=client_id,
                name=project_name.strip(),
                description=(project_description or "").strip() or None,
            )
        )
    except (AppError, ValueError) as exc:
        return render(
            request,
            "pilot_workspaces/new.html",
            clients=list_clients(),
            error=getattr(exc, "message", str(exc)),
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


@router.get("/{project_id}", include_in_schema=False)
def pilot_workspace_detail(request: Request, project_id: str):
    try:
        context = load_workspace(project_id)
    except AppError as exc:
        return render_error(request, exc.message)
    return render(
        request,
        "pilot_workspaces/detail.html",
        **context,
        notice=request.query_params.get("notice"),
        error=request.query_params.get("error"),
    )


def _resolve_client_id(
    *,
    existing_client_id: str | None,
    new_client_name: str | None,
    new_client_industry: str | None,
) -> str:
    client_id = (existing_client_id or "").strip()
    if client_id:
        return client_id
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
    return client.id
