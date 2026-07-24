from __future__ import annotations

import hashlib
import math
import random
from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func

from src.modules.creative_assets.models import CreativeAsset
from src.modules.quantitative_surveys.models import (
    QuestionType,
    QuestionnaireStatus,
    QuantitativeAnswer,
    QuantitativeQuestion,
    QuantitativeQuestionnaire,
    QuantitativeResponse,
    QuantitativeStudy,
    ResponseSource,
    StudyStatus,
)
from src.modules.quantitative_surveys.schemas import (
    CreateQuestionnaireRequest,
    CreateStudyRequest,
    QuestionnaireResponse,
    QuestionResponse,
    SimulateStudyRequest,
    StudyResponse,
    StudyResultsResponse,
    SubmitStudyResponseRequest,
    SubmittedResponse,
)
from src.shared.db.repository import db_session, json_dumps, json_loads
from src.shared.errors import AppError

_ALLOWED_METRIC_KEYS = {
    "click_intent",
    "purchase_intent",
    "brand_recall",
    "brand_fit",
    "message_clarity",
    "relevance",
    "trust",
    "visual_appeal",
    "comprehension",
    "distinctiveness",
}
_ALLOWED_TYPES = {str(item) for item in QuestionType}
_ALLOWED_SOURCES = {str(item) for item in ResponseSource}


def create_questionnaire(
    request: CreateQuestionnaireRequest,
    *,
    created_by_user_id: str | None = None,
) -> QuestionnaireResponse:
    if not request.questions:
        raise AppError("questionnaire_requires_questions", "At least one quantitative question is required", 400)
    codes = [item.code.strip() for item in request.questions]
    if any(not code for code in codes) or len(codes) != len(set(codes)):
        raise AppError("duplicate_question_codes", "Question codes must be non-empty and unique", 400)
    for item in request.questions:
        _validate_question_config(item)

    with db_session() as db:
        version = (
            db.query(func.max(QuantitativeQuestionnaire.version))
            .filter(
                QuantitativeQuestionnaire.project_id == request.project_id,
                QuantitativeQuestionnaire.name == request.name.strip(),
            )
            .scalar()
            or 0
        ) + 1
        questionnaire = QuantitativeQuestionnaire(
            project_id=request.project_id,
            name=request.name.strip(),
            description=(request.description or "").strip() or None,
            version=version,
            status=QuestionnaireStatus.draft,
            locale=request.locale.strip() or "en",
            randomize_questions=request.randomize_questions,
            metadata_json=json_dumps(request.metadata),
            created_by_user_id=created_by_user_id,
        )
        db.add(questionnaire)
        db.flush()
        for position, config in enumerate(request.questions, start=1):
            db.add(
                QuantitativeQuestion(
                    questionnaire_id=questionnaire.id,
                    position=position,
                    code=config.code.strip(),
                    prompt=config.prompt.strip(),
                    question_type=config.question_type,
                    metric_key=config.metric_key,
                    required=config.required,
                    scale_min=config.scale_min,
                    scale_max=config.scale_max,
                    low_label=(config.low_label or "").strip() or None,
                    high_label=(config.high_label or "").strip() or None,
                    options_json=json_dumps(config.options),
                    reverse_scored=config.reverse_scored,
                )
            )
        db.flush()
        db.refresh(questionnaire)
        return _questionnaire_response(db, questionnaire)


def publish_questionnaire(questionnaire_id: str) -> QuestionnaireResponse:
    with db_session() as db:
        questionnaire = _require_questionnaire(db, questionnaire_id)
        if questionnaire.status == QuestionnaireStatus.archived:
            raise AppError("questionnaire_archived", "Archived questionnaire cannot be published", 409)
        if questionnaire.status != QuestionnaireStatus.published:
            questionnaire.status = QuestionnaireStatus.published
            questionnaire.published_at = datetime.now(timezone.utc)
            db.flush()
        return _questionnaire_response(db, questionnaire)


def get_questionnaire(questionnaire_id: str) -> QuestionnaireResponse | None:
    with db_session() as db:
        questionnaire = (
            db.query(QuantitativeQuestionnaire)
            .filter(QuantitativeQuestionnaire.id == questionnaire_id)
            .first()
        )
        return _questionnaire_response(db, questionnaire) if questionnaire else None


