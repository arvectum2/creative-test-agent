from uuid import uuid4

import pytest

from src.modules.clarifications.lifecycle import record_clarification_response
from src.modules.clarifications.schemas import SubmitClarificationResponseRequest
from src.modules.clarifications.service import (
    generate_clarifications,
    get_clarification_run,
    list_clarification_responses,
)
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
def isolated_clarification_storage(tmp_path):
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


def _project_with_asset(filename: str = "banner.png") -> str:
    project_id = str(uuid4())
    with db_session() as db:
        db.add(
            Project(
                id=project_id,
                client_id=f"client-{uuid4()}",
                name=f"Clarification project {uuid4()}",
            )
        )
        db.add(
            CreativeAsset(
                id=str(uuid4()),
                title=filename,
                asset_type="image",
                original_filename=filename,
                project_id=project_id,
            )
        )
    return project_id


def _prepare_quality_run(project_id: str, content: bytes):
    session = create_import_session(
        CreateImportSessionRequest(project_id=project_id, name=f"Delivery {uuid4()}")
    )
    source = add_source_file(session.id, "history.csv", content, "text/csv")
    inspection = inspect_source_file(session.id, source.id)
    assert inspection.status == "completed"
    table = list_source_tables(session.id, source.id)[0]
    mapping = generate_mapping_suggestions(session.id, source.id, table.id)
    by_header = {item.normalized_header: item for item in mapping.columns}
    targets = {
        "campaign": "campaign_reference",
        "creative": "creative_reference",
        "platform": "platform",
        "placement": "placement_type",
        "format": "format",
        "date": "date",
        "impressions": "impressions",
        "clicks": "clicks",
        "ctr": "ctr",
    }
    for header, target in targets.items():
        decide_column_mapping(
            session.id,
            source.id,
            table.id,
            by_header[header].source_column_id,
            ColumnMappingDecisionRequest(status="confirmed", target_field=target),
            decided_by_user_id="clarification-test-user",
        )
    normalize_source_table(session.id, source.id, table.id)
    quality = generate_data_quality_report(session.id, source.id, table.id)
    return session, source, table, quality


def _ambiguous_quality_context():
    project_id = _project_with_asset()
    return _prepare_quality_run(
        project_id,
        (
            "Campaign,Creative,Platform,Placement,Format,Date,Impressions,Clicks,CTR\n"
            "Alpha,banner.png,Ozon,search,300x250,2026-06-01,1000,20,0.02\n"
            "Alpha,banner.png,Ozon,search,300x250,2026-06-01,1000,20,0.02\n"
            "Beta,missing.png,,search,300x250,2026-06-02,0,3,5%\n"
            "Gamma,missing2.png,Yandex,search,728x90,2026-06-03,1000,20,2\n"
        ).encode("utf-8"),
    )


def test_client_questions_are_evidence_backed_ranked_and_capped(
    isolated_clarification_storage,
):
    _session, _source, _table, quality = _ambiguous_quality_context()

    result = generate_clarifications(
        quality.run.id,
        audience="client",
        max_questions=3,
    )

    assert result.run.status == "open"
    assert result.run.question_count == 3
    assert result.run.open_question_count == 3
    assert result.run.max_questions == 3
    assert len(result.questions) == 3
    assert [item.priority_score for item in result.questions] == sorted(
        [item.priority_score for item in result.questions], reverse=True
    )
    assert [item.question_key for item in result.questions] == [
        "client.metrics.correct_impossible_values",
        "client.metrics.confirm_ctr_scale",
        "client.creatives.provide_asset_mapping",
    ]
    assert all(item.audience == "client" for item in result.questions)
    assert all(item.evidence["data_quality_run_id"] == quality.run.id for item in result.questions)
    assert all(item.evidence["data_quality_issue_ids"] for item in result.questions)
    assert all(item.impact["automatic_mutation"] is False for item in result.questions)

    repeated = generate_clarifications(
        quality.run.id,
        audience="client",
        max_questions=3,
    )
    assert repeated.run.id == result.run.id
    assert repeated.run.input_fingerprint == result.run.input_fingerprint

    forced = generate_clarifications(
        quality.run.id,
        audience="client",
        max_questions=3,
        force=True,
    )
    assert forced.run.id != result.run.id
    assert forced.run.input_fingerprint == result.run.input_fingerprint


def test_answered_batch_is_suppressed_and_next_questions_are_progressive(
    isolated_clarification_storage,
):
    _session, _source, _table, quality = _ambiguous_quality_context()
    first = generate_clarifications(quality.run.id, audience="client", max_questions=3)
    first_keys = {item.question_key for item in first.questions}

    for question in first.questions:
        answer = question.options[0]["value"] if question.options else "Confirmed"
        updated = record_clarification_response(
            question.id,
            SubmitClarificationResponseRequest(
                resolution="answered",
                answer=answer,
                note="Reviewed against the client export.",
            ),
            responded_by_user_id="analyst-1",
        )
        assert updated.status == "answered"
        assert updated.latest_response is not None
        assert updated.latest_response.response_number == 1

    resolved = get_clarification_run(first.run.id)
    assert resolved is not None
    assert resolved.run.status == "resolved"
    assert resolved.run.open_question_count == 0
    assert resolved.run.answered_question_count == 3

    second = generate_clarifications(quality.run.id, audience="client", max_questions=3)
    second_keys = {item.question_key for item in second.questions}
    assert second.run.id != first.run.id
    assert second.run.input_fingerprint != first.run.input_fingerprint
    assert second.run.suppressed_question_count >= 3
    assert not (first_keys & second_keys)
    assert second.run.question_count <= 3
    assert set(second.run.summary["suppressed_question_keys"]) >= first_keys

    first_question = first.questions[0]
    revised = record_clarification_response(
        first_question.id,
        SubmitClarificationResponseRequest(
            resolution="not_applicable",
            note="The corrected source removed the affected records.",
        ),
        responded_by_user_id="analyst-2",
    )
    assert revised.status == "not_applicable"
    assert revised.latest_response is not None
    assert revised.latest_response.response_number == 2
    history = list_clarification_responses(first_question.id)
    assert history.total == 2
    assert [item.response_number for item in history.responses] == [1, 2]


def test_generator_does_not_invent_filler_questions_for_clean_data(
    isolated_clarification_storage,
):
    project_id = _project_with_asset()
    _session, _source, _table, quality = _prepare_quality_run(
        project_id,
        (
            "Campaign,Creative,Platform,Placement,Format,Date,Impressions,Clicks,CTR\n"
            "Alpha,banner.png,Ozon,search,300x250,2026-06-01,1000,20,0.02\n"
        ).encode("utf-8"),
    )

    result = generate_clarifications(quality.run.id, audience="client", max_questions=5)

    assert result.questions == []
    assert result.run.question_count == 0
    assert result.run.status == "resolved"
    assert result.run.summary["next_action"] == "no_unresolved_questions"
