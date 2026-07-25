from uuid import uuid4

import pytest

from src.modules.creative_assets.models import CreativeAsset
from src.modules.data_quality.service import generate_data_quality_report
from src.modules.import_sessions.schemas import CreateImportSessionRequest
from src.modules.import_sessions.service import add_source_file, create_import_session
from src.modules.import_sessions.tabular_service import inspect_source_file, list_source_tables
from src.modules.mapping_engine.schemas import ColumnMappingDecisionRequest
from src.modules.mapping_engine.service import decide_column_mapping, generate_mapping_suggestions
from src.modules.normalized_data.service import normalize_source_table
from src.modules.projects.models import Project
from src.shared.config.settings import get_settings
from src.shared.db.repository import db_session


@pytest.fixture
def isolated_data_quality_storage(tmp_path):
    settings = get_settings()
    previous_root = settings.storage_root
    previous_limit = settings.import_max_upload_size_mb
    settings.storage_root = str(tmp_path)
    settings.import_max_upload_size_mb = 10
    try:
        yield tmp_path
    finally:
        settings.storage_root = previous_root
        settings.import_max_upload_size_mb = previous_limit


def _create_project() -> str:
    project_id = str(uuid4())
    with db_session() as db:
        db.add(
            Project(
                id=project_id,
                client_id=f"client-{uuid4()}",
                name=f"Data quality project {uuid4()}",
            )
        )
    return project_id


def _prepare_table(project_id: str, content: bytes):
    session = create_import_session(
        CreateImportSessionRequest(project_id=project_id, name=f"Delivery {uuid4()}")
    )
    source = add_source_file(session.id, "history.csv", content, "text/csv")
    inspection = inspect_source_file(session.id, source.id)
    assert inspection.status == "completed"
    table = list_source_tables(session.id, source.id)[0]
    mapping = generate_mapping_suggestions(session.id, source.id, table.id)
    return session, source, table, mapping


def _confirm_mappings(session, source, table, mapping, targets: dict[str, str]):
    by_header = {item.normalized_header: item for item in mapping.columns}
    for header, target in targets.items():
        decide_column_mapping(
            session.id,
            source.id,
            table.id,
            by_header[header].source_column_id,
            ColumnMappingDecisionRequest(status="confirmed", target_field=target),
            decided_by_user_id="data-quality-test-user",
        )


def test_data_quality_report_aggregates_all_required_categories(
    isolated_data_quality_storage,
):
    project_id = _create_project()
    with db_session() as db:
        db.add(
            CreativeAsset(
                id=str(uuid4()),
                title="Known banner",
                asset_type="image",
                original_filename="banner.png",
                project_id=project_id,
            )
        )

    session, source, table, mapping = _prepare_table(
        project_id,
        (
            "Campaign,Creative,Platform,Placement,Format,Date,Impressions,Clicks,CTR,Brand,Notes\n"
            "Alpha,banner.png,Ozon,search,300x250,2026-06-01,1000,20,0.02,Brand X,ok\n"
            "Alpha,banner.png,Ozon,search,300x250,2026-06-01,1000,20,0.02,Brand X,ok\n"
            "Beta,missing.png,,search,300x250,2026-06-02,0,3,5%,Brand X,bad\n"
            "Gamma,missing2.png,Yandex,search,728x90,2026-06-03,-5,-1,-0.2,Brand X,negative\n"
            "Delta,missing3.png,Yandex,search,300x250,2026-06-04,1000,20,2,Brand X,scale\n"
        ).encode("utf-8"),
    )
    _confirm_mappings(
        session,
        source,
        table,
        mapping,
        {
            "campaign": "campaign_reference",
            "creative": "creative_reference",
            "platform": "platform",
            "placement": "placement_type",
            "format": "format",
            "date": "date",
            "impressions": "impressions",
            "clicks": "clicks",
            "ctr": "ctr",
            "brand": "brand",
        },
    )
    normalization = normalize_source_table(session.id, source.id, table.id)
    assert normalization.run.source_row_count == 5

    result = generate_data_quality_report(session.id, source.id, table.id)

    assert result.run.overall_status == "blocked"
    assert result.run.source_file_count == 1
    assert result.run.source_table_count == 1
    assert result.run.source_row_count == 5
    assert result.run.confirmed_mapping_count == 10
    assert result.run.unmapped_mapping_count == 1
    assert result.run.creative_record_count == 4
    assert result.run.linked_creative_count == 1
    assert result.run.unlinked_creative_count == 3
    assert result.run.performance_observation_count == 5
    assert result.run.blocking_issue_count >= 4

    codes = {item.code for item in result.issues}
    assert {
        "source_files_verified",
        "duplicate_source_rows",
        "duplicate_performance_observations",
        "creative_assets_unlinked",
        "missing_platform",
        "negative_impressions",
        "negative_clicks",
        "negative_ctr",
        "clicks_with_zero_impressions",
        "ctr_percent_scale_suspected",
    } <= codes

    assert set(result.run.category_counts) == {
        "file_integrity",
        "schema_detection",
        "mapping",
        "missing_values",
        "duplicates",
        "creative_linking",
        "metric_consistency",
        "prediction_readiness",
    }
    assert result.run.summary["prediction_decision"] == "not_evaluated_in_cta_pre_006"
    metric_issue = next(item for item in result.issues if item.code == "negative_impressions")
    assert metric_issue.source_table_id == table.id
    assert metric_issue.affected_count == 1


