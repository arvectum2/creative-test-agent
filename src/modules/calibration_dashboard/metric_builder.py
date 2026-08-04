"""Metric assembly for the calibration quality dashboard."""

from __future__ import annotations

from typing import Any


def build_metrics(
    *,
    yes_correct: int,
    correctness_assessed: int,
    review_coverage: float | None,
    actionable: int,
    resolved_count: int,
    traceable: int,
    latest_human: dict[str, Any],
    selected_cases: set[str],
    harmful: int,
    material_disagreement: list[Any],
    independent: list[Any],
    selected_disagreements: list[Any],
    touch_minutes: list[float],
    measured_cases: set[str],
    actions_per_case: list[int],
    workflow_coverage: float | None,
    outcome_coverage: float | None,
    outcome_cases: set[str],
):
    from src.modules.calibration_dashboard.service import _median, _metric, _ratio

    metrics = [
        _metric(
            key="expert_supported_finding_rate",
            label="Expert-supported finding rate",
            domain="expert_review",
            unit="ratio",
            value=_ratio(yes_correct, correctness_assessed),
            numerator=yes_correct,
            denominator=correctness_assessed,
            coverage=review_coverage,
            definition=(
                "Resolved system findings with correctness >=4 divided by resolved "
                "findings with correctness >=4 or <=2; neutral score 3 is excluded."
            ),
            interpretation=(
                "Observed expert support in this calibration set; not validated model accuracy."
            ),
            limitations=[
                "Single-review, unresolved disagreement and stale adjudication are "
                "excluded from the rate and shown as coverage gaps."
            ],
        ),
        _metric(
            key="finding_actionability_rate",
            label="Actionability rate",
            domain="expert_review",
            unit="ratio",
            value=_ratio(actionable, resolved_count),
            numerator=actionable,
            denominator=resolved_count,
            coverage=review_coverage,
            definition=(
                "Resolved assessments with actionability >=4 divided by all resolved assessments."
            ),
            interpretation=(
                "Share of reviewed findings judged operationally actionable in this evidence set."
            ),
            limitations=["This is reviewer judgement, not downstream business impact."],
        ),
        _metric(
            key="evidence_traceability_rate",
            label="Traceability rate",
            domain="expert_review",
            unit="ratio",
            value=_ratio(traceable, resolved_count),
            numerator=traceable,
            denominator=resolved_count,
            coverage=review_coverage,
            definition=(
                "Resolved assessments with traceability >=4 divided by all resolved assessments."
            ),
            interpretation=(
                "Share of reviewed findings with evidence judged sufficiently traceable."
            ),
            limitations=["Traceability does not prove factual correctness or causal effect."],
        ),
        _metric(
            key="human_added_finding_count",
            label="Human-added findings",
            domain="expert_review",
            unit="count",
            value=len(latest_human),
            numerator=len(latest_human),
            denominator=len(selected_cases),
            coverage=review_coverage,
            definition=(
                "Count of distinct latest human-added omission findings in included cases."
            ),
            interpretation=(
                "Material omissions captured separately from system findings."
            ),
            limitations=[
                "No semantic deduplication across separately entered human findings is performed."
            ],
        ),
        _metric(
            key="harmful_false_positive_count",
            label="Harmful false positives",
            domain="expert_review",
            unit="count",
            value=harmful,
            numerator=harmful,
            denominator=resolved_count,
            coverage=review_coverage,
            definition=(
                "Resolved system findings whose final decision is harmful_false_positive."
            ),
            interpretation=(
                "Potentially damaging unsupported conclusions requiring methodology review."
            ),
            limitations=["Only explicit reviewer/adjudicator decisions are counted."],
        ),
        _metric(
            key="reviewer_disagreement_rate",
            label="Reviewer disagreement",
            domain="expert_review",
            unit="ratio",
            value=_ratio(len(material_disagreement), len(independent)),
            numerator=len(material_disagreement),
            denominator=len(independent),
            coverage=_ratio(len(independent), len(selected_disagreements)),
            definition=(
                "Findings with material disagreement divided by findings with at least "
                "two independent reviewers; adjudicated disagreements remain in the numerator."
            ),
            interpretation="Methodology-consistency signal, not model accuracy.",
            limitations=[
                "The material-disagreement policy remains provisional pending client sign-off."
            ],
        ),
        _metric(
            key="operator_touch_time_minutes",
            label="Operator touch time",
            domain="workflow",
            unit="minutes_per_case_median",
            value=round(_median(touch_minutes), 4) if touch_minutes else None,
            numerator=round(sum(touch_minutes), 4) if touch_minutes else None,
            denominator=len(measured_cases),
            coverage=workflow_coverage,
            definition=(
                "Median of per-case sums of explicitly recorded operator touch seconds, "
                "converted to minutes."
            ),
            interpretation=(
                "Active operator effort kept separate from runtime and wall-clock duration."
            ),
            limitations=[
                "No touch time is inferred from audit timestamps or browser-session spans."
            ],
        ),
        _metric(
            key="manual_action_count",
            label="Manual action count",
            domain="workflow",
            unit="actions_per_case_median",
            value=_median(actions_per_case),
            numerator=sum(actions_per_case) if actions_per_case else None,
            denominator=len(measured_cases),
            coverage=workflow_coverage,
            definition=(
                "Median of per-case sums of explicitly recorded non-negative manual actions."
            ),
            interpretation=(
                "Workflow burden indicator; lower is not automatically better if controls are removed."
            ),
            limitations=["Action-count taxonomy must stay stable across compared runs."],
        ),
        _metric(
            key="historical_metric_coverage",
            label="Outcome coverage",
            domain="outcomes",
            unit="ratio",
            value=outcome_coverage,
            numerator=len(outcome_cases),
            denominator=len(selected_cases),
            coverage=1.0 if selected_cases else None,
            definition=(
                "Included cases with at least one provenance-bound observed campaign outcome "
                "divided by included cases."
            ),
            interpretation=(
                "Descriptive evidence coverage only; campaign outcomes are not attributed "
                "causally to an individual asset."
            ),
            limitations=[
                "Missing outcomes remain missing; uncertain linkage is not promoted to exact."
            ],
        ),
    ]
    return metrics
