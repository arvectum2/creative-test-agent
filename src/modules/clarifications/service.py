from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func

from src.modules.clarifications.models import (
    ClarificationAnswerType,
    ClarificationAudience,
    ClarificationPriority,
    ClarificationQuestion,
    ClarificationQuestionStatus,
    ClarificationResponse,
    ClarificationRun,
    ClarificationRunStatus,
)
from src.modules.clarifications.schemas import (
    ClarificationQuestionPageResponse,
    ClarificationQuestionResponse,
    ClarificationResponsePageResponse,
    ClarificationResponseResponse,
    ClarificationResultResponse,
    ClarificationRunResponse,
    SubmitClarificationResponseRequest,
)
from src.modules.data_quality.models import DataQualityIssue, DataQualityRun, DataQualityRunStatus
from src.modules.import_sessions.models import SourceColumn, SourceTable
from src.modules.mapping_engine.models import ColumnMapping, ColumnMappingStatus
from src.shared.db.repository import db_session, json_dumps, json_loads
from src.shared.errors import AppError

GENERATOR_NAME = "progressive-clarification-generator"
GENERATOR_VERSION = "1.0.0"
_TERMINAL_STATUSES = {
    ClarificationQuestionStatus.answered,
    ClarificationQuestionStatus.not_available,
    ClarificationQuestionStatus.not_applicable,
}
_ALLOWED_RESOLUTIONS = {
    ClarificationQuestionStatus.answered,
    ClarificationQuestionStatus.deferred,
    ClarificationQuestionStatus.not_available,
    ClarificationQuestionStatus.not_applicable,
}


@dataclass
class _Candidate:
    key: str
    audience: str
    score: int
    category: str
    question_text: str
    why_needed: str
    answer_type: str
    options: list[dict[str, str]] = field(default_factory=list)
    issue_codes: list[str] = field(default_factory=list)
    issue_ids: list[str] = field(default_factory=list)
    evidence: dict[str, Any] = field(default_factory=dict)
    impact: dict[str, Any] = field(default_factory=dict)


