from fastapi import APIRouter, Query, Request

from src.modules.audit_log.service import write_audit_event
from src.modules.clarifications.lifecycle import record_clarification_response
from src.modules.clarifications.schemas import (
    ClarificationQuestionPageResponse,
    ClarificationQuestionResponse,
    ClarificationResponsePageResponse,
    ClarificationResultResponse,
    GenerateClarificationsRequest,
    SubmitClarificationResponseRequest,
)
from src.modules.clarifications.service import (
    generate_clarifications,
    get_clarification_run,
    get_latest_clarifications,
    list_clarification_questions,
    list_clarification_responses,
)
from src.shared.errors import AppError
from src.shared.security.auth import get_optional_user_id

router = APIRouter(tags=["clarifications"])


@router.post(
    "/data-quality-runs/{data_quality_run_id}/clarifications",
    response_model=ClarificationResultResponse,
)
def post_clarifications(
    data_quality_run_id: str,
    body: GenerateClarificationsRequest,
    request: Request,
):
    result = generate_clarifications(
        data_quality_run_id,
        audience=body.audience,
        max_questions=body.max_questions,
        force=body.force,
        created_by_user_id=get_optional_user_id(request),
    )
    write_audit_event(
        "clarification_run_generated",
        "clarification_run",
        result.run.id,
        {
            "data_quality_run_id": data_quality_run_id,
            "audience": result.run.audience,
            "max_questions": result.run.max_questions,
            "question_count": result.run.question_count,
            "suppressed_question_count": result.run.suppressed_question_count,
            "force": body.force,
        },
    )
    return result


@router.get(
    "/data-quality-runs/{data_quality_run_id}/clarifications/latest",
    response_model=ClarificationResultResponse,
)
def get_latest_quality_clarifications(
    data_quality_run_id: str,
    audience: str = Query("client"),
):
    result = get_latest_clarifications(data_quality_run_id, audience=audience)
    if result is None:
        raise AppError("clarification_run_not_found", "Clarification run not found", 404)
    return result


@router.get(
    "/clarification-runs/{run_id}",
    response_model=ClarificationResultResponse,
)
def get_clarifications(run_id: str):
    result = get_clarification_run(run_id)
    if result is None:
        raise AppError("clarification_run_not_found", "Clarification run not found", 404)
    return result


@router.get(
    "/clarification-runs/{run_id}/questions",
    response_model=ClarificationQuestionPageResponse,
)
def get_questions(
    run_id: str,
    status: str | None = Query(None),
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
):
    return list_clarification_questions(
        run_id,
        status=status,
        offset=offset,
        limit=limit,
    )


@router.post(
    "/clarification-questions/{question_id}/responses",
    response_model=ClarificationQuestionResponse,
)
def post_clarification_response(
    question_id: str,
    body: SubmitClarificationResponseRequest,
    request: Request,
):
    result = record_clarification_response(
        question_id,
        body,
        responded_by_user_id=get_optional_user_id(request),
    )
    write_audit_event(
        "clarification_response_recorded",
        "clarification_question",
        question_id,
        {
            "clarification_run_id": result.clarification_run_id,
            "question_key": result.question_key,
            "resolution": result.status,
            "response_number": (
                result.latest_response.response_number if result.latest_response else None
            ),
            "automatic_mutation": False,
        },
    )
    return result


@router.get(
    "/clarification-questions/{question_id}/responses",
    response_model=ClarificationResponsePageResponse,
)
def get_clarification_responses(question_id: str):
    return list_clarification_responses(question_id)