def list_questionnaires(project_id: str) -> list[QuestionnaireResponse]:
    with db_session() as db:
        items = (
            db.query(QuantitativeQuestionnaire)
            .filter(QuantitativeQuestionnaire.project_id == project_id)
            .order_by(
                QuantitativeQuestionnaire.name.asc(),
                QuantitativeQuestionnaire.version.desc(),
            )
            .all()
        )
        return [_questionnaire_response(db, item) for item in items]


def create_study(
    request: CreateStudyRequest,
    *,
    created_by_user_id: str | None = None,
) -> StudyResponse:
    creative_ids = list(dict.fromkeys(item.strip() for item in request.creative_asset_ids if item.strip()))
    if not creative_ids:
        raise AppError("study_requires_creatives", "At least one creative asset is required", 400)
    with db_session() as db:
        questionnaire = _require_questionnaire(db, request.questionnaire_id)
        if questionnaire.project_id != request.project_id:
            raise AppError("questionnaire_project_mismatch", "Questionnaire belongs to another project", 409)
        if questionnaire.status != QuestionnaireStatus.published:
            raise AppError("questionnaire_not_published", "Study requires a published questionnaire", 409)
        found = {
            item.id
            for item in db.query(CreativeAsset)
            .filter(
                CreativeAsset.project_id == request.project_id,
                CreativeAsset.id.in_(creative_ids),
            )
            .all()
        }
        missing = [item for item in creative_ids if item not in found]
        if missing:
            raise AppError(
                "creative_assets_not_found",
                "Some creative assets do not belong to the project",
                404,
                details={"creative_asset_ids": missing},
            )
        study = QuantitativeStudy(
            project_id=request.project_id,
            questionnaire_id=questionnaire.id,
            name=request.name.strip(),
            status=StudyStatus.draft,
            target_response_count=request.target_response_count,
            response_count=0,
            creative_asset_ids_json=json_dumps(creative_ids),
            randomize_creatives=request.randomize_creatives,
            seed=request.seed,
            metadata_json=json_dumps(request.metadata),
            created_by_user_id=created_by_user_id,
        )
        db.add(study)
        db.flush()
        db.refresh(study)
        return _study_response(study)


def open_study(study_id: str) -> StudyResponse:
    with db_session() as db:
        study = _require_study(db, study_id)
        if study.status == StudyStatus.closed:
            raise AppError("study_closed", "Closed study cannot be reopened in place", 409)
        if study.status != StudyStatus.open:
            study.status = StudyStatus.open
            study.opened_at = datetime.now(timezone.utc)
            db.flush()
        return _study_response(study)


def close_study(study_id: str) -> StudyResponse:
    with db_session() as db:
        study = _require_study(db, study_id)
        study.status = StudyStatus.closed
        study.closed_at = datetime.now(timezone.utc)
        _refresh_response_count(db, study)
        db.flush()
        return _study_response(study)


def get_study(study_id: str) -> StudyResponse | None:
    with db_session() as db:
        study = db.query(QuantitativeStudy).filter(QuantitativeStudy.id == study_id).first()
        return _study_response(study) if study else None


