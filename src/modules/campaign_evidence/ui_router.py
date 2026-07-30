from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse

from src.modules.client_demo.ui_router import router as client_demo_ui_router
from src.modules.ui.router import _error, _render
from src.shared.errors import AppError

from .service import get_campaign_evidence_detail, get_campaign_evidence_workspace


router = APIRouter()
router.include_router(client_demo_ui_router)
CAMPAIGN_EVIDENCE_CSS = Path(__file__).parents[1] / "ui" / "static" / "campaign_evidence.css"


@router.get("/static/campaign-evidence.css", include_in_schema=False)
def serve_campaign_evidence_css():
    return FileResponse(str(CAMPAIGN_EVIDENCE_CSS), media_type="text/css")


@router.get("/ui/projects/{project_id}/campaign-evidence", include_in_schema=False)
def ui_campaign_evidence_workspace(request: Request, project_id: str):
    try:
        workspace = get_campaign_evidence_workspace(project_id)
    except AppError as exc:
        return _error(request, exc.message)
    return _render(
        request,
        "campaign_evidence/list.html",
        workspace=workspace,
    )


@router.get(
    "/ui/projects/{project_id}/campaign-evidence/{campaign_id}",
    include_in_schema=False,
)
def ui_campaign_evidence_detail(request: Request, project_id: str, campaign_id: str):
    try:
        workspace = get_campaign_evidence_workspace(project_id)
        campaign = get_campaign_evidence_detail(project_id, campaign_id)
    except AppError as exc:
        return _error(request, exc.message)
    return _render(
        request,
        "campaign_evidence/detail.html",
        workspace=workspace,
        campaign=campaign,
    )
