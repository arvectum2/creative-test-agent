from fastapi import APIRouter, Request

from src.modules.audit_log.service import write_audit_event
from src.modules.prediction_readiness.schemas import (
    GeneratePredictionReadinessRequest,
    PredictionReadinessResultResponse,
)
from src.modules.prediction_readiness.service import (
    evaluate_prediction_readiness,
    get_latest_prediction_readiness,
    get_prediction_readiness_run,
)
from src.shared.errors import AppError
from src.shared.security.auth import get_optional_user_id

router = APIRouter(tags=["prediction-readiness"])


@router.post(
    "/data-quality-runs/{data_quality_run_id}/prediction-readiness",
    response_model=PredictionReadinessResultResponse,
)
def post_prediction_readiness(
    data_quality_run_id: str,
    body: GeneratePredictionReadinessRequest,
    request: Request,
):
    result = evaluate_prediction_readiness(
        data_quality_run_id,
        force=body.force,
        created_by_user_id=get_optional_user_id(request),
    )
    write_audit_event(
        "prediction_readiness_evaluated",
        "prediction_readiness_run",
        result.run.id,
        {
            "data_quality_run_id": data_quality_run_id,
            "overall_status": result.run.overall_status,
            "ready_count": result.run.ready_count,
            "degraded_count": result.run.degraded_count,
            "unavailable_count": result.run.unavailable_count,
            "force": body.force,
            "prediction_generated": False,
        },
    )
    return result


@router.get(
    "/data-quality-runs/{data_quality_run_id}/prediction-readiness/latest",
    response_model=PredictionReadinessResultResponse,
)
def get_latest_readiness(data_quality_run_id: str):
    result = get_latest_prediction_readiness(data_quality_run_id)
    if result is None:
        raise AppError("prediction_readiness_run_not_found", "Prediction-readiness run not found", 404)
    return result


@router.get(
    "/prediction-readiness-runs/{run_id}",
    response_model=PredictionReadinessResultResponse,
)
def get_readiness_run(run_id: str):
    result = get_prediction_readiness_run(run_id)
    if result is None:
        raise AppError("prediction_readiness_run_not_found", "Prediction-readiness run not found", 404)
    return result
