import logging
import sys
from pathlib import Path

from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from src.modules.agent_registry.router import router as agent_registry_router
from src.modules.audit_log.router import router as audit_log_router
from src.modules.audience_profiles.router import router as audience_profiles_router
from src.modules.brand_profiles.router import router as brand_profiles_router
from src.modules.creative_assets.router import router as creative_assets_router
from src.modules.report_generator.router import router as report_generator_router
from src.modules.test_rubrics.router import router as test_rubrics_router
from src.modules.ui.router import router as ui_router
from src.modules.test_runs.router import router as test_runs_router
from src.modules.clients.router import router as clients_router
from src.modules.projects.router import router as projects_router
from src.modules.users.router import router as users_router
from src.modules.brandbooks.router import router as brandbooks_router
from src.modules.knowledge_base.router import router as knowledge_base_router
from src.modules.export_jobs.router import router as export_jobs_router
from src.modules.admin.router import router as admin_router
from src.modules.auth.router import router as auth_router
from src.modules.auth.ui_router import (
    remove_legacy_ui_auth_routes,
    router as auth_ui_router,
)
from src.modules.model_profiles.router import router as model_profiles_router
from src.modules.prompt_registry.router import router as prompt_registry_router
from src.modules.evaluations.router import router as evaluations_router
from src.modules.prompt_traces.router import router as prompt_traces_router
from src.modules.reviews.router import router as reviews_router
from src.modules.job_queue.router import router as job_queue_router
from src.modules.batches.router import router as batches_router
from src.modules.demo.router import router as demo_router
from src.modules.import_sessions.router import router as import_sessions_router
from src.modules.import_sessions.tabular_router import router as tabular_inspection_router
from src.modules.mapping_engine.router import router as mapping_engine_router
from src.modules.normalized_data.router import router as normalized_data_router
from src.modules.data_quality.router import router as data_quality_router
from src.modules.clarifications.router import router as clarifications_router
from src.modules.prediction_readiness.router import router as prediction_readiness_router
from src.modules.quantitative_surveys.router import router as quantitative_surveys_router
from src.modules.data_review_reports.router import router as data_review_reports_router
from src.shared.api.errors import register_exception_handlers
from src.shared.config.settings import get_settings
from src.shared.db.session import check_db_connection, get_database_url, init_db
from src.shared.llm.router import router as llm_router
from src.shared.security.config import (
    security_fail_closed,
    security_headers_enabled,
    security_max_request_bytes,
)
from src.shared.security.hardening import validate_security_posture
from src.shared.security.middleware import (
    BrowserOriginGuardMiddleware,
    LocalOnlyRequestMiddleware,
    RequestBodyLimitMiddleware,
    SecurityHeadersMiddleware,
)
from src.shared.security.router import router as security_router
from src.shared.vision.router import router as vision_router

from src.modules.projects.history import get_project_history
from src.shared.version import get_version_info

settings = get_settings()
app = FastAPI(title=settings.app_name)
register_exception_handlers(app)

trusted_hosts = list(settings.trusted_hosts_list)
if settings.env == "local":
    trusted_hosts.extend(["test", "testserver"])
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=sorted(set(trusted_hosts or ["localhost", "127.0.0.1"])),
)
if settings.cors_origins_list:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Accept", "Content-Type", "X-Requested-With"],
    )
app.add_middleware(LocalOnlyRequestMiddleware)
app.add_middleware(BrowserOriginGuardMiddleware)
app.add_middleware(RequestBodyLimitMiddleware, max_bytes=security_max_request_bytes())
if security_headers_enabled():
    app.add_middleware(SecurityHeadersMiddleware)


@app.on_event("startup")
def on_startup():
    _setup_logging()
    _prepare_local_directories()
    posture = validate_security_posture()
    if security_fail_closed() and posture.blocking_errors:
        details = "; ".join(f"{item.key}: {item.message}" for item in posture.blocking_errors)
        raise RuntimeError(f"Security posture blocked startup: {details}")
    init_db()


