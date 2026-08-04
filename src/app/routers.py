"""Central router registry for the application factory."""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import APIRouter, FastAPI

from src.app.system_router import router as system_router
from src.modules.admin.router import router as admin_router
from src.modules.agent_registry.router import router as agent_registry_router
from src.modules.audit_log.router import router as audit_log_router
from src.modules.audience_profiles.router import router as audience_profiles_router
from src.modules.auth.router import router as auth_router
from src.modules.auth.ui_router import router as auth_ui_router
from src.modules.batches.router import router as batches_router
from src.modules.brand_profiles.router import router as brand_profiles_router
from src.modules.brandbooks.router import router as brandbooks_router
from src.modules.calibration_dashboard.router import router as calibration_dashboard_router
from src.modules.calibration_dashboard.ui_router import router as calibration_dashboard_ui_router
from src.modules.campaign_evidence.router import router as campaign_evidence_router
from src.modules.campaign_evidence.ui_router import router as campaign_evidence_ui_router
from src.modules.clarifications.router import router as clarifications_router
from src.modules.client_one_page_reports.router import router as client_one_page_reports_router
from src.modules.clients.router import router as clients_router
from src.modules.creative_assets.router import router as creative_assets_router
from src.modules.data_quality.router import router as data_quality_router
from src.modules.data_review_reports.router import router as data_review_reports_router
from src.modules.demo.router import router as demo_router
from src.modules.evaluations.router import router as evaluations_router
from src.modules.export_jobs.router import router as export_jobs_router
from src.modules.finding_reviews.router import router as finding_reviews_router
from src.modules.finding_reviews.ui_router import router as finding_reviews_ui_router
from src.modules.import_sessions.router import router as import_sessions_router
from src.modules.import_sessions.tabular_router import router as tabular_inspection_router
from src.modules.job_queue.router import router as job_queue_router
from src.modules.knowledge_base.router import router as knowledge_base_router
from src.modules.mapping_engine.router import router as mapping_engine_router
from src.modules.model_profiles.router import router as model_profiles_router
from src.modules.normalized_data.router import router as normalized_data_router
from src.modules.pilot_intake.router import router as pilot_intake_router
from src.modules.pilot_intake.ui_router import router as pilot_intake_ui_router
from src.modules.pilot_workspace.router import router as pilot_workspace_router
from src.modules.prediction_readiness.router import router as prediction_readiness_router
from src.modules.projects.router import router as projects_router
from src.modules.prompt_registry.router import router as prompt_registry_router
from src.modules.prompt_traces.router import router as prompt_traces_router
from src.modules.quantitative_surveys.router import router as quantitative_surveys_router
from src.modules.report_generator.router import router as report_generator_router
from src.modules.reviews.router import router as reviews_router
from src.modules.test_rubrics.router import router as test_rubrics_router
from src.modules.test_runs.router import router as test_runs_router
from src.modules.ui.router import router as ui_router
from src.modules.users.router import router as users_router
from src.shared.llm.router import router as llm_router
from src.shared.security.router import router as security_router
from src.shared.vision.router import router as vision_router


@dataclass(frozen=True, slots=True)
class RouterRegistration:
    router: APIRouter
    prefix: str = ""


ROUTERS: tuple[RouterRegistration, ...] = (
    RouterRegistration(system_router),
    RouterRegistration(agent_registry_router),
    RouterRegistration(creative_assets_router),
    RouterRegistration(brand_profiles_router),
    RouterRegistration(audience_profiles_router),
    RouterRegistration(test_rubrics_router),
    RouterRegistration(test_runs_router),
    RouterRegistration(report_generator_router),
    RouterRegistration(audit_log_router),
    RouterRegistration(auth_ui_router),
    RouterRegistration(ui_router),
    RouterRegistration(campaign_evidence_ui_router),
    RouterRegistration(finding_reviews_ui_router),
    RouterRegistration(calibration_dashboard_ui_router),
    RouterRegistration(pilot_intake_ui_router),
    RouterRegistration(pilot_workspace_router),
    RouterRegistration(llm_router),
    RouterRegistration(vision_router, prefix="/vision"),
    RouterRegistration(clients_router),
    RouterRegistration(projects_router),
    RouterRegistration(users_router),
    RouterRegistration(brandbooks_router),
    RouterRegistration(knowledge_base_router),
    RouterRegistration(export_jobs_router, prefix="/exports"),
    RouterRegistration(admin_router),
    RouterRegistration(auth_router),
    RouterRegistration(model_profiles_router),
    RouterRegistration(prompt_registry_router),
    RouterRegistration(evaluations_router),
    RouterRegistration(prompt_traces_router),
    RouterRegistration(reviews_router),
    RouterRegistration(finding_reviews_router),
    RouterRegistration(calibration_dashboard_router),
    RouterRegistration(pilot_intake_router),
    RouterRegistration(job_queue_router),
    RouterRegistration(batches_router),
    RouterRegistration(import_sessions_router),
    RouterRegistration(tabular_inspection_router),
    RouterRegistration(mapping_engine_router),
    RouterRegistration(normalized_data_router),
    RouterRegistration(data_quality_router),
    RouterRegistration(clarifications_router),
    RouterRegistration(prediction_readiness_router),
    RouterRegistration(quantitative_surveys_router),
    RouterRegistration(data_review_reports_router),
    RouterRegistration(client_one_page_reports_router),
    RouterRegistration(campaign_evidence_router),
    RouterRegistration(security_router),
    RouterRegistration(demo_router),
)


def register_routers(app: FastAPI) -> None:
    for registration in ROUTERS:
        app.include_router(
            registration.router,
            prefix=registration.prefix,
        )
