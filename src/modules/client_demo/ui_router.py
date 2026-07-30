from pathlib import Path
from urllib.parse import urlencode

from fastapi import APIRouter, Form, Request
from fastapi.responses import FileResponse, RedirectResponse

from src.modules.audit_log.service import write_audit_event
from src.modules.client_report_v2.service import generate_client_report_v2
from src.modules.ui.router import _error, _render
from src.shared.errors import AppError

from .service import build_ozon_client_demo

router = APIRouter()
CLIENT_DEMO_CSS = Path(__file__).parents[1] / "ui" / "static" / "client_demo.css"


@router.get("/static/client-demo.css", include_in_schema=False)
def serve_client_demo_css():
    return FileResponse(str(CLIENT_DEMO_CSS), media_type="text/css")


@router.get("/ui/projects/{project_id}/campaign-evidence/demo", include_in_schema=False)
def ui_ozon_client_demo(
    request: Request,
    project_id: str,
    campaign_id: str | None = None,
    report_id: str | None = None,
):
    try:
        demo = build_ozon_client_demo(
            project_id,
            campaign_id=campaign_id,
            report_id=report_id,
        )
    except AppError as exc:
        return _error(request, exc.message)
    return _render(request, "client_demo/ozon.html", demo=demo)


@router.post(
    "/ui/projects/{project_id}/campaign-evidence/demo/report",
    include_in_schema=False,
)
def ui_generate_ozon_demo_report(
    request: Request,
    project_id: str,
    campaign_id: str = Form(default=""),
    locale: str = Form(default="ru"),
):
    if locale not in {"ru", "en"}:
        locale = "ru"
    try:
        report = generate_client_report_v2(project_id, locale=locale)
    except AppError as exc:
        return _error(request, exc.message)
    write_audit_event(
        "cta_demo_001_report_generated",
        "client_report_v2",
        report.report_id,
        {
            "project_id": project_id,
            "campaign_id": campaign_id or None,
            "report_version": report.report_version,
            "release_status": report.release_status,
            "manifest_sha256": report.manifest_sha256,
            "causal_interpretation_allowed": False,
            "individual_asset_outcome_attribution_allowed": False,
        },
    )
    query = urlencode(
        {
            "campaign_id": campaign_id,
            "report_id": report.report_id,
        }
    )
    return RedirectResponse(
        url=f"/ui/projects/{project_id}/campaign-evidence/demo?{query}",
        status_code=303,
    )
