from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pptx import Presentation

from scripts.client_one_page_report import _sample_context, _sample_survey
from src.modules.clients.models import Client
from src.modules.client_one_page_reports.models import ClientOnePageReportRun
from src.modules.client_one_page_reports.rendering import (
    build_report_bundle,
    compose_report_evidence,
    determine_verdict,
    validate_report_bundle,
)
from src.modules.client_one_page_reports.service import generate_client_one_page_report
from src.modules.data_quality.models import DataQualityIssue, DataQualityRun
from src.modules.import_sessions.models import ImportSourceFile, SourceTable
from src.modules.prediction_readiness.models import (
    PredictionCapabilityReadiness,
    PredictionReadinessRun,
)
from src.modules.projects.models import Project
from src.shared.db.repository import db_session
from src.shared.errors import AppError


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_verdict_is_a_workflow_state_not_a_creative_score():
    assert determine_verdict("blocked", "ready") == "blocked"
    assert determine_verdict("passed", "unavailable") == "evidence_limited"
    assert determine_verdict("review_required", "ready") == "review_required"
    assert determine_verdict("passed", "degraded") == "review_required"
    assert determine_verdict("passed", "ready") == "controlled_review_ready"


def test_renderer_produces_one_slide_one_page_and_labelled_synthetic_evidence(tmp_path: Path):
    evidence = compose_report_evidence(
        _sample_context(),
        locale="ru",
        survey=_sample_survey(),
        generated_at="2026-07-24T20:00:00+00:00",
    )
    manifest = build_report_bundle(evidence, tmp_path)

    assert validate_report_bundle(tmp_path) == []
    assert manifest["slide_count"] == 1
    assert manifest["page_count"] == 1
    assert manifest["prediction_generated"] is False
    assert len(Presentation(tmp_path / "client_one_page_report.pptx").slides) == 1

    stored = json.loads((tmp_path / "client_one_page_report_evidence.json").read_text("utf-8"))
    assert stored["survey"]["evidence_type"] == "synthetic_proxy"
    assert stored["survey"]["real_human_response_count"] == 0
    assert stored["claim_boundary"]["composite_score_generated"] is False
    assert stored["claim_boundary"]["causal_creative_lift_estimated"] is False
    assert stored["claim_boundary"]["technical_readiness_is_not_model_accuracy"] is True


