"""Shared context and evidence helpers for clarification rules."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Iterable

from src.modules.clarifications.candidate_types import ClarificationCandidate
from src.modules.data_quality.models import DataQualityIssue
from src.modules.mapping_engine.models import ColumnMappingStatus
from src.shared.db.repository import json_loads


def _as_list(value: Any) -> list:
    return value if isinstance(value, list) else []


def _as_dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def options(*items: tuple[str, str]) -> list[dict[str, str]]:
    return [{"value": value, "label": label} for value, label in items]


@dataclass(slots=True)
class CandidateContext:
    source_table: Any
    issues: list[DataQualityIssue]
    column_evidence: list[dict[str, Any]]
    issue_by_code: dict[str, list[DataQualityIssue]]
    candidates: list[ClarificationCandidate] = field(default_factory=list)

    @classmethod
    def from_inputs(
        cls,
        *,
        source_table: Any,
        issues: Iterable[DataQualityIssue],
        columns: Iterable[Any],
        mappings: Iterable[Any],
    ) -> "CandidateContext":
        issue_items = list(issues)
        issue_by_code: dict[str, list[DataQualityIssue]] = {}
        for item in issue_items:
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
                "sample_values": _as_list(json_loads(column.sample_values_json))[:5],
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
        return cls(
            source_table=source_table,
            issues=issue_items,
            column_evidence=column_evidence,
            issue_by_code=issue_by_code,
        )

    def matched(self, *codes: str) -> list[DataQualityIssue]:
        return [
            item
            for code in codes
            for item in self.issue_by_code.get(code, [])
        ]

    def add(
        self,
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
        self.candidates.append(
            ClarificationCandidate(
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
                            "details": _as_dict(json_loads(item.details_json)),
                        }
                        for item in related[:10]
                    ],
                    **(evidence or {}),
                },
                impact={"automatic_mutation": False, **(impact or {})},
            )
        )