def generate_clarifications(
    data_quality_run_id: str,
    *,
    audience: str = ClarificationAudience.client,
    max_questions: int = 5,
    force: bool = False,
    created_by_user_id: str | None = None,
) -> ClarificationResultResponse:
    audience = _validate_audience(audience)
    if max_questions < 3 or max_questions > 5:
        raise AppError(
            "invalid_clarification_limit",
            "Progressive clarification batches must request between 3 and 5 questions",
            400,
        )

    with db_session() as db:
        quality_run = (
            db.query(DataQualityRun)
            .filter(DataQualityRun.id == data_quality_run_id)
            .first()
        )
        if quality_run is None:
            raise AppError("data_quality_run_not_found", "Data-quality run not found", 404)
        if quality_run.status != DataQualityRunStatus.completed:
            raise AppError(
                "data_quality_run_not_completed",
                "Clarifications require a completed data-quality run",
                409,
            )
        source_table = (
            db.query(SourceTable)
            .filter(SourceTable.id == quality_run.source_table_id)
            .first()
        )
        if source_table is None:
            raise AppError("source_table_not_found", "Source table not found", 404)

        issues = (
            db.query(DataQualityIssue)
            .filter(DataQualityIssue.data_quality_run_id == quality_run.id)
            .order_by(
                DataQualityIssue.severity.desc(),
                DataQualityIssue.category.asc(),
                DataQualityIssue.code.asc(),
                DataQualityIssue.id.asc(),
            )
            .all()
        )
        columns = (
            db.query(SourceColumn)
            .filter(SourceColumn.source_table_id == source_table.id)
            .order_by(SourceColumn.position.asc(), SourceColumn.id.asc())
            .all()
        )
        mappings = (
            db.query(ColumnMapping)
            .filter(ColumnMapping.source_table_id == source_table.id)
            .order_by(ColumnMapping.source_column_id.asc())
            .all()
        )

        all_candidates = _build_candidates(
            quality_run=quality_run,
            source_table=source_table,
            issues=issues,
            columns=columns,
            mappings=mappings,
        )
        audience_candidates = [item for item in all_candidates if item.audience == audience]
        audience_candidates.sort(key=lambda item: (-item.score, item.category, item.key))

        resolution_history = _terminal_resolution_history(
            db,
            source_table_id=source_table.id,
            audience=audience,
        )
        suppressed_keys = {
            candidate.key for candidate in audience_candidates if candidate.key in resolution_history
        }
        unresolved_candidates = [
            candidate for candidate in audience_candidates if candidate.key not in suppressed_keys
        ]
        selected = unresolved_candidates[:max_questions]

        fingerprint_payload = {
            "generator_version": GENERATOR_VERSION,
            "data_quality": {
                "run_id": quality_run.id,
                "input_fingerprint": quality_run.input_fingerprint,
                "overall_status": quality_run.overall_status,
                "issue_ids": [item.id for item in issues],
            },
            "audience": audience,
            "max_questions": max_questions,
            "candidates": [_candidate_snapshot(item) for item in audience_candidates],
            "terminal_resolution_history": resolution_history,
        }
        input_fingerprint = hashlib.sha256(
            json.dumps(
                fingerprint_payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()

        existing = (
            db.query(ClarificationRun)
            .filter(
                ClarificationRun.source_table_id == source_table.id,
                ClarificationRun.generator_version == GENERATOR_VERSION,
                ClarificationRun.input_fingerprint == input_fingerprint,
                ClarificationRun.audience == audience,
            )
            .order_by(ClarificationRun.run_number.desc(), ClarificationRun.created_at.desc())
            .first()
        )
        if existing is not None and not force:
            return _result_response(db, existing)

        run_number = (
            db.query(func.max(ClarificationRun.run_number))
            .filter(ClarificationRun.source_table_id == source_table.id)
            .scalar()
            or 0
        ) + 1
        now = datetime.now(timezone.utc)
        run_status = (
            ClarificationRunStatus.open if selected else ClarificationRunStatus.resolved
        )
        summary = {
            "generation_policy": "evidence_backed_progressive_questions",
            "audience": audience,
            "requested_max_questions": max_questions,
            "available_candidate_count": len(audience_candidates),
            "unresolved_candidate_count": len(unresolved_candidates),
            "selected_question_keys": [item.key for item in selected],
            "suppressed_question_keys": sorted(suppressed_keys),
            "queued_for_later_count": max(len(unresolved_candidates) - len(selected), 0),
            "source_data_quality_status": quality_run.overall_status,
            "principles": [
                "Questions are generated only from persisted evidence.",
                "Previously resolved questions are not repeated for the same source table.",
                "Answers are recorded but never mutate source files, mappings or normalized data automatically.",
                "Fewer than three questions are returned when fewer material gaps exist; no filler questions are invented.",
            ],
            "next_action": "answer_open_questions" if selected else "no_unresolved_questions",
        }
        run = ClarificationRun(
            data_quality_run_id=quality_run.id,
            source_table_id=quality_run.source_table_id,
            source_file_id=quality_run.source_file_id,
            import_session_id=quality_run.import_session_id,
            project_id=quality_run.project_id,
            run_number=run_number,
            generator_name=GENERATOR_NAME,
            generator_version=GENERATOR_VERSION,
            input_fingerprint=input_fingerprint,
            audience=audience,
            max_questions=max_questions,
            status=run_status,
            candidate_count=len(audience_candidates),
            question_count=len(selected),
            suppressed_question_count=len(suppressed_keys),
            open_question_count=len(selected),
            answered_question_count=0,
            deferred_question_count=0,
            not_available_question_count=0,
            not_applicable_question_count=0,
            summary_json=json_dumps(summary),
            created_by_user_id=created_by_user_id,
            resolved_at=now if not selected else None,
        )
        db.add(run)
        db.flush()

        for rank, candidate in enumerate(selected, start=1):
            evidence = dict(candidate.evidence)
            evidence.update(
                {
                    "data_quality_run_id": quality_run.id,
                    "data_quality_input_fingerprint": quality_run.input_fingerprint,
                    "data_quality_issue_ids": sorted(candidate.issue_ids),
                    "source_table_id": quality_run.source_table_id,
                    "source_file_id": quality_run.source_file_id,
                }
            )
            db.add(
                ClarificationQuestion(
                    clarification_run_id=run.id,
                    question_key=candidate.key,
                    rank=rank,
                    priority_score=candidate.score,
                    priority=_priority(candidate.score),
                    category=candidate.category,
                    audience=candidate.audience,
                    question_text=candidate.question_text,
                    why_needed=candidate.why_needed,
                    answer_type=candidate.answer_type,
                    options_json=json_dumps(candidate.options),
                    issue_codes_json=json_dumps(sorted(set(candidate.issue_codes))),
                    evidence_json=json_dumps(evidence),
                    impact_json=json_dumps(candidate.impact),
                    status=ClarificationQuestionStatus.open,
                )
            )
        db.flush()
        db.refresh(run)
        return _result_response(db, run)


def get_latest_clarifications(
    data_quality_run_id: str,
    *,
    audience: str = ClarificationAudience.client,
) -> ClarificationResultResponse | None:
    audience = _validate_audience(audience)
    with db_session() as db:
        quality_exists = (
            db.query(DataQualityRun.id)
            .filter(DataQualityRun.id == data_quality_run_id)
            .first()
        )
        if quality_exists is None:
            raise AppError("data_quality_run_not_found", "Data-quality run not found", 404)
        run = (
            db.query(ClarificationRun)
            .filter(
                ClarificationRun.data_quality_run_id == data_quality_run_id,
                ClarificationRun.audience == audience,
            )
            .order_by(ClarificationRun.run_number.desc(), ClarificationRun.created_at.desc())
            .first()
        )
        return _result_response(db, run) if run else None


def get_clarification_run(run_id: str) -> ClarificationResultResponse | None:
    with db_session() as db:
        run = db.query(ClarificationRun).filter(ClarificationRun.id == run_id).first()
        return _result_response(db, run) if run else None


def list_clarification_questions(
    run_id: str,
    *,
    status: str | None = None,
    offset: int = 0,
    limit: int = 100,
) -> ClarificationQuestionPageResponse:
    with db_session() as db:
        run = db.query(ClarificationRun).filter(ClarificationRun.id == run_id).first()
        if run is None:
            raise AppError("clarification_run_not_found", "Clarification run not found", 404)
        query = db.query(ClarificationQuestion).filter(
            ClarificationQuestion.clarification_run_id == run.id
        )
        if status:
            valid = {str(item) for item in ClarificationQuestionStatus}
            if status not in valid:
                raise AppError(
                    "invalid_clarification_status",
                    "Unknown clarification question status",
                    400,
                )
            query = query.filter(ClarificationQuestion.status == status)
        total = query.count()
        questions = (
            query.order_by(ClarificationQuestion.rank.asc(), ClarificationQuestion.id.asc())
            .offset(offset)
            .limit(limit)
            .all()
        )
        return ClarificationQuestionPageResponse(
            clarification_run_id=run.id,
            offset=offset,
            limit=limit,
            total=total,
            questions=[_question_response(db, item) for item in questions],
        )


def submit_clarification_response(
    question_id: str,
    request: SubmitClarificationResponseRequest,
    *,
    responded_by_user_id: str | None = None,
) -> ClarificationQuestionResponse:
    resolution = request.resolution.strip().lower()
    if resolution not in {str(item) for item in _ALLOWED_RESOLUTIONS}:
        raise AppError(
            "invalid_clarification_resolution",
            "Resolution must be answered, deferred, not_available or not_applicable",
            400,
        )

    with db_session() as db:
        question = (
            db.query(ClarificationQuestion)
            .filter(ClarificationQuestion.id == question_id)
            .first()
        )
        if question is None:
            raise AppError(
                "clarification_question_not_found",
                "Clarification question not found",
                404,
            )
        run = (
            db.query(ClarificationRun)
            .filter(ClarificationRun.id == question.clarification_run_id)
            .first()
        )
        if run is None:
            raise AppError("clarification_run_not_found", "Clarification run not found", 404)

        answer = _validate_answer(question, resolution, request.answer)
        response_number = (
            db.query(func.max(ClarificationResponse.response_number))
            .filter(ClarificationResponse.clarification_question_id == question.id)
            .scalar()
            or 0
        ) + 1
        response = ClarificationResponse(
            clarification_question_id=question.id,
            response_number=response_number,
            resolution=resolution,
            answer_json=json_dumps(answer) if answer is not None else None,
            note=(request.note or "").strip() or None,
            responded_by_user_id=responded_by_user_id,
        )
        db.add(response)
        db.flush()

        question.status = resolution
        question.latest_response_id = response.id
        question.updated_at = datetime.now(timezone.utc)
        question.resolved_at = (
            None
            if resolution == ClarificationQuestionStatus.deferred
            else datetime.now(timezone.utc)
        )
        _refresh_run_counts(db, run)
        db.flush()
        db.refresh(question)
        return _question_response(db, question)


def list_clarification_responses(question_id: str) -> ClarificationResponsePageResponse:
    with db_session() as db:
        question = (
            db.query(ClarificationQuestion.id)
            .filter(ClarificationQuestion.id == question_id)
            .first()
        )
        if question is None:
            raise AppError(
                "clarification_question_not_found",
                "Clarification question not found",
                404,
            )
        responses = (
            db.query(ClarificationResponse)
            .filter(ClarificationResponse.clarification_question_id == question_id)
            .order_by(ClarificationResponse.response_number.asc())
            .all()
        )
        return ClarificationResponsePageResponse(
            clarification_question_id=question_id,
            total=len(responses),
            responses=[_response_response(item) for item in responses],
        )


def _build_candidates(*, quality_run, source_table, issues, columns, mappings):
    issue_by_code: dict[str, list[DataQualityIssue]] = {}
    for item in issues:
        issue_by_code.setdefault(item.code, []).append(item)
    mapping_by_column = {item.source_column_id: item for item in mappings}
    column_evidence = [
        {
            "source_column_id": column.id,
            "position": column.position,
            "source_header": column.source_header,
            "normalized_header": column.normalized_header,
            "inferred_type": column.inferred_type,
            "non_empty_count": column.non_empty_count,
            "sample_values": _safe_list(json_loads(column.sample_values_json))[:5],
            "mapping_status": (
                mapping_by_column[column.id].status
                if column.id in mapping_by_column
                else ColumnMappingStatus.unmapped
            ),
            "target_field": (
                mapping_by_column[column.id].target_field
                if column.id in mapping_by_column
                else None
            ),
            "mapping_confidence": (
                mapping_by_column[column.id].confidence
                if column.id in mapping_by_column
                else None
            ),
        }
        for column in columns
    ]
    candidates: list[_Candidate] = []

    def matched(*codes: str) -> list[DataQualityIssue]:
        return [item for code in codes for item in issue_by_code.get(code, [])]

    def add(
        *,
        key: str,
        audience: str,
        score: int,
        category: str,
        question_text: str,
        why_needed: str,
        answer_type: str,
        options: list[dict[str, str]] | None = None,
        issue_items: list[DataQualityIssue] | None = None,
        evidence: dict[str, Any] | None = None,
        impact: dict[str, Any] | None = None,
    ) -> None:
        related = issue_items or []
        candidates.append(
            _Candidate(
                key=key,
                audience=audience,
                score=score,
                category=category,
                question_text=question_text,
                why_needed=why_needed,
                answer_type=answer_type,
                options=options or [],
                issue_codes=sorted({item.code for item in related}),
                issue_ids=sorted({item.id for item in related}),
                evidence={
                    "affected_count": sum(item.affected_count for item in related),
                    "severities": dict(Counter(item.severity for item in related)),
                    "issue_details": [
                        {
                            "issue_id": item.id,
                            "code": item.code,
                            "severity": item.severity,
                            "affected_count": item.affected_count,
                            "details": _safe_dict(json_loads(item.details_json)),
                        }
                        for item in related[:10]
                    ],
                    **(evidence or {}),
                },
                impact={
                    "automatic_mutation": False,
                    **(impact or {}),
                },
            )
        )

    file_integrity = matched("source_files_missing", "source_files_corrupted")
    if file_integrity:
        add(
            key="client.file_integrity.provide_verified_originals",
            audience=ClarificationAudience.client,
            score=100,
            category="file_integrity",
            question_text=(
                "Could you provide the affected original file(s) again, or confirm that a verified replacement is unavailable?"
            ),
            why_needed=(
                "The locally stored original is missing or no longer matches its recorded SHA-256 checksum, so the current evidence cannot be trusted."
            ),
            answer_type=ClarificationAnswerType.single_choice,
            options=_options(
                ("resend_verified_originals", "We will resend verified originals"),
                ("no_replacement_available", "No verified replacement is available"),
                ("needs_internal_check", "We need to check internally first"),
            ),
            issue_items=file_integrity,
            impact={"unblocks": ["source_integrity", "all_downstream_analysis"]},
        )
        add(
            key="analyst.file_integrity.restore_verified_originals",
            audience=ClarificationAudience.analyst,
            score=100,
            category="file_integrity",
            question_text=(
                "Will the verified originals be restored from the approved local backup, or must the client resend them?"
            ),
            why_needed="Analysis must not continue from a missing or checksum-mismatched source file.",
            answer_type=ClarificationAnswerType.single_choice,
            options=_options(
                ("restore_from_backup", "Restore from approved backup"),
                ("request_client_resend", "Request a client resend"),
                ("mark_unavailable", "Mark the source unavailable"),
            ),
            issue_items=file_integrity,
            impact={"unblocks": ["source_integrity", "all_downstream_analysis"]},
        )

    impossible_metrics = matched(
        "negative_impressions",
        "negative_clicks",
        "negative_ctr",
        "clicks_with_zero_impressions",
    )
    if impossible_metrics:
        add(
            key="client.metrics.correct_impossible_values",
            audience=ClarificationAudience.client,
            score=99,
            category="metric_consistency",
            question_text=(
                "How should we interpret or correct the rows with negative metrics or positive clicks at zero impressions?"
            ),
            why_needed=(
                "Those values are not safely usable under the current metric definitions and would distort historical comparisons."
            ),
            answer_type=ClarificationAnswerType.single_choice,
            options=_options(
                ("send_corrected_export", "We will send a corrected export"),
                ("zero_means_missing", "Zero or negative values mean missing data"),
                ("values_are_intentional", "The values are intentional; we will provide definitions"),
                ("exclude_affected_rows", "Exclude the affected rows"),
            ),
            issue_items=impossible_metrics,
            impact={"unblocks": ["historical_metric_analysis", "prediction_readiness"]},
        )
        add(
            key="analyst.metrics.quarantine_impossible_values",
            audience=ClarificationAudience.analyst,
            score=98,
            category="metric_consistency",
            question_text=(
                "Should the affected metric rows be quarantined pending a corrected export, or documented as an intentional source convention?"
            ),
            why_needed="Impossible values must not silently enter aggregation or model-readiness decisions.",
            answer_type=ClarificationAnswerType.single_choice,
            options=_options(
                ("quarantine_rows", "Quarantine affected rows"),
                ("request_correction", "Request a corrected export"),
                ("document_source_convention", "Document an intentional convention"),
            ),
            issue_items=impossible_metrics,
            impact={"unblocks": ["historical_metric_analysis"]},
        )

    ctr_scale = matched("ctr_percent_scale_suspected", "ctr_above_one")
    if ctr_scale:
        add(
            key="client.metrics.confirm_ctr_scale",
            audience=ClarificationAudience.client,
            score=97,
            category="metric_consistency",
            question_text="In the source export, is CTR represented as a ratio (0.02), a percentage (2 or 2%), or a mixture?",
            why_needed=(
                "The supplied values appear to use more than one scale. We will not guess or rewrite the CTR units."
            ),
            answer_type=ClarificationAnswerType.single_choice,
            options=_options(
                ("ratio", "Ratio: 0.02 means 2%"),
                ("percentage", "Percentage: 2 or 2% means 2%"),
                ("mixed", "The export mixes both conventions"),
                ("do_not_use_ctr", "Do not use the supplied CTR field"),
            ),
            issue_items=ctr_scale,
            impact={"unblocks": ["metric_normalization_policy", "historical_ctr_analysis"]},
        )

    metric_scope = matched("ctr_click_impression_mismatch", "clicks_above_impressions")
    if metric_scope:
        add(
            key="client.metrics.explain_metric_scope",
            audience=ClarificationAudience.client,
            score=94,
            category="metric_consistency",
            question_text=(
                "Do clicks, impressions and CTR use the same date range, attribution window and aggregation level in this export?"
            ),
            why_needed=(
                "The fields do not reconcile under a simple same-row definition, so their scopes may differ."
            ),
            answer_type=ClarificationAnswerType.single_choice,
            options=_options(
                ("same_scope", "They use the same scope"),
                ("different_date_ranges", "They use different date ranges"),
                ("different_attribution", "They use different attribution rules"),
                ("different_aggregation", "They use different aggregation levels"),
                ("provide_definition", "We will provide another definition"),
            ),
            issue_items=metric_scope,
            impact={"unblocks": ["metric_consistency", "historical_performance_analysis"]},
        )

    creative_join = matched(
        "creative_reference_not_mapped",
        "creative_references_not_present",
    )
    if creative_join:
        add(
            key="client.creatives.explain_join_key",
            audience=ClarificationAudience.client,
            score=96,
            category="creative_linking",
            question_text=(
                "Which field or separate file links each historical performance row to the corresponding banner creative?"
            ),
            why_needed=(
                "Creative-specific effects cannot be separated from media context unless performance rows can be joined to actual creatives."
            ),
            answer_type=ClarificationAnswerType.single_choice,
            options=_options(
                ("filename", "The row contains the creative filename"),
                ("creative_id", "The row contains a creative ID"),
                ("separate_crosswalk", "A separate mapping table provides the link"),
                ("campaign_only", "Only campaign-level linking is available"),
                ("no_join_key", "No reliable join key exists"),
            ),
            issue_items=creative_join,
            impact={"unblocks": ["creative_linking", "creative_specific_analysis"]},
        )

    unlinked_creatives = matched("creative_assets_unlinked")
    if unlinked_creatives:
        add(
            key="client.creatives.provide_asset_mapping",
            audience=ClarificationAudience.client,
            score=91,
            category="creative_linking",
            question_text=(
                "How should the unmatched creative references be connected to the banner files supplied for testing?"
            ),
            why_needed=(
                "The historical rows contain creative references, but some of them do not match an uploaded asset exactly."
            ),
            answer_type=ClarificationAnswerType.single_choice,
            options=_options(
                ("filenames_should_match", "Filenames should match; we will correct them"),
                ("provide_crosswalk", "We will provide a reference-to-file mapping"),
                ("upload_missing_assets", "We will upload the missing creatives"),
                ("assets_not_available", "Those creative files are unavailable"),
            ),
            issue_items=unlinked_creatives,
            impact={"unblocks": ["creative_asset_linking", "creative_test_selection"]},
        )

    ambiguous_creatives = matched("creative_references_ambiguous")
    if ambiguous_creatives:
        add(
            key="analyst.creatives.resolve_ambiguous_assets",
            audience=ClarificationAudience.analyst,
            score=92,
            category="creative_linking",
            question_text=(
                "Which uploaded asset should be selected for each creative reference that currently matches more than one file?"
            ),
            why_needed="The system intentionally refused to choose an ambiguous creative match.",
            answer_type=ClarificationAnswerType.text,
            issue_items=ambiguous_creatives,
            impact={"unblocks": ["creative_asset_linking"]},
        )

    media_context = matched("media_context_not_mapped", "media_context_not_present")
    if media_context:
        add(
            key="client.media.locate_context_fields",
            audience=ClarificationAudience.client,
            score=90,
            category="prediction_readiness",
            question_text=(
                "Where are platform, placement, format or audience details stored for these historical rows?"
            ),
            why_needed=(
                "Creative effects must be evaluated together with media context rather than treating platform and placement differences as creative lift."
            ),
            answer_type=ClarificationAnswerType.single_choice,
            options=_options(
                ("same_table", "They are columns in the same table"),
                ("another_file", "They are in another supplied file"),
                ("campaign_naming", "They are encoded in campaign names"),
                ("platform_export", "They are available in a platform export"),
                ("not_available", "This context is unavailable"),
            ),
            issue_items=media_context,
            impact={"unblocks": ["media_context_control", "creative_lift_interpretation"]},
        )

    metric_location = matched(
        "click_impression_pair_not_mapped",
        "click_impression_pairs_not_present",
    )
    if metric_location:
        add(
            key="client.metrics.locate_click_impression_fields",
            audience=ClarificationAudience.client,
            score=93,
            category="prediction_readiness",
            question_text="Which fields or file contain comparable impressions and clicks for the same reporting unit?",
            why_needed=(
                "A paired click-and-impression history is required to assess whether historical CTR analysis is possible without inventing values."
            ),
            answer_type=ClarificationAnswerType.single_choice,
            options=_options(
                ("same_table", "Both fields are in the same table"),
                ("another_file", "They are in another supplied file"),
                ("only_ctr", "Only pre-calculated CTR is available"),
                ("only_one_metric", "Only one of the two metrics is available"),
                ("not_available", "Comparable metrics are unavailable"),
            ),
            issue_items=metric_location,
            impact={"unblocks": ["historical_ctr_readiness", "metric_consistency"]},
        )

    duplicate_items = matched(
        "duplicate_source_files",
        "duplicate_source_rows",
        "duplicate_performance_observations",
    )
    if duplicate_items:
        add(
            key="client.duplicates.confirm_repeated_records",
            audience=ClarificationAudience.client,
            score=80,
            category="duplicates",
            question_text=(
                "Are the repeated files or rows intentional repeated observations, or duplicate exports that should be excluded?"
            ),
            why_needed=(
                "Removing intentional repeats would undercount activity, while keeping accidental duplicates would overcount it."
            ),
            answer_type=ClarificationAnswerType.single_choice,
            options=_options(
                ("intentional_observations", "They are intentional observations"),
                ("duplicate_exports", "They are duplicate exports and should be excluded"),
                ("mixed", "Some are intentional and some are duplicates"),
                ("needs_review", "We need to review the examples"),
            ),
            issue_items=duplicate_items,
            impact={"unblocks": ["deduplication_policy", "historical_aggregation"]},
        )
        add(
            key="analyst.duplicates.choose_policy",
            audience=ClarificationAudience.analyst,
            score=78,
            category="duplicates",
            question_text=(
                "Should the detected repeated records remain separate, be excluded as duplicate deliveries, or be escalated for client confirmation?"
            ),
            why_needed="No automatic deletion or merge is performed because repeated rows may be legitimate observations.",
            answer_type=ClarificationAnswerType.single_choice,
            options=_options(
                ("keep_separate", "Keep as separate observations"),
                ("exclude_duplicates", "Exclude confirmed duplicates"),
                ("ask_client", "Ask the client to confirm"),
            ),
            issue_items=duplicate_items,
            impact={"unblocks": ["deduplication_policy"]},
        )

    missing_key_issues = [
        item
        for item in issues
        if item.code.startswith("missing_")
        and item.code
        in {
            "missing_creative_reference",
            "missing_platform",
            "missing_placement_type",
            "missing_format",
            "missing_audience",
            "missing_date",
            "missing_impressions",
            "missing_clicks",
        }
    ]
    if missing_key_issues:
        missing_fields = sorted(item.code.removeprefix("missing_") for item in missing_key_issues)
        add(
            key="client.missing_values.explain_blanks",
            audience=ClarificationAudience.client,
            score=76,
            category="missing_values",
            question_text=(
                "For the highlighted blank fields, do blanks mean ‘not applicable’, ‘unknown’, or data stored elsewhere?"
            ),
            why_needed=(
                "The current workflow preserves blanks, but their meaning affects whether rows may be compared or should be excluded from a specific analysis."
            ),
            answer_type=ClarificationAnswerType.single_choice,
            options=_options(
                ("not_applicable", "Blank means not applicable"),
                ("unknown", "Blank means unknown or not collected"),
                ("stored_elsewhere", "The value is stored elsewhere"),
                ("mixed", "The meaning differs by field or row"),
            ),
            issue_items=missing_key_issues,
            evidence={"affected_fields": missing_fields},
            impact={"unblocks": ["missing_value_policy"]},
        )

    invalid_values = [item for item in issues if item.code.startswith("invalid_")]
    if invalid_values:
        invalid_fields = sorted(item.code.removeprefix("invalid_") for item in invalid_values)
        add(
            key="client.values.confirm_source_formats",
            audience=ClarificationAudience.client,
            score=84,
            category="missing_values",
            question_text=(
                "What source format should be used for the values that could not be parsed, and can a corrected example be provided?"
            ),
            why_needed="The raw values are preserved, but the system will not guess an ambiguous numeric or date format.",
            answer_type=ClarificationAnswerType.text,
            issue_items=invalid_values,
            evidence={"affected_fields": invalid_fields},
            impact={"unblocks": ["value_normalization"]},
        )
        add(
            key="analyst.values.review_parse_failures",
            audience=ClarificationAudience.analyst,
            score=82,
            category="missing_values",
            question_text=(
                "Which deterministic parsing rule or client clarification is appropriate for the preserved raw values that failed normalization?"
            ),
            why_needed="The normalizer intentionally leaves ambiguous values empty instead of coercing them.",
            answer_type=ClarificationAnswerType.text,
            issue_items=invalid_values,
            impact={"unblocks": ["value_normalization_policy"]},
        )

    header_issues = matched("header_not_detected", "low_header_confidence", "duplicate_headers")
    if header_issues:
        add(
            key="analyst.schema.confirm_header_structure",
            audience=ClarificationAudience.analyst,
            score=90,
            category="schema_detection",
            question_text=(
                "Is the detected header row and duplicate-column interpretation correct for this sheet?"
            ),
            why_needed="An incorrect header interpretation would make every later mapping unreliable.",
            answer_type=ClarificationAnswerType.single_choice,
            options=_options(
                ("correct", "The detected structure is correct"),
                ("choose_another_header", "A different row is the header"),
                ("multirow_header", "The sheet uses a multi-row header"),
                ("client_definition_needed", "The client must clarify the structure"),
            ),
            issue_items=header_issues,
            evidence={
                "sheet_name": source_table.sheet_name,
                "detected_header_row": source_table.header_row_number,
                "header_confidence": source_table.header_confidence,
                "columns": column_evidence[:30],
            },
            impact={"unblocks": ["schema_confirmation", "mapping_reliability"]},
        )

    truncation = matched("row_limit_reached", "source_table_truncated")
    if truncation:
        add(
            key="analyst.schema.materialize_complete_table",
            audience=ClarificationAudience.analyst,
            score=99,
            category="schema_detection",
            question_text=(
                "Will the immutable source be re-inspected with a sufficient local row limit before downstream analysis?"
            ),
            why_needed="The current materialized table is incomplete, so aggregates would omit source rows.",
            answer_type=ClarificationAnswerType.single_choice,
            options=_options(
                ("rerun_with_higher_limit", "Re-run with a higher local limit"),
                ("split_source_file", "Split the source into verified parts"),
                ("accept_partial_for_review_only", "Use the partial table for review only"),
            ),
            issue_items=truncation,
            impact={"unblocks": ["complete_materialization"]},
        )

    mapping_issues = matched("no_confirmed_mappings", "mapping_confirmation_required")
    if mapping_issues:
        add(
            key="analyst.mapping.confirm_candidate_columns",
            audience=ClarificationAudience.analyst,
            score=98 if issue_by_code.get("no_confirmed_mappings") else 88,
            category="mapping",
            question_text=(
                "Which proposed column mappings can be confirmed, and which column meanings require client clarification?"
            ),
            why_needed="Suggestions are never promoted to confirmed mappings automatically.",
            answer_type=ClarificationAnswerType.text,
            issue_items=mapping_issues,
            evidence={"columns": column_evidence[:50]},
            impact={"unblocks": ["confirmed_mapping", "normalization"]},
        )

    duplicate_targets = matched("duplicate_confirmed_targets")
    if duplicate_targets:
        add(
            key="analyst.mapping.confirm_duplicate_target_precedence",
            audience=ClarificationAudience.analyst,
            score=88,
            category="mapping",
            question_text=(
                "Is the leftmost non-empty source value the intended precedence when several confirmed columns target the same field?"
            ),
            why_needed="The normalizer currently uses that explicit deterministic rule and records the conflict.",
            answer_type=ClarificationAnswerType.single_choice,
            options=_options(
                ("leftmost_is_correct", "Keep the leftmost non-empty rule"),
                ("change_mapping", "Change the confirmed mappings"),
                ("client_definition_needed", "Ask the client which field is authoritative"),
            ),
            issue_items=duplicate_targets,
            evidence={"columns": column_evidence[:50]},
            impact={"unblocks": ["mapping_precedence"]},
        )

    normalization_missing = matched("normalization_not_available", "no_usable_normalized_rows")
    if normalization_missing:
        add(
            key="analyst.normalization.complete_usable_run",
            audience=ClarificationAudience.analyst,
            score=97,
            category="prediction_readiness",
            question_text=(
                "What must be corrected before producing a completed normalization run with usable rows?"
            ),
            why_needed="Client questions should be based on normalized evidence, not on unresolved internal workflow state.",
            answer_type=ClarificationAnswerType.single_choice,
            options=_options(
                ("confirm_mappings", "Confirm the intended mappings"),
                ("fix_schema", "Correct the inspected schema"),
                ("reinspect_source", "Re-inspect the source file"),
                ("source_has_no_usable_rows", "The source has no usable rows"),
            ),
            issue_items=normalization_missing,
            impact={"unblocks": ["normalization", "client_clarification_quality"]},
        )

    return _deduplicate_candidates(candidates)


def _terminal_resolution_history(db, *, source_table_id: str, audience: str) -> dict[str, dict]:
    questions = (
        db.query(ClarificationQuestion, ClarificationRun)
        .join(ClarificationRun, ClarificationRun.id == ClarificationQuestion.clarification_run_id)
        .filter(
            ClarificationRun.source_table_id == source_table_id,
            ClarificationRun.audience == audience,
            ClarificationQuestion.status.in_([str(item) for item in _TERMINAL_STATUSES]),
        )
        .order_by(ClarificationQuestion.created_at.asc(), ClarificationQuestion.id.asc())
        .all()
    )
    history: dict[str, dict] = {}
    for question, run in questions:
        response = None
        if question.latest_response_id:
            response = (
                db.query(ClarificationResponse)
                .filter(ClarificationResponse.id == question.latest_response_id)
                .first()
            )
        history[question.question_key] = {
            "question_id": question.id,
            "clarification_run_id": run.id,
            "status": question.status,
            "resolution": response.resolution if response else question.status,
            "answer": json_loads(response.answer_json) if response else None,
            "response_number": response.response_number if response else None,
        }
    return history


def _validate_answer(question: ClarificationQuestion, resolution: str, answer: Any):
    if resolution == ClarificationQuestionStatus.answered and answer is None:
        raise AppError(
            "clarification_answer_required",
            "An answered question requires an answer value",
            400,
        )
    if answer is None:
        return None

    options = _safe_list(json_loads(question.options_json))
    option_values = {
        str(item.get("value"))
        for item in options
        if isinstance(item, dict) and item.get("value") is not None
    }
    answer_type = question.answer_type
    if answer_type == ClarificationAnswerType.single_choice:
        if not isinstance(answer, str) or answer not in option_values:
            raise AppError(
                "invalid_clarification_answer",
                "The answer must be one of the allowed option values",
                400,
            )
    elif answer_type == ClarificationAnswerType.multiple_choice:
        if not isinstance(answer, list) or not answer or not all(
            isinstance(item, str) and item in option_values for item in answer
        ):
            raise AppError(
                "invalid_clarification_answer",
                "The answer must be a non-empty list of allowed option values",
                400,
            )
        answer = list(dict.fromkeys(answer))
    elif answer_type == ClarificationAnswerType.text:
        if not isinstance(answer, str) or not answer.strip():
            raise AppError(
                "invalid_clarification_answer",
                "The answer must be non-empty text",
                400,
            )
        answer = answer.strip()
    elif answer_type == ClarificationAnswerType.boolean:
        if not isinstance(answer, bool):
            raise AppError(
                "invalid_clarification_answer",
                "The answer must be a boolean",
                400,
            )
    elif answer_type == ClarificationAnswerType.integer:
        if isinstance(answer, bool) or not isinstance(answer, int):
            raise AppError(
                "invalid_clarification_answer",
                "The answer must be an integer",
                400,
            )
    return answer


def _refresh_run_counts(db, run: ClarificationRun) -> None:
    counts = Counter(
        status
        for (status,) in db.query(ClarificationQuestion.status)
        .filter(ClarificationQuestion.clarification_run_id == run.id)
        .all()
    )
    run.open_question_count = counts[ClarificationQuestionStatus.open]
    run.answered_question_count = counts[ClarificationQuestionStatus.answered]
    run.deferred_question_count = counts[ClarificationQuestionStatus.deferred]
    run.not_available_question_count = counts[ClarificationQuestionStatus.not_available]
    run.not_applicable_question_count = counts[ClarificationQuestionStatus.not_applicable]
    run.updated_at = datetime.now(timezone.utc)
    unresolved = run.open_question_count + run.deferred_question_count
    if unresolved:
        run.status = ClarificationRunStatus.open
        run.resolved_at = None
    else:
        run.status = ClarificationRunStatus.resolved
        run.resolved_at = datetime.now(timezone.utc)


def _result_response(db, run: ClarificationRun) -> ClarificationResultResponse:
    questions = (
        db.query(ClarificationQuestion)
        .filter(ClarificationQuestion.clarification_run_id == run.id)
        .order_by(ClarificationQuestion.rank.asc(), ClarificationQuestion.id.asc())
        .all()
    )
    return ClarificationResultResponse(
        run=_run_response(run),
        questions=[_question_response(db, item) for item in questions],
    )


def _run_response(model: ClarificationRun) -> ClarificationRunResponse:
    summary = json_loads(model.summary_json)
    return ClarificationRunResponse(
        id=model.id,
        data_quality_run_id=model.data_quality_run_id,
        source_table_id=model.source_table_id,
        source_file_id=model.source_file_id,
        import_session_id=model.import_session_id,
        project_id=model.project_id,
        run_number=model.run_number,
        generator_name=model.generator_name,
        generator_version=model.generator_version,
        input_fingerprint=model.input_fingerprint,
        audience=model.audience,
        max_questions=model.max_questions,
        status=model.status,
        candidate_count=model.candidate_count,
        question_count=model.question_count,
        suppressed_question_count=model.suppressed_question_count,
        open_question_count=model.open_question_count,
        answered_question_count=model.answered_question_count,
        deferred_question_count=model.deferred_question_count,
        not_available_question_count=model.not_available_question_count,
        not_applicable_question_count=model.not_applicable_question_count,
        summary=summary if isinstance(summary, dict) else {},
        created_by_user_id=model.created_by_user_id,
        created_at=model.created_at,
        updated_at=model.updated_at,
        resolved_at=model.resolved_at,
    )


def _question_response(db, model: ClarificationQuestion) -> ClarificationQuestionResponse:
    latest = None
    if model.latest_response_id:
        response = (
            db.query(ClarificationResponse)
            .filter(ClarificationResponse.id == model.latest_response_id)
            .first()
        )
        if response:
            latest = _response_response(response)
    return ClarificationQuestionResponse(
        id=model.id,
        clarification_run_id=model.clarification_run_id,
        question_key=model.question_key,
        rank=model.rank,
        priority_score=model.priority_score,
        priority=model.priority,
        category=model.category,
        audience=model.audience,
        question_text=model.question_text,
        why_needed=model.why_needed,
        answer_type=model.answer_type,
        options=_safe_list(json_loads(model.options_json)),
        issue_codes=_safe_list(json_loads(model.issue_codes_json)),
        evidence=_safe_dict(json_loads(model.evidence_json)),
        impact=_safe_dict(json_loads(model.impact_json)),
        status=model.status,
        latest_response=latest,
        created_at=model.created_at,
        updated_at=model.updated_at,
        resolved_at=model.resolved_at,
    )


def _response_response(model: ClarificationResponse) -> ClarificationResponseResponse:
    return ClarificationResponseResponse(
        id=model.id,
        clarification_question_id=model.clarification_question_id,
        response_number=model.response_number,
        resolution=model.resolution,
        answer=json_loads(model.answer_json) if model.answer_json is not None else None,
        note=model.note,
        responded_by_user_id=model.responded_by_user_id,
        created_at=model.created_at,
    )


def _candidate_snapshot(candidate: _Candidate) -> dict:
    return {
        "key": candidate.key,
        "audience": candidate.audience,
        "score": candidate.score,
        "category": candidate.category,
        "question_text": candidate.question_text,
        "why_needed": candidate.why_needed,
        "answer_type": candidate.answer_type,
        "options": candidate.options,
        "issue_codes": candidate.issue_codes,
        "issue_ids": candidate.issue_ids,
        "evidence": candidate.evidence,
        "impact": candidate.impact,
    }


def _deduplicate_candidates(candidates: list[_Candidate]) -> list[_Candidate]:
    by_key: dict[tuple[str, str], _Candidate] = {}
    for candidate in candidates:
        key = (candidate.audience, candidate.key)
        existing = by_key.get(key)
        if existing is None:
            by_key[key] = candidate
            continue
        existing.score = max(existing.score, candidate.score)
        existing.issue_codes = sorted(set(existing.issue_codes) | set(candidate.issue_codes))
        existing.issue_ids = sorted(set(existing.issue_ids) | set(candidate.issue_ids))
        existing.evidence["affected_count"] = max(
            int(existing.evidence.get("affected_count", 0)),
            int(candidate.evidence.get("affected_count", 0)),
        )
    return list(by_key.values())


def _validate_audience(audience: str) -> str:
    audience = audience.strip().lower()
    if audience not in {str(item) for item in ClarificationAudience}:
        raise AppError(
            "invalid_clarification_audience",
            "Audience must be client or analyst",
            400,
        )
    return audience


def _priority(score: int) -> str:
    if score >= 90:
        return ClarificationPriority.critical
    if score >= 75:
        return ClarificationPriority.high
    return ClarificationPriority.medium


def _options(*items: tuple[str, str]) -> list[dict[str, str]]:
    return [{"value": value, "label": label} for value, label in items]


def _safe_list(value: Any) -> list:
    return value if isinstance(value, list) else []


def _safe_dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}
