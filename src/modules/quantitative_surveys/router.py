from fastapi import APIRouter, Query, Request

from src.modules.audit_log.service import write_audit_event
from src.modules.quantitative_surveys.schemas import (
    CreateQuestionnaireRequest,
    CreateStudyRequest,
    QuestionnaireResponse,
    SimulateStudyRequest,
    StudyResponse,
    StudyResultsResponse,
    SubmitStudyResponseRequest,
    SubmittedResponse,
)
from src.modules.quantitative_surveys.service import (
    close_study,
    create_questionnaire,
    create_study,
    get_questionnaire,
    get_study,
    list_questionnaires,
    open_study,
    publish_questionnaire,
    simulate_study,
    study_results,
    submit_response,
)
from src.shared.errors import AppError
from src.shared.security.auth import get_optional_user_id

router = APIRouter(tags=["quantitative-surveys"])


@router.post("/quantitative-questionnaires", response_model=QuestionnaireResponse)
def post_questionnaire(body: CreateQuestionnaireRequest, request: Request):
    result = create_questionnaire(body, created_by_user_id=get_optional_user_id(request))
    write_audit_event(
        "quantitative_questionnaire_created",
        "quantitative_questionnaire",
        result.id,
        {"project_id": result.project_id, "version": result.version, "question_count": len(result.questions)},
    )
    return result


@router.post("/quantitative-questionnaires/{questionnaire_id}/publish", response_model=QuestionnaireResponse)
def post_publish_questionnaire(questionnaire_id: str):
    result = publish_questionnaire(questionnaire_id)
    write_audit_event(
        "quantitative_questionnaire_published",
        "quantitative_questionnaire",
        result.id,
        {"project_id": result.project_id, "version": result.version},
    )
    return result


@router.get("/quantitative-questionnaires/{questionnaire_id}", response_model=QuestionnaireResponse)
def get_questionnaire_route(questionnaire_id: str):
    result = get_questionnaire(questionnaire_id)
    if result is None:
        raise AppError("questionnaire_not_found", "Quantitative questionnaire not found", 404)
    return result


@router.get("/quantitative-questionnaires", response_model=list[QuestionnaireResponse])
def list_questionnaires_route(project_id: str = Query(...)):
    return list_questionnaires(project_id)


@router.post("/quantitative-studies", response_model=StudyResponse)
def post_study(body: CreateStudyRequest, request: Request):
    result = create_study(body, created_by_user_id=get_optional_user_id(request))
    write_audit_event(
        "quantitative_study_created",
        "quantitative_study",
        result.id,
        {"project_id": result.project_id, "questionnaire_id": result.questionnaire_id, "creative_count": len(result.creative_asset_ids)},
    )
    return result


@router.get("/quantitative-studies/{study_id}", response_model=StudyResponse)
def get_study_route(study_id: str):
    result = get_study(study_id)
    if result is None:
        raise AppError("quantitative_study_not_found", "Quantitative study not found", 404)
    return result


@router.post("/quantitative-studies/{study_id}/open", response_model=StudyResponse)
def post_open_study(study_id: str):
    result = open_study(study_id)
    write_audit_event("quantitative_study_opened", "quantitative_study", result.id, {})
    return result


@router.post("/quantitative-studies/{study_id}/close", response_model=StudyResponse)
def post_close_study(study_id: str):
    result = close_study(study_id)
    write_audit_event(
        "quantitative_study_closed",
        "quantitative_study",
        result.id,
        {"response_count": result.response_count, "target_response_count": result.target_response_count},
    )
    return result


@router.post("/quantitative-studies/{study_id}/responses", response_model=SubmittedResponse)
def post_study_response(study_id: str, body: SubmitStudyResponseRequest):
    result = submit_response(study_id, body)
    write_audit_event(
        "quantitative_response_recorded",
        "quantitative_response",
        result.id,
        {"study_id": study_id, "source": result.source, "creative_asset_id": result.creative_asset_id},
    )
    return result


@router.post("/quantitative-studies/{study_id}/simulate", response_model=list[SubmittedResponse])
def post_simulate_study(study_id: str, body: SimulateStudyRequest):
    result = simulate_study(study_id, body)
    write_audit_event(
        "quantitative_study_simulated",
        "quantitative_study",
        study_id,
        {"response_count": len(result), "seed": body.seed, "not_real_people": True},
    )
    return result


@router.get("/quantitative-studies/{study_id}/results", response_model=StudyResultsResponse)
def get_study_results(study_id: str):
    return study_results(study_id)
