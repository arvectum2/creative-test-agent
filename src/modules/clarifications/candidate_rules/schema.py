"""Clarification rules for schema detection, mapping, and normalization."""

from __future__ import annotations

from src.modules.clarifications.candidate_context import CandidateContext, options
from src.modules.clarifications.models import (
    ClarificationAnswerType,
    ClarificationAudience,
)


def add_header_question(context: CandidateContext) -> None:
    issue_items = context.matched(
        "header_not_detected",
        "low_header_confidence",
        "duplicate_headers",
    )
    if not issue_items:
        return

    context.add(
        key="analyst.schema.confirm_header_structure",
        audience=ClarificationAudience.analyst,
        score=90,
        category="schema_detection",
        question_text=(
            "Is the detected header row and duplicate-column interpretation "
            "correct for this sheet?"
        ),
        why_needed=(
            "An incorrect header interpretation would make every later mapping unreliable."
        ),
        answer_type=ClarificationAnswerType.single_choice,
        options=options(
            ("correct", "The detected structure is correct"),
            ("choose_another_header", "A different row is the header"),
            ("multirow_header", "The sheet uses a multi-row header"),
            ("client_definition_needed", "The client must clarify the structure"),
        ),
        issue_items=issue_items,
        evidence={
            "sheet_name": context.source_table.sheet_name,
            "detected_header_row": context.source_table.header_row_number,
            "header_confidence": context.source_table.header_confidence,
            "columns": context.column_evidence[:30],
        },
        impact={"unblocks": ["schema_confirmation", "mapping_reliability"]},
    )


def add_truncation_question(context: CandidateContext) -> None:
    issue_items = context.matched("row_limit_reached", "source_table_truncated")
    if not issue_items:
        return

    context.add(
        key="analyst.schema.materialize_complete_table",
        audience=ClarificationAudience.analyst,
        score=99,
        category="schema_detection",
        question_text=(
            "Will the immutable source be re-inspected with a sufficient local "
            "row limit before downstream analysis?"
        ),
        why_needed=(
            "The current materialized table is incomplete, so aggregates would "
            "omit source rows."
        ),
        answer_type=ClarificationAnswerType.single_choice,
        options=options(
            ("rerun_with_higher_limit", "Re-run with a higher local limit"),
            ("split_source_file", "Split the source into verified parts"),
            (
                "accept_partial_for_review_only",
                "Use the partial table for review only",
            ),
        ),
        issue_items=issue_items,
        impact={"unblocks": ["complete_materialization"]},
    )


def add_mapping_confirmation_question(context: CandidateContext) -> None:
    issue_items = context.matched(
        "no_confirmed_mappings",
        "mapping_confirmation_required",
    )
    if not issue_items:
        return

    context.add(
        key="analyst.mapping.confirm_candidate_columns",
        audience=ClarificationAudience.analyst,
        score=98 if context.issue_by_code.get("no_confirmed_mappings") else 88,
        category="mapping",
        question_text=(
            "Which proposed column mappings can be confirmed, and which column "
            "meanings require client clarification?"
        ),
        why_needed=(
            "Suggestions are never promoted to confirmed mappings automatically."
        ),
        answer_type=ClarificationAnswerType.text,
        issue_items=issue_items,
        evidence={"columns": context.column_evidence[:50]},
        impact={"unblocks": ["confirmed_mapping", "normalization"]},
    )


def add_duplicate_target_question(context: CandidateContext) -> None:
    issue_items = context.matched("duplicate_confirmed_targets")
    if not issue_items:
        return

    context.add(
        key="analyst.mapping.confirm_duplicate_target_precedence",
        audience=ClarificationAudience.analyst,
        score=88,
        category="mapping",
        question_text=(
            "Is the leftmost non-empty source value the intended precedence when "
            "several confirmed columns target the same field?"
        ),
        why_needed=(
            "The normalizer currently uses that explicit deterministic rule and "
            "records the conflict."
        ),
        answer_type=ClarificationAnswerType.single_choice,
        options=options(
            ("leftmost_is_correct", "Keep the leftmost non-empty rule"),
            ("change_mapping", "Change the confirmed mappings"),
            (
                "client_definition_needed",
                "Ask the client which field is authoritative",
            ),
        ),
        issue_items=issue_items,
        evidence={"columns": context.column_evidence[:50]},
        impact={"unblocks": ["mapping_precedence"]},
    )


def add_normalization_question(context: CandidateContext) -> None:
    issue_items = context.matched(
        "normalization_not_available",
        "no_usable_normalized_rows",
    )
    if not issue_items:
        return

    context.add(
        key="analyst.normalization.complete_usable_run",
        audience=ClarificationAudience.analyst,
        score=97,
        category="prediction_readiness",
        question_text=(
            "What must be corrected before producing a completed normalization "
            "run with usable rows?"
        ),
        why_needed=(
            "Client questions should be based on normalized evidence, not on "
            "unresolved internal workflow state."
        ),
        answer_type=ClarificationAnswerType.single_choice,
        options=options(
            ("confirm_mappings", "Confirm the intended mappings"),
            ("fix_schema", "Correct the inspected schema"),
            ("reinspect_source", "Re-inspect the source file"),
            ("source_has_no_usable_rows", "The source has no usable rows"),
        ),
        issue_items=issue_items,
        impact={"unblocks": ["normalization", "client_clarification_quality"]},
    )
