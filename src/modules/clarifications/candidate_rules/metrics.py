"""Clarification rules for source integrity and metric consistency."""

from __future__ import annotations

from src.modules.clarifications.candidate_context import CandidateContext, options
from src.modules.clarifications.models import (
    ClarificationAnswerType,
    ClarificationAudience,
)


def add_file_integrity_questions(context: CandidateContext) -> None:
    issue_items = context.matched("source_files_missing", "source_files_corrupted")
    if not issue_items:
        return

    context.add(
        key="client.file_integrity.provide_verified_originals",
        audience=ClarificationAudience.client,
        score=100,
        category="file_integrity",
        question_text=(
            "Could you provide the affected original file(s) again, or confirm "
            "that a verified replacement is unavailable?"
        ),
        why_needed=(
            "The locally stored original is missing or no longer matches its "
            "recorded SHA-256 checksum, so the current evidence cannot be trusted."
        ),
        answer_type=ClarificationAnswerType.single_choice,
        options=options(
            ("resend_verified_originals", "We will resend verified originals"),
            ("no_replacement_available", "No verified replacement is available"),
            ("needs_internal_check", "We need to check internally first"),
        ),
        issue_items=issue_items,
        impact={"unblocks": ["source_integrity", "all_downstream_analysis"]},
    )
    context.add(
        key="analyst.file_integrity.restore_verified_originals",
        audience=ClarificationAudience.analyst,
        score=100,
        category="file_integrity",
        question_text=(
            "Will the verified originals be restored from the approved local "
            "backup, or must the client resend them?"
        ),
        why_needed=(
            "Analysis must not continue from a missing or checksum-mismatched "
            "source file."
        ),
        answer_type=ClarificationAnswerType.single_choice,
        options=options(
            ("restore_from_backup", "Restore from approved backup"),
            ("request_client_resend", "Request a client resend"),
            ("mark_unavailable", "Mark the source unavailable"),
        ),
        issue_items=issue_items,
        impact={"unblocks": ["source_integrity", "all_downstream_analysis"]},
    )


def add_impossible_metric_questions(context: CandidateContext) -> None:
    issue_items = context.matched(
        "negative_impressions",
        "negative_clicks",
        "negative_ctr",
        "clicks_with_zero_impressions",
    )
    if not issue_items:
        return

    context.add(
        key="client.metrics.correct_impossible_values",
        audience=ClarificationAudience.client,
        score=99,
        category="metric_consistency",
        question_text=(
            "How should we interpret or correct the rows with negative metrics "
            "or positive clicks at zero impressions?"
        ),
        why_needed=(
            "Those values are not safely usable under the current metric "
            "definitions and would distort historical comparisons."
        ),
        answer_type=ClarificationAnswerType.single_choice,
        options=options(
            ("send_corrected_export", "We will send a corrected export"),
            ("zero_means_missing", "Zero or negative values mean missing data"),
            (
                "values_are_intentional",
                "The values are intentional; we will provide definitions",
            ),
            ("exclude_affected_rows", "Exclude the affected rows"),
        ),
        issue_items=issue_items,
        impact={"unblocks": ["historical_metric_analysis", "prediction_readiness"]},
    )
    context.add(
        key="analyst.metrics.quarantine_impossible_values",
        audience=ClarificationAudience.analyst,
        score=98,
        category="metric_consistency",
        question_text=(
            "Should the affected metric rows be quarantined pending a corrected "
            "export, or documented as an intentional source convention?"
        ),
        why_needed=(
            "Impossible values must not silently enter aggregation or "
            "model-readiness decisions."
        ),
        answer_type=ClarificationAnswerType.single_choice,
        options=options(
            ("quarantine_rows", "Quarantine affected rows"),
            ("request_correction", "Request a corrected export"),
            (
                "document_source_convention",
                "Document an intentional convention",
            ),
        ),
        issue_items=issue_items,
        impact={"unblocks": ["historical_metric_analysis"]},
    )


def add_ctr_scale_question(context: CandidateContext) -> None:
    issue_items = context.matched("ctr_percent_scale_suspected", "ctr_above_one")
    if not issue_items:
        return

    context.add(
        key="client.metrics.confirm_ctr_scale",
        audience=ClarificationAudience.client,
        score=97,
        category="metric_consistency",
        question_text=(
            "In the source export, is CTR represented as a ratio (0.02), a "
            "percentage (2 or 2%), or a mixture?"
        ),
        why_needed=(
            "The supplied values appear to use more than one scale. We will not "
            "guess or rewrite the CTR units."
        ),
        answer_type=ClarificationAnswerType.single_choice,
        options=options(
            ("ratio", "Ratio: 0.02 means 2%"),
            ("percentage", "Percentage: 2 or 2% means 2%"),
            ("mixed", "The export mixes both conventions"),
            ("do_not_use_ctr", "Do not use the supplied CTR field"),
        ),
        issue_items=issue_items,
        impact={"unblocks": ["metric_normalization_policy", "historical_ctr_analysis"]},
    )


def add_metric_scope_question(context: CandidateContext) -> None:
    issue_items = context.matched(
        "ctr_click_impression_mismatch",
        "clicks_above_impressions",
    )
    if not issue_items:
        return

    context.add(
        key="client.metrics.explain_metric_scope",
        audience=ClarificationAudience.client,
        score=94,
        category="metric_consistency",
        question_text=(
            "Do clicks, impressions and CTR use the same date range, attribution "
            "window and aggregation level in this export?"
        ),
        why_needed=(
            "The fields do not reconcile under a simple same-row definition, so "
            "their scopes may differ."
        ),
        answer_type=ClarificationAnswerType.single_choice,
        options=options(
            ("same_scope", "They use the same scope"),
            ("different_date_ranges", "They use different date ranges"),
            ("different_attribution", "They use different attribution rules"),
            ("different_aggregation", "They use different aggregation levels"),
            ("provide_definition", "We will provide another definition"),
        ),
        issue_items=issue_items,
        impact={"unblocks": ["metric_consistency", "historical_performance_analysis"]},
    )


def add_metric_location_question(context: CandidateContext) -> None:
    issue_items = context.matched(
        "click_impression_pair_not_mapped",
        "click_impression_pairs_not_present",
    )
    if not issue_items:
        return

    context.add(
        key="client.metrics.locate_click_impression_fields",
        audience=ClarificationAudience.client,
        score=93,
        category="prediction_readiness",
        question_text=(
            "Which fields or file contain comparable impressions and clicks for "
            "the same reporting unit?"
        ),
        why_needed=(
            "A paired click-and-impression history is required to assess whether "
            "historical CTR analysis is possible without inventing values."
        ),
        answer_type=ClarificationAnswerType.single_choice,
        options=options(
            ("same_table", "Both fields are in the same table"),
            ("another_file", "They are in another supplied file"),
            ("only_ctr", "Only pre-calculated CTR is available"),
            ("only_one_metric", "Only one of the two metrics is available"),
            ("not_available", "Comparable metrics are unavailable"),
        ),
        issue_items=issue_items,
        impact={"unblocks": ["historical_ctr_readiness", "metric_consistency"]},
    )
