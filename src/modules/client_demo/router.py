from fastapi import APIRouter, Query

from .schemas import OzonClientDemoState
from .service import build_ozon_client_demo

router = APIRouter(prefix="/demo", tags=["client-demo"])


@router.get("/projects/{project_id}", response_model=OzonClientDemoState)
def get_ozon_client_demo(
    project_id: str,
    campaign_id: str | None = Query(default=None),
    report_id: str | None = Query(default=None),
):
    return build_ozon_client_demo(
        project_id,
        campaign_id=campaign_id,
        report_id=report_id,
    )