def submit_response(
    study_id: str,
    request: SubmitStudyResponseRequest,
) -> SubmittedResponse:
    source = request.source.strip().lower()
    if source not in _ALLOWED_SOURCES:
        raise AppError("invalid_response_source", "Unknown quantitative response source", 400)
    if source == ResponseSource.synthetic and not request.generation_provenance:
        raise AppError(
            "synthetic_response_requires_provenance",
            "Synthetic responses require explicit generation provenance",
            400,
        )
    respondent_key = request.respondent_key.strip()
    if not respondent_key:
        raise AppError("respondent_key_required", "A pseudonymous respondent key is required", 400)

    with db_session() as db:
        study = _require_study(db, study_id)
        if study.status != StudyStatus.open:
            raise AppError("study_not_open", "Responses can only be submitted to an open study", 409)
        creative_ids = _safe_list(json_loads(study.creative_asset_ids_json))
        if request.creative_asset_id not in creative_ids:
            raise AppError("creative_not_in_study", "Creative asset is not part of this study", 409)
        questions = _questions(db, study.questionnaire_id)
        answers_by_code = {item.question_code: item.value for item in request.answers}
        duplicate_codes = [item.question_code for item in request.answers]
        if len(duplicate_codes) != len(set(duplicate_codes)):
            raise AppError("duplicate_answers", "Each question may be answered once", 400)
        unknown = sorted(set(answers_by_code) - {item.code for item in questions})
        if unknown:
            raise AppError("unknown_question_code", "Response contains unknown question codes", 400, details={"codes": unknown})
        missing_required = [item.code for item in questions if item.required and item.code not in answers_by_code]
        if missing_required:
            raise AppError("required_answers_missing", "Required quantitative answers are missing", 400, details={"codes": missing_required})

        respondent_hash = hashlib.sha256(f"{study.id}:{respondent_key}".encode("utf-8")).hexdigest()
        existing = (
            db.query(QuantitativeResponse)
            .filter(
                QuantitativeResponse.study_id == study.id,
                QuantitativeResponse.respondent_hash == respondent_hash,
            )
            .first()
        )
        if existing is not None:
            raise AppError("duplicate_study_response", "Respondent already submitted a response to this study", 409)

        response = QuantitativeResponse(
            study_id=study.id,
            respondent_hash=respondent_hash,
            creative_asset_id=request.creative_asset_id,
            source=source,
            generation_provenance_json=json_dumps(request.generation_provenance),
        )
        db.add(response)
        db.flush()
        for question in questions:
            if question.code not in answers_by_code:
                continue
            numeric, boolean, selected = _validate_answer(question, answers_by_code[question.code])
            db.add(
                QuantitativeAnswer(
                    response_id=response.id,
                    question_id=question.id,
                    numeric_value=numeric,
                    boolean_value=boolean,
                    selected_values_json=json_dumps(selected) if selected is not None else None,
                )
            )
        db.flush()
        _refresh_response_count(db, study)
        db.flush()
        db.refresh(response)
        return _submitted_response(response)


def simulate_study(study_id: str, request: SimulateStudyRequest) -> list[SubmittedResponse]:
    with db_session() as db:
        study = _require_study(db, study_id)
        if study.status == StudyStatus.draft:
            study.status = StudyStatus.open
            study.opened_at = datetime.now(timezone.utc)
        if study.status != StudyStatus.open:
            raise AppError("study_not_open", "Synthetic responses require an open study", 409)
        creative_ids = _safe_list(json_loads(study.creative_asset_ids_json))
        questions = _questions(db, study.questionnaire_id)
        seed = request.seed if request.seed is not None else study.seed
        rng = random.Random(seed)
        created: list[QuantitativeResponse] = []
        existing_count = (
            db.query(func.count(QuantitativeResponse.id))
            .filter(QuantitativeResponse.study_id == study.id)
            .scalar()
            or 0
        )
        for index in range(request.respondent_count):
            ordinal = existing_count + index
            creative_id = creative_ids[ordinal % len(creative_ids)]
            if study.randomize_creatives:
                creative_id = creative_ids[rng.randrange(len(creative_ids))]
            effect = max(-1.0, min(1.0, float(request.creative_effects.get(creative_id, 0.0))))
            respondent_hash = hashlib.sha256(
                f"synthetic:{study.id}:{seed}:{ordinal}".encode("utf-8")
            ).hexdigest()
            response = QuantitativeResponse(
                study_id=study.id,
                respondent_hash=respondent_hash,
                creative_asset_id=creative_id,
                source=ResponseSource.synthetic,
                generation_provenance_json=json_dumps(
                    {
                        "generator": "deterministic-quantitative-simulator",
                        "version": "1.0.0",
                        "seed": seed,
                        "ordinal": ordinal,
                        "creative_effect": effect,
                        "not_a_real_person": True,
                    }
                ),
            )
            db.add(response)
            db.flush()
            for question in questions:
                numeric, boolean, selected = _simulate_answer(rng, question, effect)
                db.add(
                    QuantitativeAnswer(
                        response_id=response.id,
                        question_id=question.id,
                        numeric_value=numeric,
                        boolean_value=boolean,
                        selected_values_json=json_dumps(selected) if selected is not None else None,
                    )
                )
            created.append(response)
        db.flush()
        _refresh_response_count(db, study)
        db.flush()
        return [_submitted_response(item) for item in created]


