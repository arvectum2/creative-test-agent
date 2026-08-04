"""Review, batch, knowledge, test-run, report, and export UI routes."""

from __future__ import annotations

import json
from collections.abc import Callable

from fastapi import APIRouter, Form, Query, Request
from fastapi.responses import RedirectResponse

from src.modules.audit_log.service import write_audit_event
from src.modules.audience_profiles.service import list_profiles as list_audience_profiles
from src.modules.batches.schemas import CreateBatchRequest
from src.modules.batches.service import create_batch, get_batch, list_batches
from src.modules.brand_profiles.service import list_profiles as list_brand_profiles
from src.modules.creative_assets.service import list_assets
from src.modules.report_generator.comparison import compare_test_runs
from src.modules.report_generator.service import generate_report
from src.modules.reviews.schemas import CreateReviewRequest
from src.modules.reviews.service import create_review, get_review, list_reviews
from src.modules.test_rubrics.service import list_rubrics
from src.modules.test_runs.schemas import CreateTestRunRequest
from src.modules.test_runs.service import (
    create_test_run,
    get_test_run,
    list_test_runs,
    run_test_run,
)
from src.modules.ui.common import render, render_error
from src.modules.ui.form_utils import (
    batch_request_payload,
    comma_values,
    json_object,
)
from src.shared.errors import AppError

router = APIRouter()


@router.get("/ui/reviews", include_in_schema=False)
def ui_reviews_list(
    request: Request,
    creative_asset_id: str | None = Query(None),
    project_id: str | None = Query(None),
    status: str | None = Query(None),
):
    return render(
        request,
        "reviews/list.html",
        reviews=list_reviews(
            creative_asset_id=creative_asset_id,
            project_id=project_id,
            status=status,
        ),
    )


@router.get("/ui/reviews/new", include_in_schema=False)
def ui_reviews_new(
    request: Request,
    asset_id: str | None = Query(None),
    report_id: str | None = Query(None),
):
    return render(
        request,
        "reviews/new.html",
        asset_id=asset_id,
        report_id=report_id,
    )


@router.post("/ui/reviews", include_in_schema=False)
async def ui_reviews_create(
    request: Request,
    creative_asset_id: str = Form(...),
    report_id: str | None = Form(None),
    reviewer: str = Form("system"),
    decision: str | None = Form(None),
    rating: int | None = Form(None),
    summary: str | None = Form(None),
    strengths: str | None = Form(None),
    concerns: str | None = Form(None),
    revision_requests: str | None = Form(None),
):
    try:
        review = create_review(
            CreateReviewRequest(
                creative_asset_id=creative_asset_id,
                report_id=report_id,
                reviewer=reviewer,
                decision=decision or None,
                rating=rating,
                summary=summary or None,
                strengths=strengths or None,
                concerns=concerns or None,
                revision_requests=revision_requests or None,
            )
        )
    except Exception as exc:
        return render(
            request,
            "reviews/new.html",
            error=str(exc),
            asset_id=creative_asset_id,
            report_id=report_id,
        )
    write_audit_event(
        "review_created",
        "creative_review",
        review.id,
        {"creative_asset_id": creative_asset_id, "reviewer": reviewer},
    )
    return RedirectResponse(url=f"/ui/reviews/{review.id}", status_code=303)


@router.get("/ui/reviews/{review_id}", include_in_schema=False)
def ui_reviews_detail(request: Request, review_id: str):
    review = get_review(review_id)
    if review is None:
        return render_error(request, f"Review not found: {review_id}")
    return render(request, "reviews/detail.html", review=review)


@router.get("/ui/batches", include_in_schema=False)
def ui_batches_list(request: Request, project_id: str | None = Query(None)):
    return render(
        request,
        "batches/list.html",
        batches=list_batches(project_id=project_id),
    )


@router.get("/ui/batches/new", include_in_schema=False)
def ui_batches_new(
    request: Request,
    project_id: str | None = Query(None),
    asset_ids: str | None = Query(None),
):
    return render(
        request,
        "batches/new.html",
        project_id=project_id,
        asset_ids=comma_values(asset_ids),
    )


