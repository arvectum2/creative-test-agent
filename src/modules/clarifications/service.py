from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func

from src.modules.clarifications.candidate_builder import (
    ClarificationCandidate,
    build_candidates,
    priority_for_score,
)
from src.modules.clarifications.models import (
    ClarificationAnswerType,
    ClarificationAudience,
    ClarificationQuestion,
    ClarificationQuestionStatus,
    ClarificationResponse,
    ClarificationRun,
    ClarificationRunStatus,
)
from src.modules.clarifications.schemas import (
    ClarificationQuestionPageResponse,
    ClarificationQuestionResponse,
    ClarificationResponsePageResponse,
    ClarificationResponseResponse,
    ClarificationResultResponse,
    ClarificationRunResponse,
    SubmitClarificationResponseRequest,
)
from src.modules.data_quality.models import DataQualityIssue, DataQualityRun, DataQualityRunStatus
from src.modules.import_sessions.models import SourceColumn, SourceTable
from src.modules.mapping_engine.models import ColumnMapping
from src.shared.db.repository import db_session, json_dumps, json_loads
from src.shared.errors import AppError

GENERATOR_NAME = "progressive-clarification-generator"
GENERATOR_VERSION = "1.0.0"
_TERMINAL_STATUSES = {
    ClarificationQuestionStatus.answered,
    ClarificationQuestionStatus.not_available,
    ClarificationQuestionStatus.not_applicable,
}
_ALLOWED_RESOLUTIONS = {
    ClarificationQuestionStatus.answered,
    ClarificationQuestionStatus.deferred,
    ClarificationQuestionStatus.not_available,
    ClarificationQuestionStatus.not_applicable,
}