def study_results(study_id: str) -> StudyResultsResponse:
    with db_session() as db:
        study = _require_study(db, study_id)
        questionnaire = _require_questionnaire(db, study.questionnaire_id)
        questions = _questions(db, questionnaire.id)
        responses = (
            db.query(QuantitativeResponse)
            .filter(QuantitativeResponse.study_id == study.id)
            .order_by(QuantitativeResponse.completed_at.asc(), QuantitativeResponse.id.asc())
            .all()
        )
        response_by_id = {item.id: item for item in responses}
        answer_rows = (
            db.query(QuantitativeAnswer)
            .filter(QuantitativeAnswer.response_id.in_(list(response_by_id)))
            .all()
            if response_by_id
            else []
        )
        question_by_id = {item.id: item for item in questions}
        source_counts = Counter(item.source for item in responses)
        by_creative: dict[str, dict[str, Any]] = {
            creative_id: {"response_count": 0, "metrics": {}}
            for creative_id in _safe_list(json_loads(study.creative_asset_ids_json))
        }
        for response in responses:
            by_creative.setdefault(response.creative_asset_id, {"response_count": 0, "metrics": {}})
            by_creative[response.creative_asset_id]["response_count"] += 1

        grouped_numeric: dict[tuple[str, str], list[float]] = defaultdict(list)
        grouped_distribution: dict[tuple[str, str], Counter[str]] = defaultdict(Counter)
        for answer in answer_rows:
            response = response_by_id[answer.response_id]
            question = question_by_id[answer.question_id]
            key = (response.creative_asset_id, question.id)
            if answer.numeric_value is not None:
                grouped_numeric[key].append(float(answer.numeric_value))
            elif answer.boolean_value is not None:
                grouped_distribution[key][str(bool(answer.boolean_value)).lower()] += 1
            else:
                selected = _safe_list(json_loads(answer.selected_values_json))
                for value in selected:
                    grouped_distribution[key][str(value)] += 1

        question_results: list[dict[str, Any]] = []
        for question in questions:
            creative_results = {}
            for creative_id in by_creative:
                values = grouped_numeric.get((creative_id, question.id), [])
                distribution = grouped_distribution.get((creative_id, question.id), Counter())
                result: dict[str, Any] = {
                    "response_count": len(values) if values else sum(distribution.values()),
                }
                if values:
                    result.update(
                        {
                            "mean": round(sum(values) / len(values), 6),
                            "min": min(values),
                            "max": max(values),
                        }
                    )
                if distribution:
                    result["distribution"] = dict(sorted(distribution.items()))
                creative_results[creative_id] = result
                by_creative[creative_id]["metrics"][question.metric_key] = result
            question_results.append(
                {
                    "question_id": question.id,
                    "code": question.code,
                    "metric_key": question.metric_key,
                    "question_type": question.question_type,
                    "by_creative": creative_results,
                }
            )

        _refresh_response_count(db, study)
        return StudyResultsResponse(
            study=_study_response(study),
            questionnaire=_questionnaire_response(db, questionnaire),
            total_responses=len(responses),
            source_counts=dict(source_counts),
            metric_keys=sorted({item.metric_key for item in questions}),
            by_creative=by_creative,
            question_results=question_results,
            interpretation_notes=[
                "Synthetic responses are labelled and are not observations from real people.",
                "Questionnaire scores are proxy measures and are not observed campaign lift.",
                "Results must be interpreted with the declared scale, sample source and response count.",
            ],
        )


