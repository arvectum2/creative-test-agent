"""Client, project, and project-scoped batch UI routes."""

from __future__ import annotations

import json

from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse

from src.modules.audit_log.service import write_audit_event
from src.modules.audience_profiles.service import list_profiles as list_audience_profiles
from src.modules.batches.schemas import CreateBatchRequest
from src.modules.batches.service import create_batch, list_batches
from src.modules.brand_profiles.service import list_profiles as list_brand_profiles
from src.modules.clients.schemas import CreateClientRequest
from src.modules.clients.service import create_client, get_client, list_clients
from src.modules.creative_assets.service import list_assets
from src.modules.projects.history import get_project_history
from src.modules.projects.schemas import CreateProjectRequest
from src.modules.projects.service import create_project, get_project, list_projects
from src.modules.test_rubrics.service import list_rubrics
from src.modules.test_runs.service import list_test_runs
from src.modules.ui.common import render, render_error
from src.shared.errors import AppError

router = APIRouter()


@router.get("/ui/clients", include_in_schema=False)
def ui_clients_list(request: Request):
    clients = list_clients()
    project_counts: dict[str, int] = {}
    for project in list_projects():
        project_counts[project.client_id] = project_counts.get(project.client_id, 0) + 1
    return render(
        request,
        "clients/list.html",
        clients=clients,
        project_counts=project_counts,
    )


@router.get("/ui/clients/new", include_in_schema=False)
def ui_clients_new(request: Request):
    return render(request, "clients/new.html")


@router.post("/ui/clients", include_in_schema=False)
def ui_clients_create(
    request: Request,
    name: str = Form(...),
    industry: str | None = Form(None),
    description: str | None = Form(None),
    contact_name: str | None = Form(None),
    contact_email: str | None = Form(None),
):
    try:
        client = create_client(
            CreateClientRequest(
                name=name,
                industry=industry,
                description=description,
                contact_name=contact_name,
                contact_email=contact_email,
            )
        )
    except AppError as exc:
        return render(request, "clients/new.html", error=exc.message)
    write_audit_event("client_created", "client", client.id, {"name": client.name})
    return RedirectResponse(url=f"/ui/clients/{client.id}", status_code=303)


@router.get("/ui/clients/{client_id}", include_in_schema=False)
def ui_clients_detail(request: Request, client_id: str):
    client = get_client(client_id)
    if client is None:
        return render_error(request, f"Client not found: {client_id}")
    return render(
        request,
        "clients/detail.html",
        client=client,
        projects=list_projects(client_id=client_id),
    )


@router.get("/ui/clients/{client_id}/projects/new", include_in_schema=False)
def ui_client_projects_new(request: Request, client_id: str):
    return render(request, "projects/new.html", clients=[], client_id=client_id)


@router.get("/ui/projects", include_in_schema=False)
def ui_projects_list(request: Request):
    client_names = {client.id: client.name for client in list_clients()}
    return render(
        request,
        "projects/list.html",
        projects=list_projects(),
        client_names=client_names,
    )


@router.get("/ui/projects/new", include_in_schema=False)
def ui_projects_new(request: Request, client_id: str | None = None):
    return render(
        request,
        "projects/new.html",
        clients=list_clients(),
        client_id=client_id,
    )


@router.post("/ui/projects", include_in_schema=False)
def ui_projects_create(
    request: Request,
    client_id: str = Form(...),
    name: str = Form(...),
    description: str | None = Form(None),
):
    try:
        project = create_project(
            CreateProjectRequest(
                client_id=client_id,
                name=name,
                description=description,
            )
        )
    except AppError as exc:
        return render(
            request,
            "projects/new.html",
            error=exc.message,
            clients=list_clients(),
        )
    write_audit_event(
        "project_created",
        "project",
        project.id,
        {"name": project.name, "client_id": client_id},
    )
    return RedirectResponse(url=f"/ui/projects/{project.id}", status_code=303)


@router.get("/ui/projects/{project_id}", include_in_schema=False)
def ui_projects_detail(request: Request, project_id: str):
    project = get_project(project_id)
    if project is None:
        return render_error(request, f"Project not found: {project_id}")
    client = get_client(project.client_id)
    return render(
        request,
        "projects/detail.html",
        project=project,
        client_name=client.name if client else project.client_id,
        counts=_project_counts(project_id),
        history=get_project_history(project_id),
    )


@router.get("/ui/projects/{project_id}/test-runs/new", include_in_schema=False)
def ui_projects_test_runs_new(request: Request, project_id: str):
    return render(
        request,
        "test_runs/new.html",
        assets=list_assets(),
        brand_profiles=list_brand_profiles(),
        audience_profiles=list_audience_profiles(),
        rubrics=list_rubrics(),
        project_id=project_id,
    )


@router.get("/ui/projects/{project_id}/compare", include_in_schema=False)
def ui_projects_compare(request: Request, project_id: str):
    completed = [
        run
        for run in list_test_runs()
        if run.status == "completed" and getattr(run, "project_id", None) == project_id
    ]
    return render(
        request,
        "reports/compare.html",
        completed_runs=completed,
        project_id=project_id,
    )