def generate_clarifications(
    data_quality_run_id: str,
    *,
    audience: str = ClarificationAudience.client,
    max_questions: int = 5,
    force: bool = False,
    created_by_user_id: str | None = None,
) -> ClarificationResultResponse:
    audience = _validate_audience(audience)
    if max_questions < 3 or max_questions > 5:
        raise AppError(
            "invalid_clarification_limit",
            "Progressive clarification batches must request between 3 and 5 questions",
            400,
        )

    with db_session() as db:
        quality_run = (
            db.query(DataQualityRun)
            .filter(DataQualityRun.id == data_quality_run_id)
            .first()
        )
        if quality_run is None:
            raise AppError("data_quality_run_not_found", "Data-quality run not found", 404)
        if quality_run.status != DataQualityRunStatus.completed:
            raise AppError(
                "data_quality_run_not_completed",
                "Clarifications require a completed data-quality run",
                409,
            )
        source_table = (
            db.query(SourceTable)
            .filter(SourceTable.id == quality_run.source_table_id)
            .first()
        )
        if source_table is None:
            raise AppError("source_table_not_found", "Source table not found", 404)

        issues = (
            db.query(DataQualityIssue)
            .filter(DataQualityIssue.data_quality_run_id == quality_run.id)
            .order_by(
                DataQualityIssue.severity.desc(),
                DataQualityIssue.category.asc(),
                DataQualityIssue.code.asc(),
                DataQualityIssue.id.asc(),
            )
            .all()
        )
        columns = (
            db.query(SourceColumn)
            .filter(SourceColumn.source_table_id == source_table.id)
            .order_by(SourceColumn.position.asc(), SourceColumn.id.asc())
            .all()
        )
        mappings = (
            db.query(ColumnMapping)
            .filter(ColumnMapping.source_table_id == source_table.id)
            .order_by(ColumnMapping.source_column_id.asc())
            .all()
        )

        all_candidates = build_candidates(
            quality_run=quality_run,
            source_table=source_table,
            issues=issues,
            columns=columns,
            mappings=mappings,
        )
        audience_candidates = [item for item in all_candidates if item.audience == audience]
        audience_candidates.sort(key=lambda item: (-item.score, item.category, item.key))

        resolution_history = _terminal_resolution_history(
            db,
            source_table_id=source_table.id,
            audience=audience,
        )
        suppressed_keys = {
            candidate.key for candidate in audience_candidates if candidate.key in resolution_history
        }
        unresolved_candidates = [
            candidate for candidate in audience_candidates if candidate.key not in suppressed_keys
        ]
        selected = unresolved_candidates[:max_questions]

        fingerprint_payload = {
            "generator_version": GENERATOR_VERSION,
            "data_quality": {
                "run_id": quality_run.id,
                "input_fingerprint": quality_run.input_fingerprint,
                "overall_status": quality_run.overall_status,
                "issue_ids": [item.id for item in issues],
            },
            "audience": audience,
            "max_questions": max_questions,
            "candidates": [_candidate_snapshot(item) for item in audience_candidates],
            "terminal_resolution_history": resolution_history,
        }
        input_fingerprint = hashlib.sha256(
            json.dumps(
                fingerprint_payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()

        existing = (
            db.query(ClarificationRun)
            .filter(
                ClarificationRun.source_table_id == source_table.id,
                ClarificationRun.generator_version == GENERATOR_VERSION,
                ClarificationRun.input_fingerprint == input_fingerprint,
                ClarificationRun.audience == audience,
            )
            .order_by(ClarificationRun.run_number.desc(), ClarificationRun.created_at.desc())
            .first()
        )
        if existing is not None and not force:
            return _result_response(db, existing)

        run_number = (
            db.query(func.max(ClarificationRun.run_number))
            .filter(ClarificationRun.source_table_id == source_table.id)
            .scalar()
            or 0
        ) + 1
        now = datetime.now(timezone.utc)
        run_status = (
            ClarificationRunStatus.open if selected else ClarificationRunStatus.resolved
        )
        summary = {
            "generation_policy": "evidence_backed_progressive_questions",
            "audience": audience,
            "requested_max_questions": max_questions,
            "available_candidate_count": len(audience_candidates),
            "unresolved_candidate_count": len(unresolved_candidates),
            "selected_question_keys": [item.key for item in selected],
            "suppressed_question_keys": sorted(suppressed_keys),
            "queued_for_later_count": max(len(unresolved_candidates) - len(selected), 0),
            "source_data_quality_status": quality_run.overall_status,
            "principles": [
                "Questions are generated only from persisted evidence.",
                "Previously resolved questions are not repeated for the same source table.",
                "Answers are recorded but never mutate source files, mappings or normalized data automatically.",
                "Fewer than three questions are returned when fewer material gaps exist; no filler questions are invented.",
            ],
            "next_action": "answer_open_questions" if selected else "no_unresolved_questions",
        }
        run = ClarificationRun(
            data_quality_run_id=quality_run.id,
            source_table_id=quality_run.source_table_id,
            source_file_id=quality_run.source_file_id,
            import_session_id=quality_run.import_session_id,
            project_id=quality_run.project_id,
            run_number=run_number,
            generator_name=GENERATOR_NAME,
            generator_version=GENERATOR_VERSION,
            input_fingerprint=input_fingerprint,
            audience=audience,
            max_questions=max_questions,
            status=run_status,
            candidate_count=len(audience_candidates),
            question_count=len(selected),
            suppressed_question_count=len(suppressed_keys),
            open_question_count=len(selected),
            answered_question_count=0,
            deferred_question_count=0,
            not_available_question_count=0,
            not_applicable_question_count=0,
            summary_json=json_dumps(summary),
            created_by_user_id=created_by_user_id,
            resolved_at=now if not selected else None,
        )
        db.add(run)
        db.flush()

        for rank, candidate in enumerate(selected, start=1):
            evidence = dict(candidate.evidence)
            evidence.update(
                {
                    "data_quality_run_id": quality_run.id,
                    "data_quality_input_fingerprint": quality_run.input_fingerprint,
                    "data_quality_issue_ids": sorted(candidate.issue_ids),
                    "source_table_id": quality_run.source_table_id,
                    "source_file_id": quality_run.source_file_id,
                }
            )
            db.add(
                ClarificationQuestion(
                    clarification_run_id=run.id,
                    question_key=candidate.key,
                    rank=rank,
                    priority_score=candidate.score,
                    priority=priority_for_score(candidate.score),
                    category=candidate.category,
                    audience=candidate.audience,
                    question_text=candidate.question_text,
                    why_needed=candidate.why_needed,
                    answer_type=candidate.answer_type,
                    options_json=json_dumps(candidate.options),
                    issue_codes_json=json_dumps(sorted(set(candidate.issue_codes))),
                    evidence_json=json_dumps(evidence),
                    impact_json=json_dumps(candidate.impact),
                    status=ClarificationQuestionStatus.open,
                )
            )
        db.flush()
        db.refresh(run)
        return _result_response(db, run)


def get_latest_clarifications(
    data_quality_run_id: str,
    *,
    audience: str = ClarificationAudience.client,
) -> ClarificationResultResponse | None:
    audience = _validate_audience(audience)
    with db_session() as db:
        quality_exists = (
            db.query(DataQualityRun.id)
            .filter(DataQualityRun.id == data_quality_run_id)
            .first()
        )
        if quality_exists is None:
            raise AppError("data_quality_run_not_found", "Data-quality run not found", 404)
        run = (
            db.query(ClarificationRun)
            .filter(
                ClarificationRun.data_quality_run_id == data_quality_run_id,
                ClarificationRun.audience == audience,
            )
            .order_by(ClarificationRun.run_number.desc(), ClarificationRun.created_at.desc())
            .first()
        )
        return _result_response(db, run) if run else None


def get_clarification_run(run_id: str) -> ClarificationResultResponse | None:
    with db_session() as db:
        run = db.query(ClarificationRun).filter(ClarificationRun.id == run_id).first()
        return _result_response(db, run) if run else None


def list_clarification_questions(
    run_id: str,
    *,
    status: str | None = None,
    offset: int = 0,
    limit: int = 100,
) -> ClarificationQuestionPageResponse:
    with db_session() as db:
        run = db.query(ClarificationRun).filter(ClarificationRun.id == run_id).first()
        if run is None:
            raise AppError("clarification_run_not_found", "Clarification run not found", 404)
        query = db.query(ClarificationQuestion).filter(
            ClarificationQuestion.clarification_run_id == run.id
        )
        if status:
            valid = {str(item) for item in ClarificationQuestionStatus}
            if status not in valid:
                raise AppError(
                    "invalid_clarification_status",
                    "Unknown clarification question status",
                    400,
                )
            query = query.filter(ClarificationQuestion.status == status)
        total = query.count()
        questions = (
            query.order_by(ClarificationQuestion.rank.asc(), ClarificationQuestion.id.asc())
            .offset(offset)
            .limit(limit)
            .all()
        )
        return ClarificationQuestionPageResponse(
            clarification_run_id=run.id,
            offset=offset,
            limit=limit,
            total=total,
            questions=[_question_response(db, item) for item in questions],
        )


def submit_clarification_response(
    question_id: str,
    request: SubmitClarificationResponseRequest,
    *,
    responded_by_user_id: str | None = None,
) -> ClarificationQuestionResponse:
    resolution = request.resolution.strip().lower()
    if resolution not in {str(item) for item in _ALLOWED_RESOLUTIONS}:
        raise AppError(
            "invalid_clarification_resolution",
            "Resolution must be answered, deferred, not_available or not_applicable",
            400,
        )

    with db_session() as db:
        question = (
            db.query(ClarificationQuestion)
            .filter(ClarificationQuestion.id == question_id)
            .first()
        )
        if question is None:
            raise AppError(
                "clarification_question_not_found",
                "Clarification question not found",
                404,
            )
        run = (
            db.query(ClarificationRun)
            .filter(ClarificationRun.id == question.clarification_run_id)
            .first()
        )
        if run is None:
            raise AppError("clarification_run_not_found", "Clarification run not found", 404)

        answer = _validate_answer(question, resolution, request.answer)
        response_number = (
            db.query(func.max(ClarificationResponse.response_number))
            .filter(ClarificationResponse.clarification_question_id == question.id)
            .scalar()
            or 0
        ) + 1
        response = ClarificationResponse(
            clarification_question_id=question.id,
            response_number=response_number,
            resolution=resolution,
            answer_json=json_dumps(answer) if answer is not None else None,
            note=(request.note or "").strip() or None,
            responded_by_user_id=responded_by_user_id,
        )
        db.add(response)
        db.flush()

        question.status = resolution
        question.latest_response_id = response.id
        question.updated_at = datetime.now(timezone.utc)
        question.resolved_at = (
            None
            if resolution == ClarificationQuestionStatus.deferred
            else datetime.now(timezone.utc)
        )
        _refresh_run_counts(db, run)
        db.flush()
        db.refresh(question)
        return _question_response(db, question)


def list_clarification_responses(question_id: str) -> ClarificationResponsePageResponse:
    with db_session() as db:
        question = (
            db.query(ClarificationQuestion.id)
            .filter(ClarificationQuestion.id == question_id)
            .first()
        )
        if question is None:
            raise AppError(
                "clarification_question_not_found",
                "Clarification question not found",
                404,
            )
        responses = (
            db.query(ClarificationResponse)
            .filter(ClarificationResponse.clarification_question_id == question_id)
            .order_by(ClarificationResponse.response_number.asc())
            .all()
        )
        return ClarificationResponsePageResponse(
            clarification_question_id=question_id,
            total=len(responses),
            responses=[_response_response(item) for item in responses],
        )


def _terminal_resolution_history(db, *, source_table_id: str, audience: str) -> dict[str, dict]:
    questions = (
        db.query(ClarificationQuestion, ClarificationRun)
        .join(ClarificationRun, ClarificationRun.id == ClarificationQuestion.clarification_run_id)
        .filter(
            ClarificationRun.source_table_id == source_table_id,
            ClarificationRun.audience == audience,
            ClarificationQuestion.status.in_([str(item) for item in _TERMINAL_STATUSES]),
        )
        .order_by(ClarificationQuestion.created_at.asc(), ClarificationQuestion.id.asc())
        .all()
    )
    history: dict[str, dict] = {}
    for question, run in questions:
        response = None
        if question.latest_response_id:
            response = (
                db.query(ClarificationResponse)
                .filter(ClarificationResponse.id == question.latest_response_id)
                .first()
            )
        history[question.question_key] = {
            "question_id": question.id,
            "clarification_run_id": run.id,
            "status": question.status,
            "resolution": response.resolution if response else question.status,
            "answer": json_loads(response.answer_json) if response else None,
            "response_number": response.response_number if response else None,
        }
    return history


def _validate_answer(question: ClarificationQuestion, resolution: str, answer: Any):
    if resolution == ClarificationQuestionStatus.answered and answer is None:
        raise AppError(
            "clarification_answer_required",
            "An answered question requires an answer value",
            400,
        )
    if answer is None:
        return None

    options = _safe_list(json_loads(question.options_json))
    option_values = {
        str(item.get("value"))
        for item in options
        if isinstance(item, dict) and item.get("value") is not None
    }
    answer_type = question.answer_type
    if answer_type == ClarificationAnswerType.single_choice:
        if not isinstance(answer, str) or answer not in option_values:
            raise AppError(
                "invalid_clarification_answer",
                "The answer must be one of the allowed option values",
                400,
            )
    elif answer_type == ClarificationAnswerType.multiple_choice:
        if not isinstance(answer, list) or not answer or not all(
            isinstance(item, str) and item in option_values for item in answer
        ):
            raise AppError(
                "invalid_clarification_answer",
                "The answer must be a non-empty list of allowed option values",
                400,
            )
        answer = list(dict.fromkeys(answer))
    elif answer_type == ClarificationAnswerType.text:
        if not isinstance(answer, str) or not answer.strip():
            raise AppError(
                "invalid_clarification_answer",
                "The answer must be non-empty text",
                400,
            )
        answer = answer.strip()
    elif answer_type == ClarificationAnswerType.boolean:
        if not isinstance(answer, bool):
            raise AppError(
                "invalid_clarification_answer",
                "The answer must be a boolean",
                400,
            )
    elif answer_type == ClarificationAnswerType.integer:
        if isinstance(answer, bool) or not isinstance(answer, int):
            raise AppError(
                "invalid_clarification_answer",
                "The answer must be an integer",
                400,
            )
    return answer


def _refresh_run_counts(db, run: ClarificationRun) -> None:
    counts = Counter(
        status
        for (status,) in db.query(ClarificationQuestion.status)
        .filter(ClarificationQuestion.clarification_run_id == run.id)
        .all()
    )
    run.open_question_count = counts[ClarificationQuestionStatus.open]
    run.answered_question_count = counts[ClarificationQuestionStatus.answered]
    run.deferred_question_count = counts[ClarificationQuestionStatus.deferred]
    run.not_available_question_count = counts[ClarificationQuestionStatus.not_available]
    run.not_applicable_question_count = counts[ClarificationQuestionStatus.not_applicable]
    run.updated_at = datetime.now(timezone.utc)
    unresolved = run.open_question_count + run.deferred_question_count
    if unresolved:
        run.status = ClarificationRunStatus.open
        run.resolved_at = None
    else:
        run.status = ClarificationRunStatus.resolved
        run.resolved_at = datetime.now(timezone.utc)


def _result_response(db, run: ClarificationRun) -> ClarificationResultResponse:
    questions = (
        db.query(ClarificationQuestion)
        .filter(ClarificationQuestion.clarification_run_id == run.id)
        .order_by(ClarificationQuestion.rank.asc(), ClarificationQuestion.id.asc())
        .all()
    )
    return ClarificationResultResponse(
        run=_run_response(run),
        questions=[_question_response(db, item) for item in questions],
    )


def _run_response(model: ClarificationRun) -> ClarificationRunResponse:
    summary = json_loads(model.summary_json)
    return ClarificationRunResponse(
        id=model.id,
        data_quality_run_id=model.data_quality_run_id,
        source_table_id=model.source_table_id,
        source_file_id=model.source_file_id,
        import_session_id=model.import_session_id,
        project_id=model.project_id,
        run_number=model.run_number,
        generator_name=model.generator_name,
        generator_version=model.generator_version,
        input_fingerprint=model.input_fingerprint,
        audience=model.audience,
        max_questions=model.max_questions,
        status=model.status,
        candidate_count=model.candidate_count,
        question_count=model.question_count,
        suppressed_question_count=model.suppressed_question_count,
        open_question_count=model.open_question_count,
        answered_question_count=model.answered_question_count,
        deferred_question_count=model.deferred_question_count,
        not_available_question_count=model.not_available_question_count,
        not_applicable_question_count=model.not_applicable_question_count,
        summary=summary if isinstance(summary, dict) else {},
        created_by_user_id=model.created_by_user_id,
        created_at=model.created_at,
        updated_at=model.updated_at,
        resolved_at=model.resolved_at,
    )


def _question_response(db, model: ClarificationQuestion) -> ClarificationQuestionResponse:
    latest = None
    if model.latest_response_id:
        response = (
            db.query(ClarificationResponse)
            .filter(ClarificationResponse.id == model.latest_response_id)
            .first()
        )
        if response:
            latest = _response_response(response)
    return ClarificationQuestionResponse(
        id=model.id,
        clarification_run_id=model.clarification_run_id,
        question_key=model.question_key,
        rank=model.rank,
        priority_score=model.priority_score,
        priority=model.priority,
        category=model.category,
        audience=model.audience,
        question_text=model.question_text,
        why_needed=model.why_needed,
        answer_type=model.answer_type,
        options=_safe_list(json_loads(model.options_json)),
        issue_codes=_safe_list(json_loads(model.issue_codes_json)),
        evidence=_safe_dict(json_loads(model.evidence_json)),
        impact=_safe_dict(json_loads(model.impact_json)),
        status=model.status,
        latest_response=latest,
        created_at=model.created_at,
        updated_at=model.updated_at,
        resolved_at=model.resolved_at,
    )


def _response_response(model: ClarificationResponse) -> ClarificationResponseResponse:
    return ClarificationResponseResponse(
        id=model.id,
        clarification_question_id=model.clarification_question_id,
        response_number=model.response_number,
        resolution=model.resolution,
        answer=json_loads(model.answer_json) if model.answer_json is not None else None,
        note=model.note,
        responded_by_user_id=model.responded_by_user_id,
        created_at=model.created_at,
    )


def _candidate_snapshot(candidate: ClarificationCandidate) -> dict:
    return {
        "key": candidate.key,
        "audience": candidate.audience,
        "score": candidate.score,
        "category": candidate.category,
        "question_text": candidate.question_text,
        "why_needed": candidate.why_needed,
        "answer_type": candidate.answer_type,
        "options": candidate.options,
        "issue_codes": candidate.issue_codes,
        "issue_ids": candidate.issue_ids,
        "evidence": candidate.evidence,
        "impact": candidate.impact,
    }


def _validate_audience(audience: str) -> str:
    audience = audience.strip().lower()
    if audience not in {str(item) for item in ClarificationAudience}:
        raise AppError(
            "invalid_clarification_audience",
            "Audience must be client or analyst",
            400,
        )
    return audience


def _safe_list(value: Any) -> list:
    return value if isinstance(value, list) else []


def _safe_dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}
