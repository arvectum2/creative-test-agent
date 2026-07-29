from fastapi import APIRouter

from .schemas import CampaignEvidence, CampaignEvidenceWorkspace
from .service import get_campaign_evidence_detail, get_campaign_evidence_workspace


router = APIRouter(prefix="/campaign-evidence", tags=["campaign-evidence"])


@router.get("/projects/{project_id}", response_model=CampaignEvidenceWorkspace)
def get_project_campaign_evidence(project_id: str):
    return get_campaign_evidence_workspace(project_id)


@router.get(
    "/projects/{project_id}/campaigns/{campaign_id}",
    response_model=CampaignEvidence,
)
def get_project_campaign_evidence_detail(project_id: str, campaign_id: str):
    return get_campaign_evidence_detail(project_id, campaign_id)
