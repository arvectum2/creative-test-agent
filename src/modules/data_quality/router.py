from fastapi import APIRouter, Query, Request

from src.modules.audit_log.service import write_audit_event
from src.modules.data_quality.schemas import (
    DataQualityIssuePageResponse,
    DataQualityResultResponse,
    GenerateDataQualityRequest,
)
from src.modules.data_quality.service import (
    generate_data_quality_report,
    get_data_quality_report,
    get_latest_data_quality_report,
    list_data_quality_issues,
)
from src.shared.errors import AppError
from src.shared.security.auth import get_optional_user_id

router = APIRouter(tags=["data-quality"])


@router.post(
    "/import-sessions/{import_session_id}/files/{file_id}/tables/{table_id}/data-quality",
    response_model=DataQualityResultResponse,
)
def post_data_quality_report(
    import_session_id: str,
    file_id: str,
    table_id: str,
    body: GenerateDataQualityRequest,
    request: Request,
):
    result = generate_data_quality_report(
        import_session_id,
        file_id,
        table_id,
        force=body.force,
        created_by_user_id=get_optional_user_id(request),
    )
    write_audit_event(
        "data_quality_report_generated",
        "data_quality_run",
        result.run.id,
        {
            "import_session_id": import_session_id,
            "source_file_id": file_id,
            "source_table_id": table_id,
            "normalization_run_id": result.run.normalization_run_id,
            "force": body.force,
            "overall_status": result.run.overall_status,
            "issue_counts": {
                "info": result.run.info_issue_count,
                "warning": result.run.warning_issue_count,
                "blocking": result.run.blocking_issue_count,
            },
        },
    )
    return result


@router.get(
    "/import-sessions/{import_session_id}/files/{file_id}/tables/{table_id}/data-quality",
    response_model=DataQualityResultResponse,
)
def get_latest_table_data_quality(
    import_session_id: str,
    file_id: str,
    table_id: str,
):
    result = get_latest_data_quality_report(import_session_id, file_id, table_id)
    if result is None:
        raise AppError("data_quality_run_not_found", "Data-quality run not found", 404)
    return result


@router.get("/data-quality-runs/{run_id}", response_model=DataQualityResultResponse)
def get_data_quality_run(run_id: str):
    result = get_data_quality_report(run_id)
    if result is None:
        raise AppError("data_quality_run_not_found", "Data-quality run not found", 404)
    return result


@router.get(
    "/data-quality-runs/{run_id}/issues",
    response_model=DataQualityIssuePageResponse,
)
def get_data_quality_issues(
    run_id: str,
    category: str | None = Query(None),
    severity: str | None = Query(None),
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
):
    return list_data_quality_issues(
        run_id,
        category=category,
        severity=severity,
        offset=offset,
        limit=limit,
    )