@router.post("/ui/batches", include_in_schema=False)
async def ui_batches_create(
    request: Request,
    name: str = Form(...),
    description: str | None = Form(None),
    project_id: str | None = Form(None),
    creative_asset_ids: str | None = Form(None),
    audience_profile_ids: str | None = Form(None),
    brand_profile_id: str | None = Form(None),
    test_rubric_id: str | None = Form(None),
    input_context: str | None = Form(None),
):
    try:
        batch = create_batch(
            CreateBatchRequest(
                **batch_request_payload(
                    project_id=project_id,
                    name=name,
                    description=description,
                    creative_asset_ids=creative_asset_ids,
                    audience_profile_ids=audience_profile_ids,
                    brand_profile_id=brand_profile_id,
                    test_rubric_id=test_rubric_id,
                    input_context=input_context,
                )
            )
        )
    except Exception as exc:
        return render(
            request,
            "batches/new.html",
            error=str(exc),
            project_id=project_id,
        )
    write_audit_event("batch_created", "batch_run", batch.id, {"name": name})
    return RedirectResponse(url=f"/ui/batches/{batch.id}", status_code=303)


@router.get("/ui/batches/{batch_id}", include_in_schema=False)
def ui_batches_detail(request: Request, batch_id: str):
    batch = get_batch(batch_id)
    if batch is None:
        return render_error(request, f"Batch not found: {batch_id}")
    return render(request, "batches/detail.html", batch=batch)


@router.get("/ui/knowledge-base", include_in_schema=False)
def ui_knowledge_base(request: Request, q: str | None = Query(None)):
    from src.modules.knowledge_base.search import keyword_search
    from src.modules.knowledge_base.service import list_knowledge_items

    if q:
        results = keyword_search(query=q, max_results=20)
        items = [result.item for result in results]
        total = len(results)
    else:
        all_items = list_knowledge_items()
        items = all_items[:50]
        total = len(all_items)
    return render(
        request,
        "knowledge_base/list.html",
        items=items,
        total=total,
        query=q or "",
    )


@router.post("/ui/knowledge-base", include_in_schema=False)
def ui_knowledge_base_create(
    request: Request,
    title: str = Form(...),
    content: str | None = Form(None),
    tags: str | None = Form(None),
):
    from src.modules.knowledge_base.schemas import CreateKnowledgeItemRequest
    from src.modules.knowledge_base.service import create_knowledge_item

    try:
        item = create_knowledge_item(
            CreateKnowledgeItemRequest(
                source_type="manual_note",
                title=title,
                content=content,
                tags=comma_values(tags),
            )
        )
    except Exception as exc:
        return render(
            request,
            "knowledge_base/list.html",
            error=str(exc),
            items=[],
            total=0,
            query="",
            show_form=True,
        )
    return RedirectResponse(
        url=f"/ui/knowledge-base?created={item.id[:8]}",
        status_code=303,
    )


@router.get("/ui/test-runs", include_in_schema=False)
def ui_test_runs_list(request: Request):
    return render(request, "test_runs/list.html", runs=list_test_runs())


@router.get("/ui/test-runs/new", include_in_schema=False)
def ui_test_runs_new(request: Request):
    return render(request, "test_runs/new.html", **_test_run_form_context())


@router.post("/ui/test-runs", include_in_schema=False)
def ui_test_runs_create(
    request: Request,
    creative_asset_id: str = Form(...),
    brand_profile_id: str | None = Form(None),
    audience_profile_ids: list[str] = Form([]),
    rubric_id: str | None = Form(None),
    project_id: str | None = Form(None),
    input_context: str | None = Form(None),
):
    try:
        context = json_object(input_context, strict=True)
    except json.JSONDecodeError:
        return render(
            request,
            "test_runs/new.html",
            error="Invalid JSON in input context.",
            **_test_run_form_context(),
        )
    try:
        run = create_test_run(
            CreateTestRunRequest(
                creative_asset_id=creative_asset_id,
                brand_profile_id=brand_profile_id or None,
                audience_profile_ids=audience_profile_ids or [],
                rubric_id=rubric_id or None,
                input_context=context,
                project_id=project_id or None,
            )
        )
    except AppError as exc:
        return render(
            request,
            "test_runs/new.html",
            error=exc.message,
            **_test_run_form_context(),
        )
    return RedirectResponse(url=f"/ui/test-runs/{run.id}", status_code=303)


