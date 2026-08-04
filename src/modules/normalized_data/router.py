from fastapi import APIRouter, Query, Request

from src.modules.audit_log.service import write_audit_event
from src.modules.normalized_data.schemas import (
    AudienceSegmentResponse,
    CampaignResponse,
    CreativeRecordResponse,
    NormalizeTableRequest,
    NormalizationResultResponse,
    NormalizationRunResponse,
    NormalizedSourceRowPageResponse,
    PerformanceObservationResponse,
    PlacementResponse,
    PlatformResponse,
)
from src.modules.normalized_data.service import (
    get_latest_normalization,
    get_normalization_run,
    list_audience_segments,
    list_campaigns,
    list_creatives,
    list_normalized_rows,
    list_performance_observations,
    list_placements,
    list_platforms,
    normalize_source_table,
)
from src.shared.errors import AppError
from src.shared.security.auth import get_optional_user_id

router = APIRouter(tags=["normalized-data"])


@router.post(
    "/import-sessions/{import_session_id}/files/{file_id}/tables/{table_id}/normalize",
    response_model=NormalizationResultResponse,
)
def post_normalize_source_table(
    import_session_id: str,
    file_id: str,
    table_id: str,
    body: NormalizeTableRequest,
    request: Request,
):
    result = normalize_source_table(
        import_session_id,
        file_id,
        table_id,
        force=body.force,
        created_by_user_id=get_optional_user_id(request),
    )
    write_audit_event(
        "source_table_normalized",
        "source_table",
        table_id,
        {
            "import_session_id": import_session_id,
            "source_file_id": file_id,
            "normalization_run_id": result.run.id,
            "normalizer_version": result.run.normalizer_version,
            "mapping_fingerprint": result.run.mapping_fingerprint,
            "force": body.force,
            "source_row_count": result.run.source_row_count,
            "normalized_row_count": result.run.normalized_row_count,
            "partial_row_count": result.run.partial_row_count,
            "skipped_row_count": result.run.skipped_row_count,
        },
    )
    return result


@router.get(
    "/import-sessions/{import_session_id}/files/{file_id}/tables/{table_id}/normalization",
    response_model=NormalizationResultResponse,
)
def get_source_table_normalization(import_session_id: str, file_id: str, table_id: str):
    result = get_latest_normalization(import_session_id, file_id, table_id)
    if result is None:
        raise AppError("normalization_run_not_found", "Normalization run not found", 404)
    return result


@router.get("/normalization-runs/{run_id}", response_model=NormalizationRunResponse)
def get_normalization_run_by_id(run_id: str):
    result = get_normalization_run(run_id)
    if result is None:
        raise AppError("normalization_run_not_found", "Normalization run not found", 404)
    return result


@router.get(
    "/normalization-runs/{run_id}/rows",
    response_model=NormalizedSourceRowPageResponse,
)
def get_normalized_rows(
    run_id: str,
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
):
    total, rows = list_normalized_rows(run_id, offset=offset, limit=limit)
    return NormalizedSourceRowPageResponse(
        normalization_run_id=run_id,
        offset=offset,
        limit=limit,
        total=total,
        rows=rows,
    )


@router.get("/normalization-runs/{run_id}/campaigns", response_model=list[CampaignResponse])
def get_normalized_campaigns(run_id: str):
    return list_campaigns(run_id)


@router.get(
    "/normalization-runs/{run_id}/creatives",
    response_model=list[CreativeRecordResponse],
)
def get_normalized_creatives(run_id: str):
    return list_creatives(run_id)


@router.get("/normalization-runs/{run_id}/platforms", response_model=list[PlatformResponse])
def get_normalized_platforms(run_id: str):
    return list_platforms(run_id)


@router.get(
    "/normalization-runs/{run_id}/audience-segments",
    response_model=list[AudienceSegmentResponse],
)
def get_normalized_audience_segments(run_id: str):
    return list_audience_segments(run_id)


@router.get("/normalization-runs/{run_id}/placements", response_model=list[PlacementResponse])
def get_normalized_placements(run_id: str):
    return list_placements(run_id)


@router.get(
    "/normalization-runs/{run_id}/performance-observations",
    response_model=list[PerformanceObservationResponse],
)
def get_normalized_performance_observations(run_id: str):
    return list_performance_observations(run_id)
