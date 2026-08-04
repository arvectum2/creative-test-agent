"""Deterministic stages of the executable PRE-TZ demonstration."""

from __future__ import annotations

import hashlib
from pathlib import Path

from src.modules.pre_tz_demo.contracts import (
    DemoAnalysis,
    DemoFoundation,
    DemoImportedSource,
    DemoReport,
    DemoRun,
    DemoSurvey,
)
from src.modules.pre_tz_demo.workspace import DemoPaths

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


def execute_demo(paths: DemoPaths, *, respondent_count: int) -> DemoRun:
    foundation = _create_foundation()
    imported = _import_source(paths, foundation)
    analysis = _analyze_source(imported)
    survey = _run_synthetic_survey(foundation, respondent_count=respondent_count)
    report = _generate_report(analysis, survey)
    return DemoRun(
        foundation=foundation,
        imported=imported,
        analysis=analysis,
        survey=survey,
        report=report,
    )


def _create_foundation() -> DemoFoundation:
    from src.modules.clients.schemas import CreateClientRequest
    from src.modules.clients.service import create_client
    from src.modules.creative_assets.schemas import CreateCreativeAssetRequest
    from src.modules.creative_assets.service import create_asset
    from src.modules.projects.schemas import CreateProjectRequest
    from src.modules.projects.service import create_project

    client = create_client(
        CreateClientRequest(
            name="CTA PRE-TZ Messy Demo Client",
            industry="pharma-demo",
            description=(
                "Synthetic local-only client used only for executable PRE-TZ "
                "verification."
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
    return DemoFoundation(
        client=client,
        project=project,
        asset_a=asset_a,
        asset_b=asset_b,
    )


def _import_source(paths: DemoPaths, foundation: DemoFoundation) -> DemoImportedSource:
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

    import_session = create_import_session(
        CreateImportSessionRequest(
            project_id=foundation.project.id,
            name="Messy campaign export",
            notes="Deliberately inconsistent CSV used by CTA-PRE-012.",
            metadata={"demo_version": DEMO_VERSION, "fixture": paths.fixture.name},
        )
    )
    source_bytes = paths.fixture.read_bytes()
    source_file = add_source_file(
        import_session.id,
        paths.fixture.name,
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
    return DemoImportedSource(
        completed_session=completed_session,
        source_file=source_file,
        source_bytes=source_bytes,
        integrity=integrity,
        inspection=inspection,
        table=table,
        table_detail=table_detail,
    )


def _analyze_source(imported: DemoImportedSource) -> DemoAnalysis:
    from src.modules.clarifications.service import generate_clarifications
    from src.modules.data_quality.service import generate_data_quality_report
    from src.modules.mapping_engine.schemas import ColumnMappingDecisionRequest
    from src.modules.mapping_engine.service import (
        decide_column_mapping,
        generate_mapping_suggestions,
        get_table_mapping,
    )
    from src.modules.normalized_data.service import normalize_source_table
    from src.modules.prediction_readiness.service import evaluate_prediction_readiness

    session_id = imported.completed_session.id
    source_file_id = imported.source_file.id
    table_id = imported.table.id

    generate_mapping_suggestions(
        session_id,
        source_file_id,
        table_id,
        force=True,
    )
    mapping_before = get_table_mapping(session_id, source_file_id, table_id)
    confirmed_headers: list[str] = []
    for column in mapping_before.columns:
        target = _HEADER_TARGETS.get(column.source_header or "")
        if target is None:
            continue
        decide_column_mapping(
            session_id,
            source_file_id,
            table_id,
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

    mapping = get_table_mapping(session_id, source_file_id, table_id)
    if mapping.confirmed_columns != len(_HEADER_TARGETS):
        raise RuntimeError(
            f"Expected {len(_HEADER_TARGETS)} confirmed mappings, "
            f"got {mapping.confirmed_columns}"
        )

    normalization = normalize_source_table(
        session_id,
        source_file_id,
        table_id,
        force=True,
    )
    quality = generate_data_quality_report(
        session_id,
        source_file_id,
        table_id,
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
    return DemoAnalysis(
        confirmed_headers=confirmed_headers,
        mapping=mapping,
        normalization=normalization,
        quality=quality,
        client_questions=client_questions,
        analyst_questions=analyst_questions,
        readiness=readiness,
    )


def _run_synthetic_survey(
    foundation: DemoFoundation,
    *,
    respondent_count: int,
) -> DemoSurvey:
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

    questionnaire = create_questionnaire(
        CreateQuestionnaireRequest(
            project_id=foundation.project.id,
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
            questions=_question_configs(QuestionConfig),
        )
    )
    questionnaire = publish_questionnaire(questionnaire.id)
    study = create_study(
        CreateStudyRequest(
            project_id=foundation.project.id,
            questionnaire_id=questionnaire.id,
            name="CTA-PRE-012 deterministic synthetic study",
            target_response_count=respondent_count,
            creative_asset_ids=[foundation.asset_a.id, foundation.asset_b.id],
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
            creative_effects={
                foundation.asset_a.id: 0.25,
                foundation.asset_b.id: -0.10,
            },
        ),
    )
    study = close_study(study.id)
    return DemoSurvey(
        questionnaire=questionnaire,
        study=study,
        synthetic_responses=synthetic_responses,
        results=study_results(study.id),
    )


def _question_configs(question_config):
    return [
        question_config(
            code="click_intent",
            prompt="Насколько вероятно, что вы нажмёте на этот баннер?",
            question_type="likert",
            metric_key="click_intent",
            scale_min=1,
            scale_max=7,
            low_label="Совсем не вероятно",
            high_label="Очень вероятно",
        ),
        question_config(
            code="message_clarity",
            prompt="Насколько понятно основное сообщение?",
            question_type="likert",
            metric_key="message_clarity",
            scale_min=1,
            scale_max=7,
            low_label="Совсем непонятно",
            high_label="Полностью понятно",
        ),
        question_config(
            code="brand_fit",
            prompt="Насколько креатив соответствует бренду?",
            question_type="likert",
            metric_key="brand_fit",
            scale_min=1,
            scale_max=7,
            low_label="Не соответствует",
            high_label="Полностью соответствует",
        ),
    ]


def _generate_report(analysis: DemoAnalysis, survey: DemoSurvey) -> DemoReport:
    from src.modules.data_review_reports.service import (
        data_review_report_path,
        generate_data_review_report,
    )

    report = generate_data_review_report(
        analysis.quality.run.id,
        prediction_readiness_run_id=analysis.readiness.run.id,
        quantitative_study_id=survey.study.id,
        force=True,
    )
    report_path, report_filename = data_review_report_path(report.id)
    path = Path(report_path)
    verified_sha256 = _sha256_file(path)
    if verified_sha256 != report.sha256:
        raise RuntimeError("Generated report SHA-256 mismatch")
    return DemoReport(
        record=report,
        path=path,
        filename=report_filename,
        verified_sha256=verified_sha256,
    )


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
