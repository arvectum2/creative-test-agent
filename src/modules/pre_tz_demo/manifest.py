"""Manifest serialization for the executable PRE-TZ demo."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from src.modules.pre_tz_demo.contracts import DemoRun
from src.modules.pre_tz_demo.pipeline import DEMO_VERSION, _HEADER_TARGETS
from src.modules.pre_tz_demo.workspace import DemoPaths


def build_manifest(paths: DemoPaths, run: DemoRun) -> dict[str, Any]:
    foundation = run.foundation
    imported = run.imported
    analysis = run.analysis
    survey = run.survey
    report = run.report

    custom_headers = [
        column.source_header or column.normalized_header
        for column in imported.table_detail.columns
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
        for item in analysis.readiness.capabilities
    }

    return {
        "demo": "CTA-PRE-012",
        "demo_version": DEMO_VERSION,
        "status": "completed",
        "workspace": str(paths.workspace),
        "fixture": {
            "path": str(paths.fixture),
            "filename": paths.fixture.name,
            "sha256": hashlib.sha256(imported.source_bytes).hexdigest(),
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
        "client": {
            "id": foundation.client.id,
            "name": foundation.client.name,
        },
        "project": {
            "id": foundation.project.id,
            "name": foundation.project.name,
        },
        "creative_assets": [
            {"id": foundation.asset_a.id, "title": foundation.asset_a.title},
            {"id": foundation.asset_b.id, "title": foundation.asset_b.title},
        ],
        "import": {
            "session_id": imported.completed_session.id,
            "session_status": imported.completed_session.status,
            "source_file_id": imported.source_file.id,
            "source_sha256": imported.source_file.sha256,
            "integrity_ok": imported.integrity.ok,
            "file_count": imported.completed_session.file_count,
        },
        "inspection": {
            "id": imported.inspection.id,
            "status": imported.inspection.status,
            "format": imported.inspection.file_format,
            "encoding": imported.inspection.encoding,
            "delimiter": imported.inspection.delimiter,
            "table_id": imported.table.id,
            "header_row_number": imported.table.header_row_number,
            "source_rows": imported.table.source_row_count,
            "data_rows": imported.table.data_row_count,
            "columns": imported.table.column_count,
            "warnings": imported.inspection.warnings + imported.table.warnings,
        },
        "mapping": {
            "run_id": analysis.mapping.run.id if analysis.mapping.run else None,
            "confirmed_count": analysis.mapping.confirmed_columns,
            "confirmed_headers": analysis.confirmed_headers,
            "suggested_count": analysis.mapping.suggested_columns,
            "unmapped_count": analysis.mapping.unmapped_columns,
            "custom_headers_preserved": custom_headers,
        },
        "normalization": {
            "run_id": analysis.normalization.run.id,
            "status": analysis.normalization.run.status,
            "source_rows": analysis.normalization.run.source_row_count,
            "normalized_rows": analysis.normalization.run.normalized_row_count,
            "partial_rows": analysis.normalization.run.partial_row_count,
            "creative_records": analysis.normalization.run.creative_count,
            "performance_observations": (
                analysis.normalization.run.performance_observation_count
            ),
            "warnings": analysis.normalization.run.warnings,
        },
        "data_quality": {
            "run_id": analysis.quality.run.id,
            "overall_status": analysis.quality.run.overall_status,
            "total_issues": analysis.quality.run.total_issue_count,
            "info_issues": analysis.quality.run.info_issue_count,
            "warning_issues": analysis.quality.run.warning_issue_count,
            "blocking_issues": analysis.quality.run.blocking_issue_count,
            "issue_codes": sorted({item.code for item in analysis.quality.issues}),
        },
        "clarifications": {
            "client_run_id": analysis.client_questions.run.id,
            "client_question_count": analysis.client_questions.run.question_count,
            "client_questions": _question_summary(analysis.client_questions),
            "analyst_run_id": analysis.analyst_questions.run.id,
            "analyst_question_count": analysis.analyst_questions.run.question_count,
            "analyst_questions": _question_summary(analysis.analyst_questions),
        },
        "prediction_readiness": {
            "run_id": analysis.readiness.run.id,
            "overall_status": analysis.readiness.run.overall_status,
            "prediction_generated": analysis.readiness.run.summary.get(
                "prediction_generated",
                False,
            ),
            "capabilities": capability_summary,
        },
        "quantitative_proxy": {
            "questionnaire_id": survey.questionnaire.id,
            "study_id": survey.study.id,
            "study_status": survey.study.status,
            "target_response_count": survey.study.target_response_count,
            "response_count": survey.study.response_count,
            "generated_response_count": len(survey.synthetic_responses),
            "source_counts": survey.results.source_counts,
            "metric_keys": survey.results.metric_keys,
            "not_real_people": True,
            "interpretation_notes": survey.results.interpretation_notes,
        },
        "report": {
            "id": report.record.id,
            "filename": report.filename,
            "path": str(report.path),
            "path_relative_to_workspace": str(
                report.path.relative_to(paths.workspace)
            ),
            "sha256": report.record.sha256,
            "verified_sha256": report.verified_sha256,
            "file_size_bytes": report.record.file_size_bytes,
            "sheet_count": report.record.sheet_count,
            "status": report.record.status,
        },
    }


def failure_manifest(paths: DemoPaths, error: Exception) -> dict[str, Any]:
    return {
        "demo": "CTA-PRE-012",
        "demo_version": DEMO_VERSION,
        "status": "failed",
        "workspace": str(paths.workspace),
        "error_type": type(error).__name__,
        "error": str(error),
    }


def write_manifest(paths: DemoPaths, manifest: dict[str, Any]) -> None:
    paths.manifest.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _question_summary(result) -> list[dict[str, Any]]:
    return [
        {
            "key": item.question_key,
            "priority": item.priority,
            "text": item.question_text,
            "issue_codes": item.issue_codes,
        }
        for item in result.questions
    ]