def project_survey_evidence(db, project_id: str) -> dict[str, Any]:
    studies = (
        db.query(QuantitativeStudy)
        .filter(QuantitativeStudy.project_id == project_id)
        .order_by(QuantitativeStudy.created_at.desc(), QuantitativeStudy.id.desc())
        .all()
    )
    for study in studies:
        questions = _questions(db, study.questionnaire_id)
        metric_keys = sorted({item.metric_key for item in questions})
        if study.response_count:
            return {
                "study_id": study.id,
                "status": study.status,
                "response_count": study.response_count,
                "target_response_count": study.target_response_count,
                "metric_keys": metric_keys,
                "completed_target": study.response_count >= study.target_response_count,
                "closed": study.status == StudyStatus.closed,
            }
    published = (
        db.query(QuantitativeQuestionnaire)
        .filter(
            QuantitativeQuestionnaire.project_id == project_id,
            QuantitativeQuestionnaire.status == QuestionnaireStatus.published,
        )
        .order_by(QuantitativeQuestionnaire.created_at.desc())
        .first()
    )
    return {
        "study_id": None,
        "status": None,
        "response_count": 0,
        "target_response_count": 0,
        "metric_keys": sorted({item.metric_key for item in _questions(db, published.id)}) if published else [],
        "completed_target": False,
        "closed": False,
        "published_questionnaire_available": published is not None,
    }


def _validate_question_config(config) -> None:
    if config.question_type not in _ALLOWED_TYPES:
        raise AppError("unsupported_question_type", "Only quantitative question types are supported", 400)
    if config.metric_key not in _ALLOWED_METRIC_KEYS:
        raise AppError("unsupported_metric_key", "Question metric key is not supported", 400)
    if not config.prompt.strip():
        raise AppError("question_prompt_required", "Question prompt is required", 400)
    if config.question_type in {QuestionType.likert, QuestionType.numeric}:
        if config.scale_min is None or config.scale_max is None or config.scale_max <= config.scale_min:
            raise AppError("invalid_numeric_scale", "Numeric questions require scale_min < scale_max", 400)
        if config.question_type == QuestionType.likert:
            if not float(config.scale_min).is_integer() or not float(config.scale_max).is_integer():
                raise AppError("invalid_likert_scale", "Likert bounds must be integers", 400)
            if config.scale_max - config.scale_min < 1 or config.scale_max - config.scale_min > 10:
                raise AppError("invalid_likert_scale", "Likert scale must contain 2 to 11 points", 400)
    elif config.question_type in {QuestionType.single_choice, QuestionType.multiple_choice}:
        options = [item.strip() for item in config.options if item.strip()]
        if len(options) < 2 or len(options) != len(set(options)):
            raise AppError("invalid_question_options", "Choice questions require at least two unique options", 400)
    elif config.options:
        raise AppError("unexpected_question_options", "Options are only valid for choice questions", 400)


def _validate_answer(question, value):
    options = _safe_list(json_loads(question.options_json))
    if question.question_type in {QuestionType.likert, QuestionType.numeric}:
        if isinstance(value, bool):
            raise AppError("invalid_numeric_answer", "Numeric answer cannot be boolean", 400)
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            raise AppError("invalid_numeric_answer", "Expected a numeric answer", 400)
        if numeric < question.scale_min or numeric > question.scale_max:
            raise AppError("numeric_answer_out_of_range", "Numeric answer is outside the configured scale", 400)
        return numeric, None, None
    if question.question_type == QuestionType.yes_no:
        if not isinstance(value, bool):
            raise AppError("invalid_boolean_answer", "Expected a boolean answer", 400)
        return None, value, None
    if question.question_type == QuestionType.single_choice:
        if not isinstance(value, str) or value not in options:
            raise AppError("invalid_choice_answer", "Answer is not a configured option", 400)
        return None, None, [value]
    if question.question_type == QuestionType.multiple_choice:
        if not isinstance(value, list) or not value or any(item not in options for item in value):
            raise AppError("invalid_multiple_choice_answer", "Answers must be configured options", 400)
        if len(value) != len(set(value)):
            raise AppError("duplicate_multiple_choice_answer", "Multiple-choice values must be unique", 400)
        return None, None, value
    raise AppError("unsupported_question_type", "Unsupported quantitative question type", 400)


