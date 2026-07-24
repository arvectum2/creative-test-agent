from collections import Counter
from datetime import datetime, timezone

from src.modules.clarifications.models import (
    ClarificationQuestion,
    ClarificationQuestionStatus,
    ClarificationRun,
    ClarificationRunStatus,
)
from src.modules.clarifications.schemas import (
    ClarificationQuestionResponse,
    SubmitClarificationResponseRequest,
)
from src.modules.clarifications.service import (
    list_clarification_questions,
    submit_clarification_response,
)
from src.shared.db.repository import db_session


def record_clarification_response(
    question_id: str,
    request: SubmitClarificationResponseRequest,
    *,
    responded_by_user_id: str | None = None,
) -> ClarificationQuestionResponse:
    """Persist a response and reconcile aggregate run state after commit.

    The project session factory intentionally disables autoflush. The response
    service therefore commits the question transition first, and this wrapper
    recalculates the parent run in a fresh transaction so aggregate counts always
    reflect the persisted question statuses.
    """
    submitted = submit_clarification_response(
        question_id,
        request,
        responded_by_user_id=responded_by_user_id,
    )
    _reconcile_run(submitted.clarification_run_id)
    page = list_clarification_questions(
        submitted.clarification_run_id,
        offset=0,
        limit=500,
    )
    return next(item for item in page.questions if item.id == question_id)


def _reconcile_run(run_id: str) -> None:
    with db_session() as db:
        run = db.query(ClarificationRun).filter(ClarificationRun.id == run_id).first()
        if run is None:
            return
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
        db.flush()
