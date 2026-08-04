"""Model, evaluation, trace, user, and maintenance UI routes."""

from __future__ import annotations

from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse

from src.modules.ui.common import render, render_error
from src.shared.config.settings import get_settings
from src.shared.security.auth import get_optional_user_from_request

router = APIRouter()

_EVALUATION_CASES = [
    {"case_id": "novabank_variant_a", "title": "NovaBank Variant A (clean)"},
    {"case_id": "novabank_variant_b", "title": "NovaBank Variant B (clean)"},
    {"case_id": "novabank_variant_c_risky", "title": "NovaBank Variant C (risky)"},
    {
        "case_id": "brandbook_claim_policy_violation",
        "title": "Brandbook Claim Policy Violation",
    },
    {"case_id": "tone_of_voice_mismatch", "title": "Tone of Voice Mismatch"},
]


@router.get("/ui/model-profiles", include_in_schema=False)
def ui_model_profiles_list(request: Request):
    from src.modules.model_profiles.service import list_profiles

    return render(request, "model_profiles/list.html", profiles=list_profiles())


@router.get("/ui/model-profiles/new", include_in_schema=False)
def ui_model_profiles_new(request: Request):
    return render(request, "model_profiles/new.html")


@router.post("/ui/model-profiles", include_in_schema=False)
def ui_model_profiles_create(
    request: Request,
    profile_name: str = Form(...),
    provider: str = Form(...),
    model: str = Form(...),
    base_url: str | None = Form(None),
    timeout_seconds: int = Form(120),
    notes: str | None = Form(None),
):
    from src.modules.model_profiles.schemas import CreateModelProfileRequest
    from src.modules.model_profiles.service import create_profile

    try:
        profile = create_profile(
            CreateModelProfileRequest(
                profile_name=profile_name,
                provider=provider,
                model=model,
                base_url=base_url or None,
                timeout_seconds=timeout_seconds,
                notes=notes or None,
            )
        )
    except ValueError as exc:
        return render(request, "model_profiles/new.html", error=str(exc))
    return RedirectResponse(url=f"/ui/model-profiles/{profile.id}", status_code=303)


@router.get("/ui/model-profiles/{profile_id}", include_in_schema=False)
def ui_model_profiles_detail(request: Request, profile_id: str):
    from src.modules.model_profiles.service import get_profile

    profile = get_profile(profile_id)
    if profile is None:
        return render_error(request, f"Model profile not found: {profile_id}")
    return render(
        request,
        "model_profiles/detail.html",
        profile=profile,
        health=None,
    )


@router.post("/ui/model-profiles/{profile_id}/health", include_in_schema=False)
def ui_model_profiles_health(request: Request, profile_id: str):
    from src.modules.model_profiles.service import check_profile_health, get_profile

    profile = get_profile(profile_id)
    if profile is None:
        return render_error(request, f"Model profile not found: {profile_id}")
    try:
        health = check_profile_health(profile_id)
    except ValueError as exc:
        return render(
            request,
            "model_profiles/detail.html",
            profile=profile,
            health=None,
            error=str(exc),
        )
    return render(
        request,
        "model_profiles/detail.html",
        profile=profile,
        health=health,
    )


@router.post("/ui/model-profiles/load-from-config", include_in_schema=False)
def ui_model_profiles_load_config(request: Request):
    from src.modules.model_profiles.router import post_load_from_config
    from src.modules.model_profiles.service import list_profiles

    try:
        post_load_from_config()
    except Exception as exc:
        return render(
            request,
            "model_profiles/list.html",
            profiles=list_profiles(),
            error=str(exc),
        )
    return RedirectResponse(url="/ui/model-profiles", status_code=303)


@router.get("/ui/evaluations", include_in_schema=False)
def ui_evaluations_list(request: Request):
    from src.modules.evaluations.models import EvaluationRun
    from src.shared.db.repository import db_session, json_loads

    with db_session() as db:
        runs = db.query(EvaluationRun).order_by(EvaluationRun.created_at.desc()).all()
        run_list = [
            {
                "id": run.id,
                "profile_id": run.profile_id,
                "provider": run.provider,
                "model": run.model,
                "status": run.status,
                "summary": json_loads(run.summary_json) or {},
                "created_at": run.created_at,
            }
            for run in runs
        ]
    return render(request, "evaluations/list.html", runs=run_list)


@router.get("/ui/evaluations/run", include_in_schema=False)
def ui_evaluations_run_form(request: Request):
    from src.modules.model_profiles.service import list_profiles

    return render(
        request,
        "evaluations/run.html",
        profiles=list_profiles(),
        cases=_EVALUATION_CASES,
    )


