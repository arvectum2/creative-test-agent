"""Pilot workspace quality review, clarification, readiness, and report routes."""

from __future__ import annotations

from fastapi import APIRouter, Form, Request

from src.modules.clarifications.lifecycle import record_clarification_response
from src.modules.clarifications.schemas import SubmitClarificationResponseRequest
from src.modules.clarifications.service import (
    generate_clarifications,
    get_latest_clarifications,
)
from src.modules.client_one_page_reports.service import (
    generate_client_one_page_report,
    get_latest_client_one_page_report,
)
from src.modules.data_quality.service import get_data_quality_report
from src.modules.data_review_reports.service import (
    generate_data_review_report,
    get_latest_data_review_report,
)
from src.modules.pilot_workspace.helpers import quality_redirect, require_project
from src.modules.prediction_readiness.service import (
    evaluate_prediction_readiness,
    get_latest_prediction_readiness,
)
from src.modules.ui.common import render, render_error
from src.shared.errors import AppError
from src.shared.security.auth import get_optional_user_id

router = APIRouter(prefix="/ui/pilot-workspaces", tags=["pilot-workspace"])


@router.get("/{project_id}/data-quality/{run_id}", include_in_schema=False)
def pilot_workspace_quality(request: Request, project_id: str, run_id: str):
    try:
        project = require_project(project_id)
        quality = get_data_quality_report(run_id)
        if quality is None or quality.run.project_id != project_id:
            raise AppError(
                "data_quality_run_not_found",
                "Data-quality run not found",
                404,
            )
        client_questions = get_latest_clarifications(run_id, audience="client")
        analyst_questions = get_latest_clarifications(run_id, audience="analyst")
        readiness = get_latest_prediction_readiness(run_id)
        data_review = get_latest_data_review_report(run_id)
        one_page = get_latest_client_one_page_report(run_id)
    except AppError as exc:
        return render_error(request, exc.message)
    return render(
        request,
        "pilot_workspaces/data_quality.html",
        project=project,
        quality=quality,
        client_questions=client_questions,
        analyst_questions=analyst_questions,
        readiness=readiness,
        data_review=data_review,
        one_page=one_page,
        notice=request.query_params.get("notice"),
        error=request.query_params.get("error"),
    )


@router.post(
    "/{project_id}/data-quality/{run_id}/clarifications",
    include_in_schema=False,
)
def pilot_workspace_clarifications(
    request: Request,
    project_id: str,
    run_id: str,
    audience: str = Form("client"),
):
    try:
        result = generate_clarifications(
            run_id,
            audience=audience,
            max_questions=5,
            force=True,
            created_by_user_id=get_optional_user_id(request),
        )
        return quality_redirect(
            project_id,
            run_id,
            notice=f"Сформировано вопросов: {result.run.question_count}",
        )
    except (AppError, ValueError) as exc:
        return quality_redirect(
            project_id,
            run_id,
            error=getattr(exc, "message", str(exc)),
        )


@router.post(
    "/{project_id}/data-quality/{run_id}/questions/{question_id}",
    include_in_schema=False,
)
def pilot_workspace_answer_question(
    request: Request,
    project_id: str,
    run_id: str,
    question_id: str,
    resolution: str = Form("answered"),
    answer: str | None = Form(None),
    note: str | None = Form(None),
):
    try:
        record_clarification_response(
            question_id,
            SubmitClarificationResponseRequest(
                resolution=resolution,
                answer=(answer or "").strip() or None,
                note=(note or "").strip() or None,
            ),
            responded_by_user_id=get_optional_user_id(request),
        )
        return quality_redirect(project_id, run_id, notice="Ответ сохранён")
    except (AppError, ValueError) as exc:
        return quality_redirect(
            project_id,
            run_id,
            error=getattr(exc, "message", str(exc)),
        )


@router.post(
    "/{project_id}/data-quality/{run_id}/readiness",
    include_in_schema=False,
)
def pilot_workspace_readiness(request: Request, project_id: str, run_id: str):
    try:
        result = evaluate_prediction_readiness(
            run_id,
            force=True,
            created_by_user_id=get_optional_user_id(request),
        )
        return quality_redirect(
            project_id,
            run_id,
            notice=f"Готовность обновлена: {result.run.overall_status}",
        )
    except (AppError, ValueError) as exc:
        return quality_redirect(
            project_id,
            run_id,
            error=getattr(exc, "message", str(exc)),
        )


@router.post(
    "/{project_id}/data-quality/{run_id}/reports/data-review",
    include_in_schema=False,
)
def pilot_workspace_data_review_report(
    request: Request,
    project_id: str,
    run_id: str,
):
    try:
        readiness = get_latest_prediction_readiness(run_id)
        result = generate_data_review_report(
            run_id,
            prediction_readiness_run_id=readiness.run.id if readiness else None,
            quantitative_study_id=None,
            force=True,
            created_by_user_id=get_optional_user_id(request),
        )
        return quality_redirect(
            project_id,
            run_id,
            notice=f"XLSX-отчёт сформирован: {result.filename}",
        )
    except (AppError, ValueError) as exc:
        return quality_redirect(
            project_id,
            run_id,
            error=getattr(exc, "message", str(exc)),
        )


@router.post(
    "/{project_id}/data-quality/{run_id}/reports/one-page",
    include_in_schema=False,
)
def pilot_workspace_one_page_report(
    request: Request,
    project_id: str,
    run_id: str,
    locale: str = Form("ru"),
):
    try:
        readiness = get_latest_prediction_readiness(run_id)
        result = generate_client_one_page_report(
            run_id,
            prediction_readiness_run_id=readiness.run.id if readiness else None,
            quantitative_study_id=None,
            locale=locale if locale in {"ru", "en"} else "ru",
            force=True,
            created_by_user_id=get_optional_user_id(request),
        )
        return quality_redirect(
            project_id,
            run_id,
            notice=f"Одностраничный отчёт сформирован: {result.verdict}",
        )
    except (AppError, ValueError) as exc:
        return quality_redirect(
            project_id,
            run_id,
            error=getattr(exc, "message", str(exc)),
        )
