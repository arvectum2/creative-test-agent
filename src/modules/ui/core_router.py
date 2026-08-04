"""Home, language, and static-file UI routes."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, RedirectResponse

from src.modules.audience_profiles.service import list_profiles as list_audience_profiles
from src.modules.brand_profiles.service import list_profiles as list_brand_profiles
from src.modules.clients.service import list_clients
from src.modules.creative_assets.service import list_assets
from src.modules.projects.service import list_projects
from src.modules.test_runs.service import list_test_runs
from src.modules.ui.common import STATIC_DIR, render

router = APIRouter()


@router.get("/lang/{lang}", include_in_schema=False)
def switch_lang(request: Request, lang: str, ref: str | None = None):
    if lang not in ("ru", "en"):
        lang = "ru"
    redirect_to = ref or request.headers.get("referer", "/")
    response = RedirectResponse(url=redirect_to, status_code=303)
    response.set_cookie(
        key="lang",
        value=lang,
        max_age=365 * 24 * 3600,
        samesite="lax",
    )
    return response


@router.get("/static/styles.css", include_in_schema=False)
def serve_css():
    return FileResponse(str(STATIC_DIR / "styles.css"), media_type="text/css")


@router.get("/static/logo.svg", include_in_schema=False)
def serve_logo():
    return FileResponse(str(STATIC_DIR / "logo.svg"), media_type="image/svg+xml")


@router.get("/", include_in_schema=False)
@router.get("/ui", include_in_schema=False)
def dashboard(request: Request):
    assets = list_assets()
    brands = list_brand_profiles()
    audiences = list_audience_profiles()
    runs = list_test_runs()
    recent = sorted(runs, key=lambda run: run.created_at, reverse=True)[:5]

    from src.modules.brandbooks.service import list_brandbooks
    from src.modules.knowledge_base.service import list_knowledge_items

    clients = list_clients()
    projects = list_projects()
    return render(
        request,
        "dashboard.html",
        client_count=len(clients),
        project_count=len(projects),
        asset_count=len(assets),
        brand_count=len(brands),
        audience_count=len(audiences),
        run_count=len(runs),
        recent_runs=recent,
        brandbook_count=len(list_brandbooks()),
        knowledge_count=len(list_knowledge_items()),
    )