def test_data_quality_can_report_pipeline_blockers_before_normalization(
    isolated_data_quality_storage,
):
    project_id = _create_project()
    session, source, table, mapping = _prepare_table(
        project_id,
        b"Campaign,Creative\nAlpha,banner.png\n",
    )
    _confirm_mappings(
        session,
        source,
        table,
        mapping,
        {
            "campaign": "campaign_reference",
            "creative": "creative_reference",
        },
    )

    result = generate_data_quality_report(session.id, source.id, table.id)

    assert result.run.overall_status == "blocked"
    assert result.run.normalization_run_id is None
    assert result.run.summary["readiness_indicators"]["normalization_available"] is False
    assert "normalization_not_available" in {item.code for item in result.issues}


def test_data_quality_rejects_stale_normalization_after_mapping_change(
    isolated_data_quality_storage,
):
    project_id = _create_project()
    session, source, table, mapping = _prepare_table(
        project_id,
        b"Campaign,Creative,Impressions,Clicks\nAlpha,banner.png,1000,20\n",
    )
    _confirm_mappings(
        session,
        source,
        table,
        mapping,
        {
            "campaign": "campaign_reference",
            "creative": "creative_reference",
            "impressions": "impressions",
            "clicks": "clicks",
        },
    )
    first_normalization = normalize_source_table(session.id, source.id, table.id)

    by_header = {item.normalized_header: item for item in mapping.columns}
    decide_column_mapping(
        session.id,
        source.id,
        table.id,
        by_header["clicks"].source_column_id,
        ColumnMappingDecisionRequest(status="confirmed", target_field="ctr"),
        decided_by_user_id="data-quality-test-user",
    )

    stale = generate_data_quality_report(session.id, source.id, table.id)

    assert stale.run.overall_status == "blocked"
    assert stale.run.normalization_run_id is None
    assert stale.run.normalized_row_count == 0
    assert stale.run.partial_row_count == 0
    assert stale.run.performance_observation_count == 0
    assert stale.run.summary["readiness_indicators"]["normalization_available"] is False
    assert (
        stale.run.summary["readiness_indicators"]["normalization_matches_current_mapping"]
        is False
    )
    assert stale.run.summary["lineage"]["selected_normalization_run_id"] is None
    assert (
        stale.run.summary["lineage"]["latest_completed_normalization_run_id"]
        == first_normalization.run.id
    )
    assert (
        stale.run.summary["lineage"]["current_mapping_fingerprint"]
        != first_normalization.run.mapping_fingerprint
    )
    stale_issue = next(
        item
        for item in stale.issues
        if item.code == "normalization_stale_for_current_mapping"
    )
    assert stale_issue.severity == "blocking"
    assert (
        stale_issue.details["latest_completed_normalization_run_id"]
        == first_normalization.run.id
    )

    refreshed_normalization = normalize_source_table(session.id, source.id, table.id)
    refreshed = generate_data_quality_report(
        session.id,
        source.id,
        table.id,
        force=True,
    )

    assert refreshed.run.normalization_run_id == refreshed_normalization.run.id
    assert refreshed.run.summary["readiness_indicators"]["normalization_available"] is True
    assert refreshed.run.summary["lineage"]["current_mapping_fingerprint"] == (
        refreshed_normalization.run.mapping_fingerprint
    )
    assert "normalization_stale_for_current_mapping" not in {
        item.code for item in refreshed.issues
    }


def test_forced_reinspection_does_not_inflate_active_source_table_count(
    isolated_data_quality_storage,
):
    project_id = _create_project()
    session, source, first_table, _first_mapping = _prepare_table(
        project_id,
        b"Campaign,Creative\nAlpha,banner.png\n",
    )

    second_inspection = inspect_source_file(session.id, source.id, force=True)
    assert second_inspection.inspection_number == 2
    second_table = list_source_tables(session.id, source.id)[0]
    assert second_table.id != first_table.id
    second_mapping = generate_mapping_suggestions(session.id, source.id, second_table.id)
    _confirm_mappings(
        session,
        source,
        second_table,
        second_mapping,
        {
            "campaign": "campaign_reference",
            "creative": "creative_reference",
        },
    )
    normalize_source_table(session.id, source.id, second_table.id)

    result = generate_data_quality_report(session.id, source.id, second_table.id)

    assert result.run.source_table_count == 1
    assert result.run.summary["coverage"]["source_tables"] == 1