def _simulate_answer(rng, question, effect):
    options = _safe_list(json_loads(question.options_json))
    if question.question_type in {QuestionType.likert, QuestionType.numeric}:
        low = float(question.scale_min)
        high = float(question.scale_max)
        midpoint = (low + high) / 2
        value = midpoint + effect * (high - low) / 3 + rng.gauss(0, (high - low) / 6)
        value = max(low, min(high, value))
        if question.question_type == QuestionType.likert:
            value = float(round(value))
        if question.reverse_scored:
            value = low + high - value
        return value, None, None
    if question.question_type == QuestionType.yes_no:
        probability = max(0.05, min(0.95, 0.5 + effect * 0.3))
        return None, rng.random() < probability, None
    if question.question_type == QuestionType.single_choice:
        index = rng.randrange(len(options))
        if effect > 0.4:
            index = len(options) - 1
        elif effect < -0.4:
            index = 0
        return None, None, [options[index]]
    count = 1 if len(options) == 2 else rng.randint(1, min(2, len(options)))
    return None, None, rng.sample(options, count)


def _require_questionnaire(db, questionnaire_id):
    item = db.query(QuantitativeQuestionnaire).filter(QuantitativeQuestionnaire.id == questionnaire_id).first()
    if item is None:
        raise AppError("questionnaire_not_found", "Quantitative questionnaire not found", 404)
    return item


def _require_study(db, study_id):
    item = db.query(QuantitativeStudy).filter(QuantitativeStudy.id == study_id).first()
    if item is None:
        raise AppError("quantitative_study_not_found", "Quantitative study not found", 404)
    return item


def _questions(db, questionnaire_id):
    return (
        db.query(QuantitativeQuestion)
        .filter(QuantitativeQuestion.questionnaire_id == questionnaire_id)
        .order_by(QuantitativeQuestion.position.asc(), QuantitativeQuestion.id.asc())
        .all()
    )


def _refresh_response_count(db, study):
    db.flush()
    study.response_count = (
        db.query(func.count(QuantitativeResponse.id))
        .filter(QuantitativeResponse.study_id == study.id)
        .scalar()
        or 0
    )


def _questionnaire_response(db, questionnaire):
    metadata = json_loads(questionnaire.metadata_json)
    return QuestionnaireResponse(
        id=questionnaire.id,
        project_id=questionnaire.project_id,
        name=questionnaire.name,
        description=questionnaire.description,
        version=questionnaire.version,
        status=questionnaire.status,
        locale=questionnaire.locale,
        randomize_questions=questionnaire.randomize_questions,
        metadata=metadata if isinstance(metadata, dict) else {},
        published_at=questionnaire.published_at,
        created_by_user_id=questionnaire.created_by_user_id,
        created_at=questionnaire.created_at,
        questions=[_question_response(item) for item in _questions(db, questionnaire.id)],
    )


def _question_response(question):
    return QuestionResponse(
        id=question.id,
        questionnaire_id=question.questionnaire_id,
        position=question.position,
        code=question.code,
        prompt=question.prompt,
        question_type=question.question_type,
        metric_key=question.metric_key,
        required=question.required,
        scale_min=question.scale_min,
        scale_max=question.scale_max,
        low_label=question.low_label,
        high_label=question.high_label,
        options=_safe_list(json_loads(question.options_json)),
        reverse_scored=question.reverse_scored,
    )


def _study_response(study):
    metadata = json_loads(study.metadata_json)
    return StudyResponse(
        id=study.id,
        project_id=study.project_id,
        questionnaire_id=study.questionnaire_id,
        name=study.name,
        status=study.status,
        target_response_count=study.target_response_count,
        response_count=study.response_count,
        creative_asset_ids=_safe_list(json_loads(study.creative_asset_ids_json)),
        randomize_creatives=study.randomize_creatives,
        seed=study.seed,
        metadata=metadata if isinstance(metadata, dict) else {},
        opened_at=study.opened_at,
        closed_at=study.closed_at,
        created_by_user_id=study.created_by_user_id,
        created_at=study.created_at,
    )


def _submitted_response(response):
    return SubmittedResponse(
        id=response.id,
        study_id=response.study_id,
        respondent_hash=response.respondent_hash,
        creative_asset_id=response.creative_asset_id,
        source=response.source,
        completed_at=response.completed_at,
    )


def _safe_list(value):
    return value if isinstance(value, list) else []