def _persist_report_context(tmp_path: Path, *, with_readiness: bool = True) -> tuple[str, str]:
    suffix = uuid4().hex
    source_path = tmp_path / f"source-{suffix}.csv"
    source_path.write_bytes(b"creative,impressions,clicks\nA,100,2\n")
    client_id = f"client-{suffix}"
    project_id = f"project-{suffix}"
    source_file_id = f"file-{suffix}"
    source_table_id = f"table-{suffix}"
    dq_id = f"dq-{suffix}"

    with db_session() as db:
        db.add(Client(id=client_id, name="Fictional client"))
        db.add(Project(id=project_id, client_id=client_id, name=f"Pilot {suffix}"))
        db.add(
            ImportSourceFile(
                id=source_file_id,
                import_session_id=f"session-{suffix}",
                project_id=project_id,
                original_filename="history.csv",
                extension="csv",
                declared_mime_type="text/csv",
                file_size_bytes=source_path.stat().st_size,
                sha256=_sha(source_path),
                storage_path=str(source_path),
            )
        )
        db.add(
            SourceTable(
                id=source_table_id,
                inspection_id=f"inspection-{suffix}",
                source_file_id=source_file_id,
                sheet_index=0,
                sheet_name="history",
                header_row_number=1,
                header_confidence=1.0,
                source_row_count=2,
                data_row_count=1,
                column_count=3,
            )
        )
        db.add(
            DataQualityRun(
                id=dq_id,
                source_table_id=source_table_id,
                source_file_id=source_file_id,
                import_session_id=f"session-{suffix}",
                project_id=project_id,
                normalization_run_id=f"normalization-{suffix}",
                run_number=1,
                engine_name="test-dq",
                engine_version="1.0.0",
                input_fingerprint="d" * 64,
                status="completed",
                overall_status="review_required",
                source_file_count=1,
                source_table_count=1,
                source_row_count=1,
                source_column_count=3,
                confirmed_mapping_count=3,
                normalized_row_count=1,
                creative_record_count=1,
                linked_creative_count=1,
                performance_observation_count=1,
                warning_issue_count=1,
                total_issue_count=1,
            )
        )
        db.add(
            DataQualityIssue(
                id=f"issue-{suffix}",
                data_quality_run_id=dq_id,
                category="prediction_readiness",
                code="small_sample",
                severity="warning",
                scope_type="run",
                affected_count=1,
                message="Historical sample is too small for a validated forecast.",
                remediation_hint="Add comparable historical observations.",
            )
        )
        if with_readiness:
            readiness_id = f"readiness-{suffix}"
            db.add(
                PredictionReadinessRun(
                    id=readiness_id,
                    data_quality_run_id=dq_id,
                    source_table_id=source_table_id,
                    source_file_id=source_file_id,
                    import_session_id=f"session-{suffix}",
                    project_id=project_id,
                    run_number=1,
                    evaluator_name="test-readiness",
                    evaluator_version="1.0.0",
                    input_fingerprint="r" * 64,
                    status="completed",
                    overall_status="degraded",
                    capability_count=1,
                    degraded_count=1,
                )
            )
            db.add(
                PredictionCapabilityReadiness(
                    id=f"capability-{suffix}",
                    prediction_readiness_run_id=readiness_id,
                    capability_key="historical_ctr_prediction",
                    status="degraded",
                    mode="calibration_only",
                    evidence_strength="weak",
                    title="Historical CTR prediction",
                    user_message="Historical comparison is directional only.",
                    internal_message="No accuracy claim is permitted.",
                    missing_inputs_json=json.dumps(["Comparable history"]),
                    prohibited_operations_json=json.dumps(["Validated accuracy claim"]),
                )
            )
    return dq_id, str(source_path)


def test_service_is_idempotent_force_versioned_and_integrity_checked(tmp_path: Path, monkeypatch):
    dq_id, source_path = _persist_report_context(tmp_path)
    import src.modules.client_one_page_reports.service as service

    monkeypatch.setattr(service, "get_settings", lambda: SimpleNamespace(storage_root=str(tmp_path)))

    first = generate_client_one_page_report(dq_id, locale="ru")
    repeated = generate_client_one_page_report(dq_id, locale="ru")
    forced = generate_client_one_page_report(dq_id, locale="ru", force=True)

    assert repeated.id == first.id
    assert forced.id != first.id
    assert first.run_number == 1
    assert forced.run_number == 2
    assert first.slide_count == 1
    assert {item.artifact_type for item in first.artifacts} == {"pptx", "html", "evidence"}
    assert first.summary["claim_boundary"]["prediction_generated"] is False

    with db_session() as db:
        assert db.query(ClientOnePageReportRun).filter(
            ClientOnePageReportRun.data_quality_run_id == dq_id
        ).count() == 2

    Path(source_path).write_bytes(b"tampered")
    with pytest.raises(AppError) as exc:
        generate_client_one_page_report(dq_id, locale="en", force=True)
    assert exc.value.code == "source_file_integrity_failed"


def test_service_requires_completed_prediction_readiness(tmp_path: Path, monkeypatch):
    dq_id, _ = _persist_report_context(tmp_path, with_readiness=False)
    import src.modules.client_one_page_reports.service as service

    monkeypatch.setattr(service, "get_settings", lambda: SimpleNamespace(storage_root=str(tmp_path)))
    with pytest.raises(AppError) as exc:
        generate_client_one_page_report(dq_id)
    assert exc.value.code == "prediction_readiness_required"
