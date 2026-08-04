"""Clarification rules for creative linking and media context."""

from __future__ import annotations

from src.modules.clarifications.candidate_context import CandidateContext, options
from src.modules.clarifications.models import (
    ClarificationAnswerType,
    ClarificationAudience,
)


def add_creative_join_question(context: CandidateContext) -> None:
    issue_items = context.matched(
        "creative_reference_not_mapped",
        "creative_references_not_present",
    )
    if not issue_items:
        return

    context.add(
        key="client.creatives.explain_join_key",
        audience=ClarificationAudience.client,
        score=96,
        category="creative_linking",
        question_text=(
            "Which field or separate file links each historical performance row "
            "to the corresponding banner creative?"
        ),
        why_needed=(
            "Creative-specific effects cannot be separated from media context "
            "unless performance rows can be joined to actual creatives."
        ),
        answer_type=ClarificationAnswerType.single_choice,
        options=options(
            ("filename", "The row contains the creative filename"),
            ("creative_id", "The row contains a creative ID"),
            ("separate_crosswalk", "A separate mapping table provides the link"),
            ("campaign_only", "Only campaign-level linking is available"),
            ("no_join_key", "No reliable join key exists"),
        ),
        issue_items=issue_items,
        impact={"unblocks": ["creative_linking", "creative_specific_analysis"]},
    )


def add_unlinked_creative_question(context: CandidateContext) -> None:
    issue_items = context.matched("creative_assets_unlinked")
    if not issue_items:
        return

    context.add(
        key="client.creatives.provide_asset_mapping",
        audience=ClarificationAudience.client,
        score=91,
        category="creative_linking",
        question_text=(
            "How should the unmatched creative references be connected to the "
            "banner files supplied for testing?"
        ),
        why_needed=(
            "The historical rows contain creative references, but some of them "
            "do not match an uploaded asset exactly."
        ),
        answer_type=ClarificationAnswerType.single_choice,
        options=options(
            (
                "filenames_should_match",
                "Filenames should match; we will correct them",
            ),
            ("provide_crosswalk", "We will provide a reference-to-file mapping"),
            ("upload_missing_assets", "We will upload the missing creatives"),
            ("assets_not_available", "Those creative files are unavailable"),
        ),
        issue_items=issue_items,
        impact={"unblocks": ["creative_asset_linking", "creative_test_selection"]},
    )


def add_ambiguous_creative_question(context: CandidateContext) -> None:
    issue_items = context.matched("creative_references_ambiguous")
    if not issue_items:
        return

    context.add(
        key="analyst.creatives.resolve_ambiguous_assets",
        audience=ClarificationAudience.analyst,
        score=92,
        category="creative_linking",
        question_text=(
            "Which uploaded asset should be selected for each creative reference "
            "that currently matches more than one file?"
        ),
        why_needed=(
            "The system intentionally refused to choose an ambiguous creative match."
        ),
        answer_type=ClarificationAnswerType.text,
        issue_items=issue_items,
        impact={"unblocks": ["creative_asset_linking"]},
    )


def add_media_context_question(context: CandidateContext) -> None:
    issue_items = context.matched("media_context_not_mapped", "media_context_not_present")
    if not issue_items:
        return

    context.add(
        key="client.media.locate_context_fields",
        audience=ClarificationAudience.client,
        score=90,
        category="prediction_readiness",
        question_text=(
            "Where are platform, placement, format or audience details stored "
            "for these historical rows?"
        ),
        why_needed=(
            "Creative effects must be evaluated together with media context "
            "rather than treating platform and placement differences as creative lift."
        ),
        answer_type=ClarificationAnswerType.single_choice,
        options=options(
            ("same_table", "They are columns in the same table"),
            ("another_file", "They are in another supplied file"),
            ("campaign_naming", "They are encoded in campaign names"),
            ("platform_export", "They are available in a platform export"),
            ("not_available", "This context is unavailable"),
        ),
        issue_items=issue_items,
        impact={"unblocks": ["media_context_control", "creative_lift_interpretation"]},
    )
