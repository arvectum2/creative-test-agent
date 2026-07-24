from typing import Literal

from fastapi import APIRouter, Query, Request
from fastapi.responses import FileResponse

from src.modules.audit_log.service import write_audit_event
from src.modules.client_one_page_reports.schemas import (
    ClientOnePageReportResponse,
    GenerateClientOnePageReportRequest,
)
from src.modules.client_one_page_reports.secure_download import (
    secure_client_one_page_artifact_path,
)
from src.modules.client_one_page_reports.service import (
    generate_client_one_page_report,
    get_client_one_page_report,
    get_latest_client_one_page_report,
)
from src.shared.errors import AppError
from src.shared.security.auth import get_current_user_from_request
from src.shared.security.hardening import safe_download_name

router = APIRouter(tags=["client-one-page-reports"])


def _user_id(request: Request) -> str | None:
    try:
        user = get_current_user_from_request(request)
    except Exception:
        return None
    return user.get("user_id") or user.get("id")


@router.post(
    "/data-quality-runs/{data_quality_run_id}/client-one-page-report",
    response_model=ClientOnePageReportResponse,
)
def post_client_one_page_report(
    data_quality_run_id: str,
    body: GenerateClientOnePageReportRequest,
    request: Request,
):
    result = generate_client_one_page_report(
        data_quality_run_id,
        prediction_readiness_run_id=body.prediction_readiness_run_id,
        quantitative_study_id=body.quantitative_study_id,
        locale=body.locale,
        force=body.force,
        created_by_user_id=_user_id(request),
    )
    write_audit_event(
        "client_one_page_report_generated",
        "client_one_page_report_run",
        result.id,
        {
            "data_quality_run_id": result.data_quality_run_id,
            "prediction_readiness_run_id": result.prediction_readiness_run_id,
            "quantitative_study_id": result.quantitative_study_id,
            "locale": result.locale,
            "verdict": result.verdict,
            "artifact_sha256": {item.artifact_type: item.sha256 for item in result.artifacts},
            "manifest_sha256": result.manifest_sha256,
            "slide_count": result.slide_count,
            "prediction_generated": False,
            "market_effectiveness_not_evaluated": True,
            "force": body.force,
        },
    )
    return result


@router.get(
    "/data-quality-runs/{data_quality_run_id}/client-one-page-report/latest",
    response_model=ClientOnePageReportResponse,
)
def get_latest_report(data_quality_run_id: str):
    result = get_latest_client_one_page_report(data_quality_run_id)
    if result is None:
        raise AppError("client_one_page_report_not_found", "Client one-page report not found", 404)
    return result


@router.get(
    "/client-one-page-reports/{report_id}",
    response_model=ClientOnePageReportResponse,
)
def get_report(report_id: str):
    result = get_client_one_page_report(report_id)
    if result is None:
        raise AppError("client_one_page_report_not_found", "Client one-page report not found", 404)
    return result


@router.get("/client-one-page-reports/{report_id}/download")
def download_report_artifact(
    report_id: str,
    artifact: Literal["pptx", "html", "evidence", "manifest"] = Query("pptx"),
):
    path, filename, media_type = secure_client_one_page_artifact_path(report_id, artifact)
    fallback = {
        "pptx": "client-one-page-report.pptx",
        "html": "client-one-page-report.html",
        "evidence": "client-one-page-report-evidence.json",
        "manifest": "client-one-page-report-manifest.json",
    }[artifact]
    return FileResponse(
        path=path,
        filename=safe_download_name(filename, fallback),
        media_type=media_type,
        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
    )