@router.get("/ui/projects/{project_id}/reports", include_in_schema=False)
def ui_projects_reports(request: Request, project_id: str):
    from src.modules.report_generator.models import Report
    from src.shared.db.repository import db_session

    with db_session() as db:
        reports = (
            db.query(Report)
            .filter(Report.project_id == project_id)
            .order_by(Report.created_at.desc())
            .all()
        )
    report_list = [
        {
            "id": report.id,
            "test_run_id": report.test_run_id,
            "report_type": report.report_type,
            "created_at": report.created_at,
        }
        for report in reports
    ]
    return render(
        request,
        "reports/project_list.html",
        reports=report_list,
        project_id=project_id,
    )


@router.get("/ui/projects/{project_id}/exports", include_in_schema=False)
def ui_projects_exports(request: Request, project_id: str):
    return render(
        request,
        "exports/project_list.html",
        jobs=[],
        project_id=project_id,
    )


@router.get("/ui/projects/{project_id}/batches", include_in_schema=False)
def ui_projects_batches(request: Request, project_id: str):
    return render(
        request,
        "batches/list.html",
        batches=list_batches(project_id=project_id),
    )


@router.get("/ui/projects/{project_id}/batches/new", include_in_schema=False)
def ui_projects_batches_new(request: Request, project_id: str):
    return render(request, "batches/new.html", project_id=project_id)


@router.post("/ui/projects/{project_id}/batches", include_in_schema=False)
async def ui_projects_batches_create(
    request: Request,
    project_id: str,
    name: str = Form(...),
    description: str | None = Form(None),
    creative_asset_ids: str | None = Form(None),
    audience_profile_ids: str | None = Form(None),
    brand_profile_id: str | None = Form(None),
    test_rubric_id: str | None = Form(None),
    input_context: str | None = Form(None),
):
    payload = _batch_payload(
        project_id=project_id,
        name=name,
        description=description,
        creative_asset_ids=creative_asset_ids,
        audience_profile_ids=audience_profile_ids,
        brand_profile_id=brand_profile_id,
        test_rubric_id=test_rubric_id,
        input_context=input_context,
    )
    try:
        batch = create_batch(CreateBatchRequest(**payload))
    except Exception as exc:
        return render(
            request,
            "batches/new.html",
            error=str(exc),
            project_id=project_id,
        )
    write_audit_event("batch_created", "batch_run", batch.id, {"name": name})
    return RedirectResponse(url=f"/ui/batches/{batch.id}", status_code=303)


def _batch_payload(**values) -> dict:
    creative_ids = values.pop("creative_asset_ids")
    audience_ids = values.pop("audience_profile_ids")
    raw_context = values.pop("input_context")
    context = {}
    if raw_context:
        try:
            context = json.loads(raw_context)
        except json.JSONDecodeError:
            context = {}
    return {
        **values,
        "description": values.get("description") or None,
        "creative_asset_ids": _lines(creative_ids),
        "audience_profile_ids": _lines(audience_ids),
        "brand_profile_id": values.get("brand_profile_id") or None,
        "test_rubric_id": values.get("test_rubric_id") or None,
        "input_context": context,
    }


def _lines(value: str | None) -> list[str]:
    return [item.strip() for item in value.split("\n") if item.strip()] if value else []


def _project_counts(project_id: str) -> dict[str, int]:
    from src.modules.audience_profiles.models import AudienceProfile
    from src.modules.batches.models import BatchRun
    from src.modules.brand_profiles.models import BrandProfile
    from src.modules.brandbooks.models import BrandbookDocument
    from src.modules.creative_assets.models import CreativeAsset
    from src.modules.knowledge_base.models import KnowledgeItem
    from src.modules.report_generator.models import Report
    from src.modules.test_runs.models import TestRun
    from src.shared.db.repository import db_session

    with db_session() as db:
        runs = db.query(TestRun).filter(TestRun.project_id == project_id).all()
        return {
            "creative_assets": db.query(CreativeAsset).filter(CreativeAsset.project_id == project_id).count(),
            "brand_profiles": db.query(BrandProfile).filter(BrandProfile.project_id == project_id).count(),
            "audience_profiles": db.query(AudienceProfile).filter(AudienceProfile.project_id == project_id).count(),
            "brandbooks": db.query(BrandbookDocument).filter(BrandbookDocument.project_id == project_id).count(),
            "knowledge_items": db.query(KnowledgeItem).filter(KnowledgeItem.project_id == project_id).count(),
            "test_runs": len(runs),
            "completed_runs": sum(1 for run in runs if run.status == "completed"),
            "reports": db.query(Report).filter(Report.project_id == project_id).count(),
            "exports": 0,
            "batches": db.query(BatchRun).filter(BatchRun.project_id == project_id).count(),
        }
