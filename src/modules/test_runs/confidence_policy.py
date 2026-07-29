from __future__ import annotations

import hashlib
import json
from typing import Any

from src.shared.llm.base import LLMProvider

from .visual_context import VisualEvidenceEnvelope


POLICY_ID = "visual-confidence-abstention-v1"
POLICY_SCHEMA_NAME = "visual_confidence_abstention_policy"
POLICY_SCHEMA_VERSION = "1.0"

# Provisional operational gates. They are not validated model-accuracy thresholds.
HARD_ABSTAIN_BELOW = 0.45
CLIENT_RELEASE_MIN = 0.65
HIGH_CONFIDENCE_MIN = 0.75

_VISUAL_STATUSES = {"supported", "partial", "unsupported", "unassessed"}
_ABSTENTION_STATUSES = {"accepted", "review_required", "abstained", "not_applicable"}


def _canonical_hash(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _numeric_confidence(value: Any, default: float = 1.0) -> float:
    if isinstance(value, str):
        value = {"high": 0.85, "medium": 0.6, "low": 0.3}.get(value.lower(), default)
    try:
        return round(min(max(float(value), 0.0), 1.0), 4)
    except (TypeError, ValueError):
        return round(default, 4)


def confidence_band(value: float | None, *, applicable: bool = True) -> str:
    if not applicable or value is None:
        return "not_applicable"
    numeric = _numeric_confidence(value, 0.0)
    if numeric >= HIGH_CONFIDENCE_MIN:
        return "high"
    if numeric >= HARD_ABSTAIN_BELOW:
        return "medium"
    return "low"


def _is_visual_finding(item: dict[str, Any]) -> bool:
    scope = str(item.get("evidence_scope") or "").strip().lower()
    trace_status = str(item.get("visual_traceability_status") or "not_used").strip().lower()
    return (
        scope in {"visual", "mixed"}
        or trace_status in _VISUAL_STATUSES
        or bool(item.get("visual_evidence_refs"))
        or bool(item.get("rejected_visual_evidence_refs"))
    )


def _finding_policy(
    item: dict[str, Any],
    *,
    stage: str,
    finding_key: str,
    visual_policy_applicable: bool,
    reference_confidences: dict[str, float],
) -> tuple[dict[str, Any], dict[str, Any]]:
    decorated = dict(item)
    visual_required = visual_policy_applicable and _is_visual_finding(decorated)
    confidence = _numeric_confidence(decorated.get("confidence"), 1.0)
    trace_status = str(decorated.get("visual_traceability_status") or "not_used").strip().lower()
    accepted_refs = list(decorated.get("visual_evidence_refs") or [])
    reasons: list[str] = []

    if not visual_required:
        status = "not_applicable"
    elif trace_status in {"unsupported", "unassessed"}:
        status = "abstained"
        reasons.append(f"traceability_{trace_status}")
    elif not accepted_refs:
        status = "abstained"
        reasons.append("no_accepted_visual_reference")
    elif confidence < HARD_ABSTAIN_BELOW:
        status = "abstained"
        reasons.append("finding_confidence_below_hard_floor")
    elif trace_status == "partial":
        status = "review_required"
        reasons.append("partial_visual_traceability")
    elif confidence < CLIENT_RELEASE_MIN:
        status = "review_required"
        reasons.append("finding_confidence_below_client_release_gate")
    else:
        status = "accepted"

    if status not in _ABSTENTION_STATUSES:
        raise ValueError(f"invalid visual abstention status: {status}")

    decorated["visual_confidence_score"] = confidence if visual_required else None
    decorated["visual_confidence_band"] = confidence_band(confidence, applicable=visual_required)
    decorated["visual_abstention_status"] = status
    decorated["visual_abstention_reasons"] = list(dict.fromkeys(reasons))
    decorated["visual_assessment_allowed"] = status != "abstained"
    decorated["visual_client_release_allowed"] = status in {"accepted", "not_applicable"}

    observation_confidences = [
        reference_confidences[reference_id]
        for reference_id in accepted_refs
        if reference_id in reference_confidences
    ]
    record = {
        "stage": stage,
        "finding_key": finding_key,
        "visual_required": visual_required,
        "traceability_status": trace_status,
        "finding_confidence": confidence if visual_required else None,
        "observation_confidences": observation_confidences,
        "minimum_observation_confidence": min(observation_confidences) if observation_confidences else None,
        "confidence_band": decorated["visual_confidence_band"],
        "abstention_status": status,
        "reasons": decorated["visual_abstention_reasons"],
        "visual_evidence_refs": accepted_refs,
    }
    return decorated, record


def _envelope_policy(envelope: VisualEvidenceEnvelope) -> dict[str, Any]:
    reasons: list[str] = []
    confidence = envelope.evidence_confidence

    if not envelope.asset_requires_visual_evidence:
        status = "not_applicable"
    elif envelope.status == "missing" or not envelope.references:
        status = "abstained"
        reasons.append("visual_evidence_missing")
    elif confidence < HARD_ABSTAIN_BELOW:
        status = "abstained"
        reasons.append("evidence_confidence_below_hard_floor")
    elif envelope.status == "limited" or confidence < CLIENT_RELEASE_MIN:
        status = "review_required"
        if envelope.status == "limited":
            reasons.append("visual_evidence_limited")
        if confidence < CLIENT_RELEASE_MIN:
            reasons.append("evidence_confidence_below_client_release_gate")
    else:
        status = "accepted"

    return {
        "status": status,
        "confidence": confidence if envelope.asset_requires_visual_evidence else None,
        "confidence_band": confidence_band(confidence, applicable=envelope.asset_requires_visual_evidence),
        "reasons": list(dict.fromkeys(reasons)),
        "extraction_confidence": envelope.extraction_confidence,
        "evidence_confidence": envelope.evidence_confidence,
        "completeness_ratio": envelope.completeness_ratio,
        "visual_evidence_status": envelope.status,
    }


def _aggregate_compliance(
    compliance: dict[str, Any],
    violation_records: list[dict[str, Any]],
    *,
    visual_policy_applicable: bool,
    reference_confidences: dict[str, float],
) -> tuple[dict[str, Any], dict[str, Any]]:
    item = dict(compliance or {})
    traced, own_record = _finding_policy(
        item,
        stage="brandbook_compliance",
        finding_key="overall",
        visual_policy_applicable=visual_policy_applicable,
        reference_confidences=reference_confidences,
    )
    visual_records = [record for record in violation_records if record["visual_required"]]
    statuses = [record["abstention_status"] for record in visual_records]
    reasons = list(traced.get("visual_abstention_reasons") or [])

    if any(status == "abstained" for status in statuses):
        aggregate_status = "abstained"
        reasons.append("compliance_contains_abstained_visual_violation")
    elif any(status == "review_required" for status in statuses):
        aggregate_status = "review_required"
        reasons.append("compliance_contains_visual_violation_requiring_review")
    elif any(status == "accepted" for status in statuses):
        aggregate_status = "accepted"
    else:
        aggregate_status = traced["visual_abstention_status"]

    traced["visual_abstention_status"] = aggregate_status
    traced["visual_abstention_reasons"] = list(dict.fromkeys(reasons))
    traced["visual_assessment_allowed"] = aggregate_status != "abstained"
    traced["visual_client_release_allowed"] = aggregate_status in {"accepted", "not_applicable"}

    own_record["abstention_status"] = aggregate_status
    own_record["reasons"] = traced["visual_abstention_reasons"]
    return traced, own_record


def _decision_policy(
    *,
    result: dict[str, Any],
    envelope_policy: dict[str, Any],
    finding_records: list[dict[str, Any]],
) -> dict[str, Any]:
    details = dict(result.get("final_recommendation_details") or {})
    proposed = str(
        details.get("proposed_recommendation")
        or details.get("final_recommendation")
        or result.get("final_recommendation")
        or "revise"
    )

    critical_stages = {"rubric_scoring", "brand_safety", "brandbook_compliance"}
    critical = [
        record
        for record in finding_records
        if record["visual_required"] and record["stage"] in critical_stages
    ]
    advisory = [
        record
        for record in finding_records
        if record["visual_required"] and record["stage"] not in critical_stages
    ]

    hard_blockers = [
        f"{record['stage']}:{record['finding_key']}"
        for record in critical
        if record["abstention_status"] == "abstained"
    ]
    review_blockers = [
        f"{record['stage']}:{record['finding_key']}"
        for record in critical
        if record["abstention_status"] == "review_required"
    ]
    advisory_review = [
        f"{record['stage']}:{record['finding_key']}"
        for record in advisory
        if record["abstention_status"] in {"abstained", "review_required"}
    ]

    reasons: list[str] = []
    if envelope_policy["status"] == "not_applicable":
        release_status = "not_applicable"
        abstention_status = "not_applicable"
        effective = proposed
    elif envelope_policy["status"] == "abstained" or hard_blockers:
        release_status = "abstained"
        abstention_status = "abstained"
        effective = "abstain"
        reasons.extend(envelope_policy["reasons"])
        reasons.extend(f"critical_finding_abstained:{item}" for item in hard_blockers)
    elif envelope_policy["status"] == "review_required" or review_blockers or advisory_review:
        release_status = "manual_review_required"
        abstention_status = "review_required"
        effective = "manual_review"
        reasons.extend(envelope_policy["reasons"])
        reasons.extend(f"critical_finding_review_required:{item}" for item in review_blockers)
        reasons.extend(f"advisory_visual_finding_unresolved:{item}" for item in advisory_review)
    else:
        release_status = "released"
        abstention_status = "accepted"
        effective = proposed

    visual_confidences = [
        float(record["finding_confidence"])
        for record in finding_records
        if record["visual_required"] and record["finding_confidence"] is not None
    ]
    if envelope_policy["confidence"] is not None:
        visual_confidences.append(float(envelope_policy["confidence"]))
    policy_confidence = round(min(visual_confidences), 4) if visual_confidences else None

    return {
        "proposed_recommendation": proposed,
        "effective_recommendation": effective,
        "release_status": release_status,
        "visual_abstention_status": abstention_status,
        "visual_abstention_reasons": list(dict.fromkeys(reasons)),
        "policy_confidence_score": policy_confidence,
        "policy_confidence_band": confidence_band(policy_confidence, applicable=policy_confidence is not None),
        "critical_hard_blockers": hard_blockers,
        "critical_review_blockers": review_blockers,
        "advisory_review_items": advisory_review,
    }


def validate_visual_confidence_policy_manifest(payload: dict[str, Any]) -> None:
    if payload.get("schema_name") != POLICY_SCHEMA_NAME:
        raise ValueError("visual confidence policy schema name mismatch")
    if payload.get("schema_version") != POLICY_SCHEMA_VERSION:
        raise ValueError("visual confidence policy schema version mismatch")
    if payload.get("policy_id") != POLICY_ID:
        raise ValueError("visual confidence policy id mismatch")
    supplied = str(payload.get("fingerprint") or "")
    expected = _canonical_hash({key: value for key, value in payload.items() if key != "fingerprint"})
    if supplied != expected:
        raise ValueError("visual confidence policy fingerprint mismatch")


def apply_visual_confidence_policy(
    result: dict[str, Any],
    envelope: VisualEvidenceEnvelope,
) -> dict[str, Any]:
    """Apply deterministic confidence gates without changing legacy diagnostic scores."""

    governed = dict(result)
    records: list[dict[str, Any]] = []
    visual_policy_applicable = envelope.asset_requires_visual_evidence
    reference_confidences = {
        reference.reference_id: reference.confidence
        for reference in envelope.references
    }

    summary, summary_record = _finding_policy(
        governed.get("summary_details") or {"summary": governed.get("summary", "")},
        stage="creative_summary",
        finding_key="summary",
        visual_policy_applicable=visual_policy_applicable,
        reference_confidences=reference_confidences,
    )
    records.append(summary_record)

    audience: list[dict[str, Any]] = []
    for index, raw in enumerate(governed.get("audience_reactions") or []):
        item, record = _finding_policy(
            dict(raw),
            stage="audience_simulation",
            finding_key=f"audience_reaction:{index}",
            visual_policy_applicable=visual_policy_applicable,
            reference_confidences=reference_confidences,
        )
        audience.append(item)
        records.append(record)

    scorecard: list[dict[str, Any]] = []
    for index, raw in enumerate(governed.get("scorecard") or []):
        criterion = str(raw.get("criterion") or "")
        item, record = _finding_policy(
            dict(raw),
            stage="rubric_scoring",
            finding_key=f"scorecard:{index}:{criterion}",
            visual_policy_applicable=visual_policy_applicable,
            reference_confidences=reference_confidences,
        )
        scorecard.append(item)
        records.append(record)

    risks: list[dict[str, Any]] = []
    for index, raw in enumerate(governed.get("risks") or []):
        risk_type = str(raw.get("risk_type") or "")
        item, record = _finding_policy(
            dict(raw),
            stage="brand_safety",
            finding_key=f"risk:{index}:{risk_type}",
            visual_policy_applicable=visual_policy_applicable,
            reference_confidences=reference_confidences,
        )
        risks.append(item)
        records.append(record)

    compliance = dict(governed.get("brandbook_compliance") or {})
    violations: list[dict[str, Any]] = []
    violation_records: list[dict[str, Any]] = []
    for index, raw in enumerate(compliance.get("violations") or []):
        rule = str(raw.get("rule") or "")
        item, record = _finding_policy(
            dict(raw),
            stage="brandbook_compliance",
            finding_key=f"violation:{index}:{rule}",
            visual_policy_applicable=visual_policy_applicable,
            reference_confidences=reference_confidences,
        )
        violations.append(item)
        violation_records.append(record)
        records.append(record)
    compliance["violations"] = violations
    compliance, compliance_record = _aggregate_compliance(
        compliance,
        violation_records,
        visual_policy_applicable=visual_policy_applicable,
        reference_confidences=reference_confidences,
    )
    records.append(compliance_record)

    envelope_record = _envelope_policy(envelope)
    decision = _decision_policy(
        result={**governed, "final_recommendation_details": governed.get("final_recommendation_details") or {}},
        envelope_policy=envelope_record,
        finding_records=records,
    )

    final_details = dict(governed.get("final_recommendation_details") or {})
    final_details.update(decision)

    findings = [
        {
            "criterion": item.get("criterion", ""),
            "score": item.get("score", 0.0),
            "explanation": item.get("rationale", ""),
            "confidence": item.get("confidence", 1.0),
            "evidence_notes": item.get("evidence_notes", []),
            "visual_evidence_refs": item.get("visual_evidence_refs", []),
            "rejected_visual_evidence_refs": item.get("rejected_visual_evidence_refs", []),
            "visual_traceability_status": item.get("visual_traceability_status", "not_used"),
            "traceability_notes": item.get("traceability_notes", []),
            "visual_confidence_score": item.get("visual_confidence_score"),
            "visual_confidence_band": item.get("visual_confidence_band", "not_applicable"),
            "visual_abstention_status": item.get("visual_abstention_status", "not_applicable"),
            "visual_abstention_reasons": item.get("visual_abstention_reasons", []),
            "visual_assessment_allowed": item.get("visual_assessment_allowed", True),
            "visual_client_release_allowed": item.get("visual_client_release_allowed", True),
        }
        for item in scorecard
    ]

    abstained_count = sum(record["abstention_status"] == "abstained" for record in records)
    review_count = sum(record["abstention_status"] == "review_required" for record in records)
    manifest = {
        "schema_name": POLICY_SCHEMA_NAME,
        "schema_version": POLICY_SCHEMA_VERSION,
        "policy_id": POLICY_ID,
        "thresholds": {
            "hard_abstain_below": HARD_ABSTAIN_BELOW,
            "client_release_min": CLIENT_RELEASE_MIN,
            "high_confidence_min": HIGH_CONFIDENCE_MIN,
            "calibration_status": "provisional_operational_gate_not_validated_accuracy",
        },
        "creative_asset_id": envelope.creative_asset_id,
        "visual_evidence_fingerprint": envelope.fingerprint,
        "visual_trace_fingerprint": (governed.get("visual_evidence_trace") or {}).get("fingerprint"),
        "envelope": envelope_record,
        "finding_counts": {
            "total": len(records),
            "visual": sum(record["visual_required"] for record in records),
            "accepted": sum(record["abstention_status"] == "accepted" for record in records),
            "review_required": review_count,
            "abstained": abstained_count,
            "not_applicable": sum(record["abstention_status"] == "not_applicable" for record in records),
        },
        "findings": records,
        "decision": decision,
    }
    manifest["fingerprint"] = _canonical_hash(manifest)
    validate_visual_confidence_policy_manifest(manifest)

    governed.update({
        "summary_details": summary,
        "audience_reactions": audience,
        "scorecard": scorecard,
        "risks": risks,
        "brandbook_compliance": compliance,
        "findings": findings,
        "final_recommendation_details": final_details,
        "effective_recommendation": decision["effective_recommendation"],
        "visual_decision_status": decision["release_status"],
        "visual_abstention_count": abstained_count,
        "visual_review_required_count": review_count,
        "visual_confidence_policy": manifest,
    })
    return governed


def run_confidence_aware_pipeline(
    creative_asset_id: str,
    brand_profile_id: str | None,
    audience_profile_ids: list[str],
    rubric_id: str | None,
    provider: LLMProvider,
) -> dict[str, Any]:
    """Run traceability first, then apply the canonical abstention policy."""

    from .traceability import run_traceable_pipeline

    result = run_traceable_pipeline(
        creative_asset_id=creative_asset_id,
        brand_profile_id=brand_profile_id,
        audience_profile_ids=audience_profile_ids,
        rubric_id=rubric_id,
        provider=provider,
    )
    envelope = VisualEvidenceEnvelope.model_validate(result["visual_evidence"])
    return apply_visual_confidence_policy(result, envelope)