@router.post("/ui/evaluations/run", include_in_schema=False)
def ui_evaluations_run(
    request: Request,
    profile_id: str | None = Form(None),
    case_ids: list[str] = Form([]),
):
    from src.modules.evaluations.runner import run_evaluation
    from src.modules.model_profiles.service import list_profiles

    try:
        result = run_evaluation(
            profile_id=profile_id or None,
            case_ids=case_ids or None,
        )
    except Exception as exc:
        return render(
            request,
            "evaluations/run.html",
            error=str(exc),
            profiles=list_profiles(),
            cases=_EVALUATION_CASES,
        )
    return RedirectResponse(
        url=f"/ui/evaluations/{result['evaluation_run_id']}",
        status_code=303,
    )


@router.get("/ui/evaluations/{eval_id}", include_in_schema=False)
def ui_evaluations_detail(request: Request, eval_id: str):
    from src.modules.evaluations.runner import get_evaluation_results

    result = get_evaluation_results(eval_id)
    if result is None:
        return render_error(request, f"Evaluation not found: {eval_id}")
    return render(
        request,
        "evaluations/detail.html",
        eval_id=eval_id,
        result=result,
    )


@router.get("/ui/prompt-traces", include_in_schema=False)
def ui_prompt_traces_list(
    request: Request,
    test_run_id: str | None = None,
    evaluation_run_id: str | None = None,
):
    from src.modules.prompt_traces.service import list_traces

    return render(
        request,
        "prompt_traces/list.html",
        traces=list_traces(
            test_run_id=test_run_id,
            evaluation_run_id=evaluation_run_id,
        ),
        test_run_id=test_run_id,
        evaluation_run_id=evaluation_run_id,
    )


@router.get("/ui/prompt-traces/{trace_id}", include_in_schema=False)
def ui_prompt_traces_detail(request: Request, trace_id: str):
    from src.modules.prompt_traces.service import get_trace

    trace = get_trace(trace_id)
    if trace is None:
        return render_error(request, f"Prompt trace not found: {trace_id}")
    return render(request, "prompt_traces/detail.html", trace=trace)


@router.get("/ui/test-runs/{run_id}/prompt-traces", include_in_schema=False)
def ui_test_run_prompt_traces(request: Request, run_id: str):
    from src.modules.prompt_traces.service import list_traces

    return render(
        request,
        "prompt_traces/list.html",
        traces=list_traces(test_run_id=run_id),
        test_run_id=run_id,
    )


@router.get("/ui/users", include_in_schema=False)
def ui_users_list(request: Request):
    from src.modules.users.service import list_users

    return render(request, "users/list.html", users=list_users())


@router.get("/ui/users/new", include_in_schema=False)
def ui_users_new(request: Request):
    from src.modules.users.models import UserRole

    return render(request, "users/new.html", roles=list(UserRole))


@router.post("/ui/users", include_in_schema=False)
def ui_users_create(
    request: Request,
    email: str = Form(...),
    display_name: str = Form(...),
    role: str = Form("viewer"),
    password: str = Form(...),
):
    from src.modules.users.models import UserRole
    from src.modules.users.schemas import CreateUserRequest
    from src.modules.users.service import create_user

    try:
        user = create_user(
            CreateUserRequest(
                email=email,
                display_name=display_name,
                role=UserRole(role),
                is_active=True,
                password=password,
            )
        )
    except Exception as exc:
        return render(
            request,
            "users/new.html",
            error=str(exc),
            roles=list(UserRole),
        )
    return RedirectResponse(url=f"/ui/users?created={user.id}", status_code=303)


@router.get("/ui/users/{user_id}", include_in_schema=False)
def ui_users_detail(request: Request, user_id: str):
    from src.modules.users.service import get_user

    user = get_user(user_id)
    if user is None:
        return render_error(request, f"User not found: {user_id}")
    return render(request, "users/detail.html", u=user)


@router.post("/ui/users/{user_id}/deactivate", include_in_schema=False)
def ui_users_deactivate(request: Request, user_id: str):
    from src.modules.users.service import deactivate_user

    try:
        deactivate_user(user_id)
    except ValueError as exc:
        return render_error(request, str(exc))
    return RedirectResponse(url="/ui/users", status_code=303)


@router.get("/ui/admin/maintenance", include_in_schema=False)
def ui_maintenance(request: Request):
    from src.modules.admin.router import (
        get_database_status,
        get_maintenance_status,
        get_storage_status,
    )

    settings = get_settings()
    current_user = get_optional_user_from_request(request)
    if settings.enable_auth and (
        not current_user
        or current_user.get("role") not in ("admin", "manager")
    ):
        return render_error(
            request,
            "Maintenance page requires admin or manager role.",
        )
    try:
        status = get_maintenance_status()
        storage = get_storage_status()
        db_status = get_database_status()
    except Exception as exc:
        return render_error(request, f"Could not load maintenance data: {exc}")
    return render(
        request,
        "admin/maintenance.html",
        status=status,
        storage=storage,
        db_status=db_status,
    )
