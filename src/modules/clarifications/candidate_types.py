"""Value objects used by deterministic clarification candidate generation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class ClarificationCandidate:
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
