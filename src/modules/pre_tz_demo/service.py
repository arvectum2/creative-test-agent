from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

DEMO_VERSION = "1.0.0"

_HEADER_TARGETS = {
    "ID кампании": "campaign_reference",
    "Креатив / файл": "creative_reference",
    "Площадка": "platform",
    "Место показа": "placement_type",
    "Формат": "format",
    "Аудитория": "audience",
    "Дата": "date",
    "Показы": "impressions",
    "Клики": "clicks",
    "CTR %": "ctr",
}


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _reset_workspace(workspace: Path) -> None:
    resolved = workspace.expanduser().resolve()
    forbidden = {Path("/").resolve(), Path.home().resolve(), Path.cwd().resolve()}
    if resolved in forbidden or len(resolved.parts) < 3:
        raise ValueError(f"Refusing to reset unsafe demo workspace: {resolved}")
    if resolved.exists():
        shutil.rmtree(resolved)
    resolved.mkdir(parents=True, exist_ok=True)


def run_messy_demo(
    workspace: str | Path,
    *,
    fixture_path: str | Path | None = None,
    reset: bool = True,
    respondent_count: int = 12,
) -> dict[str, Any]:
    """Run the complete PRE-TZ pipeline against a deliberately messy local CSV."""

    workspace_path = Path(workspace).expanduser().resolve()
    if reset:
        _reset_workspace(workspace_path)
    else:
        workspace_path.mkdir(parents=True, exist_ok=True)

    fixture = (
        Path(fixture_path).expanduser().resolve()
        if fixture_path
        else Path(__file__).resolve().parents[3]
        / "examples"
        / "pre_tz"
        / "messy_campaign_export.csv"
    )
    if not fixture.is_file():
        raise FileNotFoundError(f"Demo fixture not found: {fixture}")
    if respondent_count < 1 or respondent_count > 500:
        raise ValueError("respondent_count must be between 1 and 500")

    from src.shared.config.settings import get_settings
    from src.shared.db.session import close_db, init_db

    settings = get_settings()
    original_settings = {
        "database_url": settings.database_url,
        "storage_root": settings.storage_root,
        "exports_root": settings.exports_root,
        "backup_root": settings.backup_root,
        "local_only_mode": settings.local_only_mode,
        "allow_cloud_llm": settings.allow_cloud_llm,
        "enable_auth": settings.enable_auth,
        "host": settings.host,
        "public_base_url": settings.public_base_url,
        "trusted_hosts": settings.trusted_hosts,
        "cors_allowed_origins": settings.cors_allowed_origins,
    }

    demo_db = workspace_path / "creative_test_agent_demo.db"
    storage_root = workspace_path / "storage"
    exports_root = workspace_path / "exports"
    backup_root = workspace_path / "backups"
    for path in (storage_root, exports_root, backup_root):
        path.mkdir(parents=True, exist_ok=True)

    settings.database_url = f"sqlite:///{demo_db}"
    settings.storage_root = str(storage_root)
    settings.exports_root = str(exports_root)
    settings.backup_root = str(backup_root)
    settings.local_only_mode = True
    settings.allow_cloud_llm = False
    settings.enable_auth = False
    settings.host = "127.0.0.1"
    settings.public_base_url = "http://localhost:8000"
    settings.trusted_hosts = "localhost,127.0.0.1,test,testserver"
    settings.cors_allowed_origins = ""

    close_db()
    manifest_path = workspace_path / "demo_manifest.json"

    try:
        init_db()

        from src.modules.clients.schemas import CreateClientRequest
        from src.modules.clients.service import create_client
        from src.modules.projects.schemas import CreateProjectRequest
        from src.modules.projects.service import create_project
        from src.modules.creative_assets.schemas import CreateCreativeAssetRequest
        from src.modules.creative_assets.service import create_asset
        from src.modules.import_sessions.schemas import CreateImportSessionRequest
        from src.modules.import_sessions.service import (
            add_source_file,
            complete_import_session,
            create_import_session,
            verify_import_session,
        )
        from src.modules.import_sessions.tabular_service import (
            get_source_table_detail,
            inspect_source_file,
            list_source_tables,
        )
        from src.modules.mapping_engine.schemas import ColumnMappingDecisionRequest
        from src.modules.mapping_engine.service import (
            decide_column_mapping,
            generate_mapping_suggestions,
            get_table_mapping,
        )
        from src.modules.normalized_data.service import normalize_source_table
        from src.modules.data_quality.service import generate_data_quality_report
        from src.modules.clarifications.service import generate_clarifications
        from src.modules.prediction_readiness.service import evaluate_prediction_readiness
        from src.modules.quantitative_surveys.schemas import (
            CreateQuestionnaireRequest,
            CreateStudyRequest,
            QuestionConfig,
            SimulateStudyRequest,
        )
        from src.modules.quantitative_surveys.service import (
            close_study,
            create_questionnaire,
            create_study,
            open_study,
            publish_questionnaire,
            simulate_study,
            study_results,
        )
        from src.modules.data_review_reports.service import (
            data_review_report_path,
            generate_data_review_report,
        )

        client = create_client(
            CreateClientRequest(
                name="CTA PRE-TZ Messy Demo Client",
                industry="pharma-demo",
                description=(
                    "Synthetic local-only client used only for executable PRE-TZ verification."
                ),
            )
        )
        project = create_project(
            CreateProjectRequest(
                client_id=client.id,
                name="CTA-PRE-012 Messy Campaign Demo",
                description="Deterministic end-to-end PRE-TZ pipeline demonstration.",
            )
        )

        asset_a = create_asset(
            CreateCreativeAssetRequest(
                title="banner_A.png",
                asset_type="text",
                text_content=(
                    "Variant A: clear product message and neutral call to action."
                ),
                project_id=project.id,
                metadata={"demo": True, "variant": "A", "not_client_data": True},
            )
        )
        asset_b = create_asset(
            CreateCreativeAssetRequest(
                title="banner_B.png",
                asset_type="text",
                text_content=(
                    "Variant B: alternative headline and stronger call to action."
                ),
                project_id=project.id,
                metadata={"demo": True, "variant": "B", "not_client_data": True},
            )
        )

        import_session = create_import_session(
            CreateImportSessionRequest(
                project_id=project.id,
                name="Messy campaign export",
                notes="Deliberately inconsistent CSV used by CTA-PRE-012.",
                metadata={"demo_version": DEMO_VERSION, "fixture": fixture.name},
            )
        )
        source_bytes = fixture.read_bytes()
        source_file = add_source_file(
            import_session.id,
            fixture.name,
            source_bytes,
            content_type="text/csv",
            metadata={"demo": True, "deliberately_messy": True},
        )
        completed_session = complete_import_session(import_session.id)
        integrity = verify_import_session(import_session.id)
        if not integrity.ok:
            raise RuntimeError("Immutable source integrity verification failed")

        inspection = inspect_source_file(import_session.id, source_file.id)
        if inspection.status != "completed":
            raise RuntimeError(f"Source inspection failed: {inspection.error_code}")
        tables = list_source_tables(import_session.id, source_file.id)
        if len(tables) != 1:
            raise RuntimeError(f"Expected one CSV table, found {len(tables)}")
        table = tables[0]
        table_detail = get_source_table_detail(
            import_session.id,
            source_file.id,
            table.id,
            preview_limit=20,
        )

        generate_mapping_suggestions(
            import_session.id,
            source_file.id,
            table.id,
            force=True,
        )
        mapping_before = get_table_mapping(import_session.id, source_file.id, table.id)
        confirmed_headers: list[str] = []
        for column in mapping_before.columns:
            target = _HEADER_TARGETS.get(column.source_header or "")
            if target is None:
                continue
            decide_column_mapping(
                import_session.id,
                source_file.id,
                table.id,
                column.source_column_id,
                ColumnMappingDecisionRequest(
                    status="confirmed",
                    target_field=target,
                    rationale={
                        "decision": "deterministic_demo_confirmation",
                        "demo_version": DEMO_VERSION,
                    },
                ),
            )
            confirmed_headers.append(column.source_header or column.normalized_header)
        mapping = get_table_mapping(import_session.id, source_file.id, table.id)
        if mapping.confirmed_columns != len(_HEADER_TARGETS):
            raise RuntimeError(
                f"Expected {len(_HEADER_TARGETS)} confirmed mappings, "
                f"got {mapping.confirmed_columns}"
            )

        normalization = normalize_source_table(
            import_session.id,
            source_file.id,
            table.id,
            force=True,
        )
        quality = generate_data_quality_report(
            import_session.id,
            source_file.id,
            table.id,
            force=True,
        )
        client_questions = generate_clarifications(
            quality.run.id,
            audience="client",
            max_questions=5,
            force=True,
        )
        analyst_questions = generate_clarifications(
            quality.run.id,
            audience="analyst",
            max_questions=5,
            force=True,
        )
        readiness = evaluate_prediction_readiness(quality.run.id, force=True)

        questionnaire = create_questionnaire(
            CreateQuestionnaireRequest(
                project_id=project.id,
                name="CTA-PRE-012 quantitative proxy",
                description=(
                    "Synthetic quantitative instrument for pipeline verification only; "
                    "responses are not real respondents."
                ),
                locale="ru",
                randomize_questions=True,
                metadata={
                    "demo": True,
                    "not_real_people": True,
                    "not_market_research": True,
                },
                questions=[
                    QuestionConfig(
                        code="click_intent",
                        prompt="Насколько вероятно, что вы нажмёте на этот баннер?",
                        question_type="likert",
                        metric_key="click_intent",
                        scale_min=1,
                        scale_max=7,
                        low_label="Совсем не вероятно",
                        high_label="Очень вероятно",
                    ),
                    QuestionConfig(
                        code="message_clarity",
                        prompt="Насколько понятно основное сообщение?",
                        question_type="likert",
                        metric_key="message_clarity",
                        scale_min=1,
                        scale_max=7,
                        low_label="Совсем непонятно",
                        high_label="Полностью понятно",
                    ),
                    QuestionConfig(
                        code="brand_fit",
                        prompt="Насколько креатив соответствует бренду?",
                        question_type="likert",
                        metric_key="brand_fit",
                        scale_min=1,
                        scale_max=7,
                        low_label="Не соответствует",
                        high_label="Полностью соответствует",
                    ),
                ],
            )
        )
        questionnaire = publish_questionnaire(questionnaire.id)
        study = create_study(
            CreateStudyRequest(
                project_id=project.id,
                questionnaire_id=questionnaire.id,
                name="CTA-PRE-012 deterministic synthetic study",
                target_response_count=respondent_count,
                creative_asset_ids=[asset_a.id, asset_b.id],
                randomize_creatives=True,
                seed=12012,
                metadata={
                    "demo": True,
                    "not_real_people": True,
                    "purpose": "pipeline_verification",
                },
            )
        )
        study = open_study(study.id)
        synthetic_responses = simulate_study(
            study.id,
            SimulateStudyRequest(
                respondent_count=respondent_count,
                seed=12012,
                creative_effects={asset_a.id: 0.25, asset_b.id: -0.10},
            ),
        )
        study = close_study(study.id)
        survey_results = study_results(study.id)

        report = generate_data_review_report(
            quality.run.id,
            prediction_readiness_run_id=readiness.run.id,
            quantitative_study_id=study.id,
            force=True,
        )
        report_path, report_filename = data_review_report_path(report.id)
        report_path = Path(report_path)
        report_sha256 = _sha256_file(report_path)
        if report_sha256 != report.sha256:
            raise RuntimeError("Generated report SHA-256 mismatch")

        custom_headers = [
            column.source_header or column.normalized_header
            for column in table_detail.columns
            if (column.source_header or "") not in _HEADER_TARGETS
        ]
        capability_summary = {
            item.capability_key: {
                "status": item.status,
                "mode": item.mode,
                "evidence_strength": item.evidence_strength,
                "missing_inputs": item.missing_inputs,
                "degraded_inputs": item.degraded_inputs,
                "allowed_operations": item.allowed_operations,
                "prohibited_operations": item.prohibited_operations,
            }
            for item in readiness.capabilities
        }

        manifest = {
            "demo": "CTA-PRE-012",
            "demo_version": DEMO_VERSION,
            "status": "completed",
            "workspace": str(workspace_path),
            "fixture": {
                "path": str(fixture),
                "filename": fixture.name,
                "sha256": hashlib.sha256(source_bytes).hexdigest(),
                "deliberately_messy": True,
            },
            "safety": {
                "local_only": True,
                "cloud_llm_allowed": False,
                "prediction_generated": False,
                "fabricated_ctr_generated": False,
                "synthetic_responses_label": "synthetic",
                "synthetic_responses_are_real_people": False,
            },
            "client": {"id": client.id, "name": client.name},
            "project": {"id": project.id, "name": project.name},
            "creative_assets": [
                {"id": asset_a.id, "title": asset_a.title},
                {"id": asset_b.id, "title": asset_b.title},
            ],
            "import": {
                "session_id": completed_session.id,
                "session_status": completed_session.status,
                "source_file_id": source_file.id,
                "source_sha256": source_file.sha256,
                "integrity_ok": integrity.ok,
                "file_count": completed_session.file_count,
            },
            "inspection": {
                "id": inspection.id,
                "status": inspection.status,
                "format": inspection.file_format,
                "encoding": inspection.encoding,
                "delimiter": inspection.delimiter,
                "table_id": table.id,
                "header_row_number": table.header_row_number,
                "source_rows": table.source_row_count,
                "data_rows": table.data_row_count,
                "columns": table.column_count,
                "warnings": inspection.warnings + table.warnings,
            },
            "mapping": {
                "run_id": mapping.run.id if mapping.run else None,
                "confirmed_count": mapping.confirmed_columns,
                "confirmed_headers": confirmed_headers,
                "suggested_count": mapping.suggested_columns,
                "unmapped_count": mapping.unmapped_columns,
                "custom_headers_preserved": custom_headers,
            },
            "normalization": {
                "run_id": normalization.run.id,
                "status": normalization.run.status,
                "source_rows": normalization.run.source_row_count,
                "normalized_rows": normalization.run.normalized_row_count,
                "partial_rows": normalization.run.partial_row_count,
                "creative_records": normalization.run.creative_count,
                "performance_observations": (
                    normalization.run.performance_observation_count
                ),
                "warnings": normalization.run.warnings,
            },
            "data_quality": {
                "run_id": quality.run.id,
                "overall_status": quality.run.overall_status,
                "total_issues": quality.run.total_issue_count,
                "info_issues": quality.run.info_issue_count,
                "warning_issues": quality.run.warning_issue_count,
                "blocking_issues": quality.run.blocking_issue_count,
                "issue_codes": sorted({item.code for item in quality.issues}),
            },
            "clarifications": {
                "client_run_id": client_questions.run.id,
                "client_question_count": client_questions.run.question_count,
                "client_questions": [
                    {
                        "key": item.question_key,
                        "priority": item.priority,
                        "text": item.question_text,
                        "issue_codes": item.issue_codes,
                    }
                    for item in client_questions.questions
                ],
                "analyst_run_id": analyst_questions.run.id,
                "analyst_question_count": analyst_questions.run.question_count,
                "analyst_questions": [
                    {
                        "key": item.question_key,
                        "priority": item.priority,
                        "text": item.question_text,
                        "issue_codes": item.issue_codes,
                    }
                    for item in analyst_questions.questions
                ],
            },
            "prediction_readiness": {
                "run_id": readiness.run.id,
                "overall_status": readiness.run.overall_status,
                "prediction_generated": readiness.run.summary.get(
                    "prediction_generated", False
                ),
                "capabilities": capability_summary,
            },
            "quantitative_proxy": {
                "questionnaire_id": questionnaire.id,
                "study_id": study.id,
                "study_status": study.status,
                "target_response_count": study.target_response_count,
                "response_count": study.response_count,
                "generated_response_count": len(synthetic_responses),
                "source_counts": survey_results.source_counts,
                "metric_keys": survey_results.metric_keys,
                "not_real_people": True,
                "interpretation_notes": survey_results.interpretation_notes,
            },
            "report": {
                "id": report.id,
                "filename": report_filename,
                "path": str(report_path),
                "path_relative_to_workspace": str(
                    report_path.relative_to(workspace_path)
                ),
                "sha256": report.sha256,
                "verified_sha256": report_sha256,
                "file_size_bytes": report.file_size_bytes,
                "sheet_count": report.sheet_count,
                "status": report.status,
            },
        }
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return manifest
    except Exception as exc:
        failure = {
            "demo": "CTA-PRE-012",
            "demo_version": DEMO_VERSION,
            "status": "failed",
            "workspace": str(workspace_path),
            "error_type": type(exc).__name__,
            "error": str(exc),
        }
        manifest_path.write_text(
            json.dumps(failure, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        raise
    finally:
        close_db()
        for key, value in original_settings.items():
            setattr(settings, key, value)