@router.get("/ui/test-runs/{run_id}", include_in_schema=False)
def ui_test_runs_detail(request: Request, run_id: str):
    run = get_test_run(run_id)
    if run is None:
        return render_error(request, f"Test run not found: {run_id}")
    return render(request, "test_runs/detail.html", run=run)


@router.post("/ui/test-runs/{run_id}/run", include_in_schema=False)
def ui_test_runs_run(request: Request, run_id: str):
    run = get_test_run(run_id)
    if run is None:
        return render_error(request, f"Test run not found: {run_id}")
    try:
        run_test_run(run_id)
    except Exception as exc:
        return render(
            request,
            "test_runs/detail.html",
            run=get_test_run(run_id),
            error=str(exc),
        )
    return RedirectResponse(url=f"/ui/test-runs/{run_id}", status_code=303)


@router.get("/ui/reports/{run_id}", include_in_schema=False)
def ui_reports_detail(
    request: Request,
    run_id: str,
    export_job: str | None = None,
):
    report = generate_report(run_id, report_mode="internal", report_format="json")
    if report is None:
        return render_error(request, f"Report not available for test run: {run_id}")
    context = {}
    if export_job:
        from src.modules.export_jobs.service import get_export_job

        job = get_export_job(export_job)
        if job:
            context["export_job"] = job
    return render(request, "reports/detail.html", report=report, **context)


@router.post("/ui/exports/report/{report_id}/docx", include_in_schema=False)
def ui_export_report_docx(request: Request, report_id: str):
    from src.modules.export_jobs.router import post_docx_export

    return _run_report_export(request, report_id, post_docx_export)


@router.post("/ui/exports/report/{report_id}/pptx", include_in_schema=False)
def ui_export_report_pptx(request: Request, report_id: str):
    from src.modules.export_jobs.router import post_pptx_export

    return _run_report_export(request, report_id, post_pptx_export)


@router.post("/ui/exports/report/{report_id}/pdf", include_in_schema=False)
def ui_export_report_pdf(request: Request, report_id: str):
    from src.modules.export_jobs.router import post_pdf_export

    return _run_report_export(request, report_id, post_pdf_export)


@router.get("/ui/exports", include_in_schema=False)
def ui_exports_list(request: Request):
    from src.modules.export_jobs.service import list_export_jobs

    return render(request, "exports/list.html", jobs=list_export_jobs())


@router.get("/ui/exports/{job_id}", include_in_schema=False)
def ui_exports_detail(request: Request, job_id: str):
    from src.modules.export_jobs.service import get_export_job

    job = get_export_job(job_id)
    if job is None:
        return render_error(request, f"Export job not found: {job_id}")
    return render(request, "exports/list.html", jobs=[job])


@router.get("/ui/compare", include_in_schema=False)
def ui_compare_form(request: Request):
    return render(
        request,
        "reports/compare.html",
        completed_runs=_completed_runs(),
    )


@router.post("/ui/compare", include_in_schema=False)
def ui_compare_result(
    request: Request,
    test_run_ids: list[str] = Form(...),
    report_mode: str = Form("internal"),
):
    try:
        result = compare_test_runs(test_run_ids, report_mode)
    except ValueError as exc:
        return render(
            request,
            "reports/compare.html",
            error=str(exc),
            completed_runs=_completed_runs(),
        )
    return render(request, "reports/comparison_result.html", result=result)


def _test_run_form_context() -> dict:
    return {
        "assets": list_assets(),
        "brand_profiles": list_brand_profiles(),
        "audience_profiles": list_audience_profiles(),
        "rubrics": list_rubrics(),
    }


def _completed_runs() -> list:
    return [run for run in list_test_runs() if run.status == "completed"]


def _run_report_export(
    request: Request,
    report_id: str,
    exporter: Callable[[str], object],
):
    try:
        job = exporter(report_id)
        return RedirectResponse(
            url=f"/ui/reports/{job.entity_id}?export_job={job.id}",
            status_code=303,
        )
    except Exception as exc:
        from src.modules.report_generator.service import get_report_by_id

        report = get_report_by_id(report_id)
        if report:
            return render(
                request,
                "reports/detail.html",
                report=report,
                error=str(exc),
            )
        return render_error(request, str(exc))
