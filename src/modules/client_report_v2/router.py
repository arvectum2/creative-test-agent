from typing import Literal

from fastapi import APIRouter, Query
from fastapi.responses import FileResponse

from src.modules.audit_log.service import write_audit_event
from src.modules.client_report_v2.schemas import ClientReportV2Response, GenerateClientReportV2Request
from src.modules.client_report_v2.service import (
    generate_client_report_v2,
    get_client_report_v2,
    secure_client_report_v2_artifact_path,
)
from src.shared.security.hardening import safe_download_name

router = APIRouter(prefix="/reports-v2", tags=["client-report-v2"])


@router.post("/projects/{project_id}", response_model=ClientReportV2Response)
def post_client_report_v2(project_id: str, body: GenerateClientReportV2Request):
    result = generate_client_report_v2(
        project_id,
        locale=body.locale,
        expert_assessments=body.expert_assessments,
        force=body.force,
    )
    write_audit_event(
        "client_report_v2_generated",
        "client_report_v2",
        result.report_id,
        {
            "project_id": project_id,
            "report_version": result.report_version,
            "input_fingerprint": result.input_fingerprint,
            "release_status": result.release_status,
            "artifact_sha256": {item.artifact_type: item.sha256 for item in result.artifacts},
            "campaign_level_outcomes_only": True,
            "causal_interpretation_allowed": False,
            "force": body.force,
        },
    )
    return result


@router.get("/projects/{project_id}/{report_id}", response_model=ClientReportV2Response)
def get_report(project_id: str, report_id: str):
    return get_client_report_v2(project_id, report_id)


@router.get("/projects/{project_id}/{report_id}/download")
def download_report(
    project_id: str,
    report_id: str,
    artifact: Literal[
        "html", "one_page_pptx", "full_pptx", "docx", "evidence", "xlsx", "manifest"
    ] = Query("full_pptx"),
):
    path, filename, media_type = secure_client_report_v2_artifact_path(project_id, report_id, artifact)
    return FileResponse(
        path=path,
        filename=safe_download_name(filename, "client-report-v2.bin"),
        media_type=media_type,
        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
    )