def _prepare_local_directories():
    for raw in (settings.storage_root, settings.exports_root, settings.backup_root):
        Path(raw).expanduser().mkdir(parents=True, exist_ok=True)
    if settings.database_url.startswith("sqlite:///"):
        database_path = Path(settings.database_url.removeprefix("sqlite:///"))
        if database_path.parent != Path(""):
            database_path.parent.mkdir(parents=True, exist_ok=True)


def _setup_logging():
    current = get_settings()
    level = getattr(logging, current.log_level.upper(), logging.INFO)
    handlers = [logging.StreamHandler(sys.stdout)]
    if current.log_file:
        handlers.append(logging.FileHandler(current.log_file))
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=handlers,
    )
    if current.log_format == "plain":
        logging.getLogger().handlers[0].setFormatter(
            logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
        )


remove_legacy_ui_auth_routes(ui_router)

app.include_router(agent_registry_router)
app.include_router(creative_assets_router)
app.include_router(brand_profiles_router)
app.include_router(audience_profiles_router)
app.include_router(test_rubrics_router)
app.include_router(test_runs_router)
app.include_router(report_generator_router)
app.include_router(audit_log_router)
app.include_router(auth_ui_router)
app.include_router(ui_router)
app.include_router(llm_router)
app.include_router(vision_router, prefix="/vision")
app.include_router(clients_router)
app.include_router(projects_router)
app.include_router(users_router)
app.include_router(brandbooks_router)
app.include_router(knowledge_base_router)
app.include_router(export_jobs_router, prefix="/exports")
app.include_router(admin_router)
app.include_router(auth_router)
app.include_router(model_profiles_router)
app.include_router(prompt_registry_router)
app.include_router(evaluations_router)
app.include_router(prompt_traces_router)
app.include_router(reviews_router)
app.include_router(job_queue_router)
app.include_router(batches_router)
app.include_router(import_sessions_router)
app.include_router(tabular_inspection_router)
app.include_router(mapping_engine_router)
app.include_router(normalized_data_router)
app.include_router(data_quality_router)
app.include_router(clarifications_router)
app.include_router(prediction_readiness_router)
app.include_router(quantitative_surveys_router)
app.include_router(data_review_reports_router)
app.include_router(security_router)
app.include_router(demo_router)


@app.middleware("http")
async def auth_write_middleware(request, call_next):
    current = get_settings()
    if current.enable_auth and request.method in ("POST", "PUT", "PATCH", "DELETE"):
        path = request.url.path
        if path == "/":
            pass
        elif path.startswith(("/auth/login", "/auth/logout", "/ui/login", "/ui/logout")):
            pass
        else:
            from src.shared.security.auth import get_current_user_from_request
            try:
                user = get_current_user_from_request(request)
                role = user.get("role", "")
                if role not in ("admin", "manager", "analyst"):
                    from fastapi.responses import JSONResponse
                    return JSONResponse(
                        status_code=403,
                        content={"detail": f"Role '{role}' does not have write permission"},
                    )
            except Exception as exc:
                from fastapi.responses import JSONResponse
                status = getattr(exc, "status_code", 401)
                detail = getattr(exc, "detail", "Not authenticated")
                return JSONResponse(status_code=status, content={"detail": detail})
    return await call_next(request)


@app.get("/health/db")
def health_db():
    connected = check_db_connection()
    return {
        "status": "ok" if connected else "error",
        "database": "connected" if connected else "disconnected",
        "database_url": get_database_url(masked=True),
    }


@app.get("/health")
def health():
    posture = validate_security_posture()
    return {
        "status": "ok" if not posture.blocking_errors else "error",
        "app": settings.app_name,
        "local_only_mode": settings.local_only_mode,
        "security_posture": posture.status,
    }


@app.get("/version")
def version():
    return get_version_info()


@app.get("/clients/{client_id}/projects")
def get_client_projects(client_id: str):
    return list_projects_by_client(client_id)


@app.get("/projects/{project_id}/history")
def project_history(project_id: str):
    return get_project_history(project_id)


def list_projects_by_client(client_id: str):
    from src.modules.projects.service import list_projects
    return list_projects(client_id=client_id)
