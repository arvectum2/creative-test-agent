from fastapi import APIRouter, Request
from fastapi.responses import FileResponse

from src.modules.audit_log.service import write_audit_event
from src.modules.data_review_reports.schemas import (
    DataReviewReportResponse,
    GenerateDataReviewReportRequest,
)
from src.modules.data_review_reports.service import (
    data_review_report_path,
    generate_data_review_report,
    get_data_review_report,
    get_latest_data_review_report,
)
from src.shared.errors import AppError
from src.shared.security.auth import get_current_user_from_request

router = APIRouter(tags=["data-review-reports"])


def _user_id(request: Request) -> str | None:
    try:
        user = get_current_user_from_request(request)
    except Exception:
        return None
    return user.get("user_id") or user.get("id")


@router.post(
    "/data-quality-runs/{data_quality_run_id}/data-review-report",
    response_model=DataReviewReportResponse,
)
def post_data_review_report(
    data_quality_run_id: str,
    body: GenerateDataReviewReportRequest,
    request: Request,
):
    result = generate_data_review_report(
        data_quality_run_id,
        prediction_readiness_run_id=body.prediction_readiness_run_id,
        quantitative_study_id=body.quantitative_study_id,
        force=body.force,
        created_by_user_id=_user_id(request),
    )
    write_audit_event(
        "data_review_report_generated",
        "data_review_report_run",
        result.id,
        {
            "data_quality_run_id": data_quality_run_id,
            "prediction_readiness_run_id": result.prediction_readiness_run_id,
            "quantitative_study_id": result.quantitative_study_id,
            "sha256": result.sha256,
            "file_size_bytes": result.file_size_bytes,
            "sheet_count": result.sheet_count,
            "force": body.force,
        },
    )
    return result


@router.get(
    "/data-quality-runs/{data_quality_run_id}/data-review-report/latest",
    response_model=DataReviewReportResponse,
)
def get_latest_report(data_quality_run_id: str):
    result = get_latest_data_review_report(data_quality_run_id)
    if result is None:
        raise AppError("data_review_report_not_found", "Data-review report not found", 404)
    return result


@router.get("/data-review-reports/{report_id}", response_model=DataReviewReportResponse)
def get_report(report_id: str):
    result = get_data_review_report(report_id)
    if result is None:
        raise AppError("data_review_report_not_found", "Data-review report not found", 404)
    return result


@router.get("/data-review-reports/{report_id}/download")
def download_report(report_id: str):
    path, filename = data_review_report_path(report_id)
    return FileResponse(
        path=path,
        filename=filename,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
