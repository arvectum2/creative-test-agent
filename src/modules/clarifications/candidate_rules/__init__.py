"""Ordered clarification rule registry."""

from __future__ import annotations

from collections.abc import Callable

from src.modules.clarifications.candidate_context import CandidateContext
from src.modules.clarifications.candidate_rules.creatives import (
    add_ambiguous_creative_question,
    add_creative_join_question,
    add_media_context_question,
    add_unlinked_creative_question,
)
from src.modules.clarifications.candidate_rules.metrics import (
    add_ctr_scale_question,
    add_file_integrity_questions,
    add_impossible_metric_questions,
    add_metric_location_question,
    add_metric_scope_question,
)
from src.modules.clarifications.candidate_rules.records import (
    add_duplicate_questions,
    add_invalid_value_questions,
    add_missing_value_question,
)
from src.modules.clarifications.candidate_rules.schema import (
    add_duplicate_target_question,
    add_header_question,
    add_mapping_confirmation_question,
    add_normalization_question,
    add_truncation_question,
)

CandidateRule = Callable[[CandidateContext], None]

RULES: tuple[CandidateRule, ...] = (
    add_file_integrity_questions,
    add_impossible_metric_questions,
    add_ctr_scale_question,
    add_metric_scope_question,
    add_creative_join_question,
    add_unlinked_creative_question,
    add_ambiguous_creative_question,
    add_media_context_question,
    add_metric_location_question,
    add_duplicate_questions,
    add_missing_value_question,
    add_invalid_value_questions,
    add_header_question,
    add_truncation_question,
    add_mapping_confirmation_question,
    add_duplicate_target_question,
    add_normalization_question,
)

__all__ = ["RULES", "CandidateRule"]
