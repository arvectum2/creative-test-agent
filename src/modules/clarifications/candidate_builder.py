"""Evidence-backed clarification candidate orchestration.

Deterministic rule implementations live in ``candidate_rules``. This module keeps
only the public compatibility API consumed by the clarification service.
"""

from __future__ import annotations

from src.modules.clarifications.candidate_context import CandidateContext
from src.modules.clarifications.candidate_rules import RULES
from src.modules.clarifications.candidate_types import ClarificationCandidate
from src.modules.clarifications.models import ClarificationPriority


def build_candidates(*, quality_run, source_table, issues, columns, mappings):
    """Build clarification candidates in stable business-priority order."""

    del quality_run  # Kept in the public contract for service compatibility.
    context = CandidateContext.from_inputs(
        source_table=source_table,
        issues=issues,
        columns=columns,
        mappings=mappings,
    )
    for rule in RULES:
        rule(context)
    return _deduplicate_candidates(context.candidates)


def _deduplicate_candidates(
    candidates: list[ClarificationCandidate],
) -> list[ClarificationCandidate]:
    by_key: dict[tuple[str, str], ClarificationCandidate] = {}
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


def priority_for_score(score: int) -> str:
    if score >= 90:
        return ClarificationPriority.critical
    if score >= 75:
        return ClarificationPriority.high
    return ClarificationPriority.medium


__all__ = [
    "ClarificationCandidate",
    "build_candidates",
    "priority_for_score",
]
