"""Clarification rules for duplicate, missing, and invalid source records."""

from __future__ import annotations

from src.modules.clarifications.candidate_context import CandidateContext, options
from src.modules.clarifications.models import (
    ClarificationAnswerType,
    ClarificationAudience,
)

_MISSING_VALUE_CODES = {
    "missing_creative_reference",
    "missing_platform",
    "missing_placement_type",
    "missing_format",
    "missing_audience",
    "missing_date",
    "missing_impressions",
    "missing_clicks",
}


def add_duplicate_questions(context: CandidateContext) -> None:
    issue_items = context.matched(
        "duplicate_source_files",
        "duplicate_source_rows",
        "duplicate_performance_observations",
    )
    if not issue_items:
        return

    context.add(
        key="client.duplicates.confirm_repeated_records",
        audience=ClarificationAudience.client,
        score=80,
        category="duplicates",
        question_text=(
            "Are the repeated files or rows intentional repeated observations, "
            "or duplicate exports that should be excluded?"
        ),
        why_needed=(
            "Removing intentional repeats would undercount activity, while "
            "keeping accidental duplicates would overcount it."
        ),
        answer_type=ClarificationAnswerType.single_choice,
        options=options(
            ("intentional_observations", "They are intentional observations"),
            (
                "duplicate_exports",
                "They are duplicate exports and should be excluded",
            ),
            ("mixed", "Some are intentional and some are duplicates"),
            ("needs_review", "We need to review the examples"),
        ),
        issue_items=issue_items,
        impact={"unblocks": ["deduplication_policy", "historical_aggregation"]},
    )
    context.add(
        key="analyst.duplicates.choose_policy",
        audience=ClarificationAudience.analyst,
        score=78,
        category="duplicates",
        question_text=(
            "Should the detected repeated records remain separate, be excluded "
            "as duplicate deliveries, or be escalated for client confirmation?"
        ),
        why_needed=(
            "No automatic deletion or merge is performed because repeated rows "
            "may be legitimate observations."
        ),
        answer_type=ClarificationAnswerType.single_choice,
        options=options(
            ("keep_separate", "Keep as separate observations"),
            ("exclude_duplicates", "Exclude confirmed duplicates"),
            ("ask_client", "Ask the client to confirm"),
        ),
        issue_items=issue_items,
        impact={"unblocks": ["deduplication_policy"]},
    )


def add_missing_value_question(context: CandidateContext) -> None:
    issue_items = [
        item
        for item in context.issues
        if item.code.startswith("missing_") and item.code in _MISSING_VALUE_CODES
    ]
    if not issue_items:
        return

    missing_fields = sorted(item.code.removeprefix("missing_") for item in issue_items)
    context.add(
        key="client.missing_values.explain_blanks",
        audience=ClarificationAudience.client,
        score=76,
        category="missing_values",
        question_text=(
            "For the highlighted blank fields, do blanks mean ‘not applicable’, "
            "‘unknown’, or data stored elsewhere?"
        ),
        why_needed=(
            "The current workflow preserves blanks, but their meaning affects "
            "whether rows may be compared or should be excluded from a specific analysis."
        ),
        answer_type=ClarificationAnswerType.single_choice,
        options=options(
            ("not_applicable", "Blank means not applicable"),
            ("unknown", "Blank means unknown or not collected"),
            ("stored_elsewhere", "The value is stored elsewhere"),
            ("mixed", "The meaning differs by field or row"),
        ),
        issue_items=issue_items,
        evidence={"affected_fields": missing_fields},
        impact={"unblocks": ["missing_value_policy"]},
    )


def add_invalid_value_questions(context: CandidateContext) -> None:
    issue_items = [item for item in context.issues if item.code.startswith("invalid_")]
    if not issue_items:
        return

    invalid_fields = sorted(item.code.removeprefix("invalid_") for item in issue_items)
    context.add(
        key="client.values.confirm_source_formats",
        audience=ClarificationAudience.client,
        score=84,
        category="missing_values",
        question_text=(
            "What source format should be used for the values that could not be "
            "parsed, and can a corrected example be provided?"
        ),
        why_needed=(
            "The raw values are preserved, but the system will not guess an "
            "ambiguous numeric or date format."
        ),
        answer_type=ClarificationAnswerType.text,
        issue_items=issue_items,
        evidence={"affected_fields": invalid_fields},
        impact={"unblocks": ["value_normalization"]},
    )
    context.add(
        key="analyst.values.review_parse_failures",
        audience=ClarificationAudience.analyst,
        score=82,
        category="missing_values",
        question_text=(
            "Which deterministic parsing rule or client clarification is "
            "appropriate for the preserved raw values that failed normalization?"
        ),
        why_needed=(
            "The normalizer intentionally leaves ambiguous values empty instead "
            "of coercing them."
        ),
        answer_type=ClarificationAnswerType.text,
        issue_items=issue_items,
        impact={"unblocks": ["value_normalization_policy"]},
    )
