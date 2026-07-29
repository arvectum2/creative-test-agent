from __future__ import annotations

import hashlib
import json
from typing import Any

from src.modules.creative_assets.service import get_asset_model
from src.shared.llm.base import LLMProvider

from . import pipeline as base_pipeline
from .visual_context import VisualEvidenceEnvelope, VisualEvidenceReference, resolve_visual_evidence


_VISUAL_CRITERION_FIELDS: dict[str, set[str]] = {
    "memorability": {"visual_summary", "hierarchy", "cognitive_load", "message_visual_binding"},
    "call_to_action": {"cta", "hierarchy", "readability"},
    "brand_fit": {"brand_logo_prominence", "packshot", "message_visual_binding"},
    "distinctiveness": {"visual_summary", "hierarchy", "promo_badge"},
    "message_visual_binding": {"message_visual_binding"},
    "visual_hierarchy": {"hierarchy"},
    "cognitive_load": {"cognitive_load", "hierarchy"},
    "readability": {"readability", "ocr_text"},
}

_RISK_TYPE_FIELDS: dict[str, set[str]] = {
    "brand_fit": {"brand_logo_prominence", "packshot", "message_visual_binding"},
    "negativity_risk": {"visual_risks"},
    "small_disclaimer": {"visual_risks", "readability"},
    "visual_clutter": {"cognitive_load", "hierarchy", "visual_risks"},
    "readability": {"readability", "ocr_text", "visual_risks"},
}

_SUMMARY_FIELDS = {"ocr_text", "visual_summary", "hierarchy"}
_UNRESOLVED_STATUSES = {"partial", "unsupported", "unassessed"}


def _canonical_hash(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _provider_is_stub(provider: LLMProvider) -> bool:
    return provider.__class__.__name__ == "StubProvider"


def _field_name(reference: VisualEvidenceReference) -> str:
    value = reference.observation_path.removeprefix("visual_context.")
    return value.split("[", 1)[0]


def _normalize_requested_refs(value: Any) -> tuple[list[str], list[str]]:
    if value is None:
        return [], []
    if not isinstance(value, list):
        return [], ["invalid_reference_list_type"]
    valid_shape: list[str] = []
    notes: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            notes.append("invalid_reference_id_shape")
            continue
        normalized = item.strip()
        if normalized not in valid_shape:
            valid_shape.append(normalized)
    return valid_shape, notes


def _reference_ids_for_fields(
    envelope: VisualEvidenceEnvelope,
    fields: set[str] | None,
) -> list[str]:
    if fields is None:
        return [item.reference_id for item in envelope.references]
    return [
        item.reference_id
        for item in envelope.references
        if _field_name(item) in fields
    ]


def _bind_references(
    *,
    envelope: VisualEvidenceEnvelope,
    requested_value: Any,
    allowed_fields: set[str] | None,
    visual_required: bool,
    auto_bind: bool,
) -> dict[str, Any]:
    reference_map = envelope.reference_map()
    requested, shape_notes = _normalize_requested_refs(requested_value)
    relevant_ids = _reference_ids_for_fields(envelope, allowed_fields)
    relevant_set = set(relevant_ids)

    if auto_bind and not requested:
        requested = list(relevant_ids)

    accepted: list[str] = []
    rejected: list[str] = []
    notes = list(shape_notes)
    for reference_id in requested:
        if reference_id not in reference_map:
            rejected.append(reference_id)
            notes.append(f"unknown_or_stale_reference:{reference_id}")
            continue
        if allowed_fields is not None and reference_id not in relevant_set:
            rejected.append(reference_id)
            notes.append(f"criterion_unrelated_reference:{reference_id}")
            continue
        accepted.append(reference_id)

    if accepted and rejected:
        status = "partial"
    elif accepted:
        status = "supported"
    elif rejected or shape_notes:
        status = "unsupported"
    elif visual_required:
        status = "unsupported" if relevant_ids else "unassessed"
        if status == "unsupported":
            notes.append("visual_finding_missing_required_reference")
        else:
            notes.append("no_populated_relevant_visual_observation")
    else:
        status = "not_used"

    return {
        "status": status,
        "accepted": accepted,
        "rejected": rejected,
        "notes": list(dict.fromkeys(notes)),
        "relevant_ids": relevant_ids,
    }


def _numeric_confidence(value: Any, default: float = 1.0) -> float:
    if isinstance(value, str):
        return {"high": 0.85, "medium": 0.6, "low": 0.3}.get(value.lower(), default)
    try:
        return min(max(float(value), 0.0), 1.0)
    except (TypeError, ValueError):
        return default


def _bound_confidence(
    current: Any,
    binding: dict[str, Any],
    reference_map: dict[str, VisualEvidenceReference],
) -> float:
    if binding["status"] in {"unsupported", "unassessed"}:
        return 0.0
    value = _numeric_confidence(current)
    accepted = binding["accepted"]
    if accepted:
        value = min(value, *(reference_map[item].confidence for item in accepted))
    return round(value, 4)


def _binding_record(
    *,
    stage: str,
    finding_key: str,
    binding: dict[str, Any],
) -> dict[str, Any]:
    return {
        "stage": stage,
        "finding_key": finding_key,
        "status": binding["status"],
        "visual_evidence_refs": binding["accepted"],
        "rejected_visual_evidence_refs": binding["rejected"],
        "notes": binding["notes"],
    }


def _apply_binding_metadata(item: dict[str, Any], binding: dict[str, Any]) -> None:
    item["visual_evidence_refs"] = binding["accepted"]
    item["rejected_visual_evidence_refs"] = binding["rejected"]
    item["visual_traceability_status"] = binding["status"]
    item["traceability_notes"] = binding["notes"]


def _references_include_assessed_absence(
    reference_ids: list[str],
    reference_map: dict[str, VisualEvidenceReference],
) -> bool:
    return any(
        reference_map[item].observation.get("presence") == "absent"
        for item in reference_ids
        if item in reference_map
    )


def _trace_summary(
    summary: dict[str, Any],
    envelope: VisualEvidenceEnvelope,
    *,
    provider_is_stub: bool,
) -> tuple[dict[str, Any], dict[str, Any]]:
    item = dict(summary)
    scope = str(item.get("evidence_scope") or "").lower()
    visual_required = scope in {"visual", "mixed"}
    binding = _bind_references(
        envelope=envelope,
        requested_value=item.get("visual_evidence_refs"),
        allowed_fields=_SUMMARY_FIELDS,
        visual_required=visual_required,
        auto_bind=provider_is_stub,
    )
    _apply_binding_metadata(item, binding)
    item["confidence"] = _bound_confidence(item.get("confidence", 1.0), binding, envelope.reference_map())
    if binding["status"] in {"unsupported", "unassessed"} and visual_required:
        item["summary"] = "Visual summary conclusion was not accepted because no valid relevant observation reference was supplied."
        item["key_message"] = item.get("key_message") or "unclear"
    return item, _binding_record(stage="creative_summary", finding_key="summary", binding=binding)


def _trace_audience(
    reactions: list[dict[str, Any]],
    envelope: VisualEvidenceEnvelope,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    traced: list[dict[str, Any]] = []
    bindings: list[dict[str, Any]] = []
    for index, raw in enumerate(reactions):
        item = dict(raw)
        scope = str(item.get("evidence_scope") or "").lower()
        visual_required = scope in {"visual", "mixed"}
        binding = _bind_references(
            envelope=envelope,
            requested_value=item.get("visual_evidence_refs"),
            allowed_fields=None,
            visual_required=visual_required,
            auto_bind=False,
        )
        _apply_binding_metadata(item, binding)
        item["confidence"] = _bound_confidence(item.get("confidence", 1.0), binding, envelope.reference_map())
        if binding["status"] in {"unsupported", "unassessed"} and visual_required:
            item["reaction"] = "Visual audience reaction was not accepted because it lacks a valid observation reference."
        traced.append(item)
        bindings.append(_binding_record(
            stage="audience_simulation",
            finding_key=f"audience_reaction:{index}",
            binding=binding,
        ))
    return traced, bindings


def _trace_scorecard(
    scorecard: list[dict[str, Any]],
    envelope: VisualEvidenceEnvelope,
    *,
    provider_is_stub: bool,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    traced: list[dict[str, Any]] = []
    bindings: list[dict[str, Any]] = []
    reference_map = envelope.reference_map()

    for index, raw in enumerate(scorecard):
        item = dict(raw)
        criterion = str(item.get("criterion") or "")
        allowed_fields = _VISUAL_CRITERION_FIELDS.get(criterion)
        visual_required = allowed_fields is not None
        binding = _bind_references(
            envelope=envelope,
            requested_value=item.get("visual_evidence_refs"),
            allowed_fields=allowed_fields,
            visual_required=visual_required,
            auto_bind=provider_is_stub and visual_required,
        )
        _apply_binding_metadata(item, binding)
        item["evidence_scope"] = "visual" if visual_required else str(item.get("evidence_scope") or "non_visual")
        item["confidence"] = _bound_confidence(item.get("confidence", 1.0), binding, reference_map)

        if visual_required and binding["status"] in {"unsupported", "unassessed"}:
            item["rationale"] = (
                "Visual criterion was not assessed: no populated relevant observation is available."
                if binding["status"] == "unassessed"
                else "Visual conclusion was not accepted: no valid relevant observation reference was supplied."
            )
            item["recommendation"] = "Complete or review visual extraction before accepting a conclusion for this criterion."
            notes = list(item.get("evidence_notes") or [])
            notes.extend(binding["notes"])
            item["evidence_notes"] = list(dict.fromkeys(notes))
        elif visual_required and _references_include_assessed_absence(binding["accepted"], reference_map):
            item["rationale"] = "The cited visual evidence records an explicitly assessed absence; no presence claim is accepted."
            item["recommendation"] = "Review whether the explicitly absent element is required for this creative."

        traced.append(item)
        bindings.append(_binding_record(
            stage="rubric_scoring",
            finding_key=f"scorecard:{index}:{criterion}",
            binding=binding,
        ))
    return traced, bindings


def _matching_visual_risk_fields(
    item: dict[str, Any],
    envelope: VisualEvidenceEnvelope,
) -> tuple[set[str] | None, list[str]]:
    risk_type = str(item.get("risk_type") or "")
    matching_ids = [
        reference.reference_id
        for reference in envelope.references
        if _field_name(reference) == "visual_risks"
        and str(reference.observation.get("risk_type") or "") == risk_type
    ]
    if matching_ids:
        return {"visual_risks"}, matching_ids
    return _RISK_TYPE_FIELDS.get(risk_type), []


def _trace_risks(
    risks: list[dict[str, Any]],
    envelope: VisualEvidenceEnvelope,
    *,
    provider_is_stub: bool,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    traced: list[dict[str, Any]] = []
    bindings: list[dict[str, Any]] = []
    reference_map = envelope.reference_map()

    for index, raw in enumerate(risks):
        item = dict(raw)
        scope = str(item.get("evidence_scope") or "").lower()
        allowed_fields, exact_risk_ids = _matching_visual_risk_fields(item, envelope)
        visual_required = scope in {"visual", "mixed"} or allowed_fields is not None
        requested_value = item.get("visual_evidence_refs")
        auto_bind = provider_is_stub and visual_required
        binding = _bind_references(
            envelope=envelope,
            requested_value=requested_value,
            allowed_fields=allowed_fields,
            visual_required=visual_required,
            auto_bind=auto_bind,
        )
        if auto_bind and exact_risk_ids and not requested_value:
            binding = _bind_references(
                envelope=envelope,
                requested_value=exact_risk_ids,
                allowed_fields={"visual_risks"},
                visual_required=True,
                auto_bind=False,
            )
        _apply_binding_metadata(item, binding)
        item["evidence_scope"] = "visual" if visual_required else (scope or "non_visual")
        item["confidence"] = _bound_confidence(item.get("confidence", 1.0), binding, reference_map)
        if visual_required and binding["status"] in {"unsupported", "unassessed"}:
            item["description"] = (
                "Visual risk was not assessed because no populated relevant observation is available."
                if binding["status"] == "unassessed"
                else "Visual risk conclusion was not accepted because it lacks a valid relevant observation reference."
            )
            item["mitigation"] = "Complete or manually review the visual evidence before accepting this risk."
        traced.append(item)
        bindings.append(_binding_record(
            stage="brand_safety",
            finding_key=f"risk:{index}:{item.get('risk_type', '')}",
            binding=binding,
        ))
    return traced, bindings


def _trace_compliance(
    compliance: dict[str, Any],
    envelope: VisualEvidenceEnvelope,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    result = dict(compliance or {})
    bindings: list[dict[str, Any]] = []
    reference_map = envelope.reference_map()
    traced_violations: list[dict[str, Any]] = []

    for index, raw in enumerate(result.get("violations") or []):
        item = dict(raw)
        scope = str(item.get("evidence_scope") or "").lower()
        visual_required = scope in {"visual", "mixed"}
        binding = _bind_references(
            envelope=envelope,
            requested_value=item.get("visual_evidence_refs"),
            allowed_fields=None,
            visual_required=visual_required,
            auto_bind=False,
        )
        _apply_binding_metadata(item, binding)
        item["evidence_scope"] = scope or "non_visual"
        if visual_required and binding["status"] in {"unsupported", "unassessed"}:
            item["details"] = "Visual compliance conclusion was not accepted because it lacks a valid observation reference."
        traced_violations.append(item)
        bindings.append(_binding_record(
            stage="brandbook_compliance",
            finding_key=f"violation:{index}:{item.get('rule', '')}",
            binding=binding,
        ))

    top_binding = _bind_references(
        envelope=envelope,
        requested_value=result.get("visual_evidence_refs"),
        allowed_fields=None,
        visual_required=False,
        auto_bind=False,
    )
    accepted = list(top_binding["accepted"])
    rejected = list(top_binding["rejected"])
    notes = list(top_binding["notes"])
    statuses = [top_binding["status"]]
    for violation in traced_violations:
        accepted.extend(violation.get("visual_evidence_refs") or [])
        rejected.extend(violation.get("rejected_visual_evidence_refs") or [])
        notes.extend(violation.get("traceability_notes") or [])
        statuses.append(str(violation.get("visual_traceability_status") or "not_used"))

    accepted = list(dict.fromkeys(accepted))
    rejected = list(dict.fromkeys(rejected))
    if any(status in {"unsupported", "unassessed"} for status in statuses):
        overall_status = "partial" if accepted else "unsupported"
    elif any(status == "partial" for status in statuses):
        overall_status = "partial"
    elif accepted:
        overall_status = "supported"
    else:
        overall_status = "not_used"

    result["violations"] = traced_violations
    result["visual_evidence_refs"] = accepted
    result["rejected_visual_evidence_refs"] = rejected
    result["visual_traceability_status"] = overall_status
    result["traceability_notes"] = list(dict.fromkeys(notes))
    if overall_status == "unsupported":
        result["confidence"] = 0.0
    elif accepted:
        result["confidence"] = round(min(
            _numeric_confidence(result.get("confidence", 1.0)),
            *(reference_map[item].confidence for item in accepted),
        ), 4)

    aggregate_binding = {
        "status": overall_status,
        "accepted": accepted,
        "rejected": rejected,
        "notes": result["traceability_notes"],
    }
    bindings.append(_binding_record(
        stage="brandbook_compliance",
        finding_key="overall",
        binding=aggregate_binding,
    ))
    return result, bindings


def _trace_final_recommendation(
    details: dict[str, Any],
    envelope: VisualEvidenceEnvelope,
    bindings: list[dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    result = dict(details or {})
    accepted: list[str] = []
    rejected: list[str] = []
    unresolved = False
    for binding in bindings:
        accepted.extend(binding.get("visual_evidence_refs") or [])
        rejected.extend(binding.get("rejected_visual_evidence_refs") or [])
        if binding.get("status") in _UNRESOLVED_STATUSES:
            unresolved = True
    accepted = list(dict.fromkeys(accepted))
    rejected = list(dict.fromkeys(rejected))

    if accepted and unresolved:
        status = "partial"
    elif accepted:
        status = "supported"
    elif envelope.references:
        status = "not_used"
    elif envelope.asset_requires_visual_evidence:
        status = "unassessed"
    else:
        status = "not_applicable"

    notes: list[str] = []
    if status == "partial":
        notes.append("final_recommendation_inherits_unresolved_visual_findings")
    elif status == "unassessed":
        notes.append("final_recommendation_has_no_populated_visual_observations")

    result["visual_evidence_refs"] = accepted
    result["rejected_visual_evidence_refs"] = rejected
    result["visual_traceability_status"] = status
    result["traceability_notes"] = notes
    binding = {
        "status": status,
        "accepted": accepted,
        "rejected": rejected,
        "notes": notes,
    }
    return result, _binding_record(
        stage="final_recommendation",
        finding_key="decision",
        binding=binding,
    )


def apply_visual_traceability(
    result: dict[str, Any],
    envelope: VisualEvidenceEnvelope,
    *,
    provider_is_stub: bool,
) -> dict[str, Any]:
    traced = dict(result)
    bindings: list[dict[str, Any]] = []

    summary_details, summary_binding = _trace_summary(
        traced.get("summary_details") or {"summary": traced.get("summary", "")},
        envelope,
        provider_is_stub=provider_is_stub,
    )
    bindings.append(summary_binding)

    audience, audience_bindings = _trace_audience(traced.get("audience_reactions") or [], envelope)
    bindings.extend(audience_bindings)

    scorecard, score_bindings = _trace_scorecard(
        traced.get("scorecard") or [],
        envelope,
        provider_is_stub=provider_is_stub,
    )
    bindings.extend(score_bindings)

    risks, risk_bindings = _trace_risks(
        traced.get("risks") or [],
        envelope,
        provider_is_stub=provider_is_stub,
    )
    bindings.extend(risk_bindings)

    compliance, compliance_bindings = _trace_compliance(
        traced.get("brandbook_compliance") or {},
        envelope,
    )
    bindings.extend(compliance_bindings)

    final_details, final_binding = _trace_final_recommendation(
        traced.get("final_recommendation_details") or {},
        envelope,
        bindings,
    )
    bindings.append(final_binding)

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
        }
        for item in scorecard
    ]

    unresolved_count = sum(
        1 for binding in bindings
        if binding["status"] in _UNRESOLVED_STATUSES
        and binding["stage"] in {"rubric_scoring", "brand_safety", "brandbook_compliance"}
    )
    if not envelope.asset_requires_visual_evidence:
        trace_status = "not_applicable"
    elif not envelope.references:
        trace_status = "unassessed"
    elif unresolved_count:
        trace_status = "needs_review"
    else:
        trace_status = "complete"

    accepted_ids = list(dict.fromkeys(
        reference_id
        for binding in bindings
        for reference_id in binding.get("visual_evidence_refs", [])
    ))
    rejected_ids = list(dict.fromkeys(
        reference_id
        for binding in bindings
        for reference_id in binding.get("rejected_visual_evidence_refs", [])
    ))
    trace_payload = {
        "schema_name": "visual_evidence_trace",
        "schema_version": "1.0",
        "creative_asset_id": envelope.creative_asset_id,
        "visual_evidence_fingerprint": envelope.fingerprint,
        "status": trace_status,
        "reference_count": len(envelope.references),
        "accepted_reference_ids": accepted_ids,
        "rejected_reference_ids": rejected_ids,
        "unresolved_visual_finding_count": unresolved_count,
        "bindings": bindings,
    }
    trace_payload["fingerprint"] = _canonical_hash(trace_payload)

    traced.update({
        "summary": summary_details.get("summary", traced.get("summary", "")),
        "summary_details": summary_details,
        "audience_reactions": audience,
        "scorecard": scorecard,
        "risks": risks,
        "brandbook_compliance": compliance,
        "final_recommendation_details": final_details,
        "findings": findings,
        "visual_evidence": envelope.model_dump(mode="json", exclude_none=False),
        "visual_evidence_trace": trace_payload,
        "visual_traceability_status": trace_status,
        "unresolved_visual_finding_count": unresolved_count,
    })
    return traced


def run_traceable_pipeline(
    creative_asset_id: str,
    brand_profile_id: str | None,
    audience_profile_ids: list[str],
    rubric_id: str | None,
    provider: LLMProvider,
) -> dict[str, Any]:
    """Run the canonical pipeline and fail closed on untraceable visual findings."""

    asset = get_asset_model(creative_asset_id)
    visual_evidence = resolve_visual_evidence(asset)

    summary = base_pipeline.creative_summary(
        creative_asset_id,
        provider,
        visual_evidence=visual_evidence,
    )
    audience = base_pipeline.audience_simulation(
        creative_asset_id,
        audience_profile_ids,
        provider,
        visual_evidence=visual_evidence,
    )
    risks = base_pipeline.brand_safety_review(
        creative_asset_id,
        brand_profile_id,
        provider,
        visual_evidence=visual_evidence,
    )
    compliance = base_pipeline.brandbook_compliance_review(
        creative_asset_id,
        brand_profile_id,
        provider,
        context_text=base_pipeline._build_brandbook_context(brand_profile_id),
        visual_evidence=visual_evidence,
    )
    scorecard, overall = base_pipeline.rubric_scoring(
        creative_asset_id,
        rubric_id,
        provider,
        visual_evidence=visual_evidence,
    )
    recommendation_details = base_pipeline._final_recommendation_result(
        creative_asset_id,
        summary,
        scorecard,
        risks,
        audience,
        provider,
        brandbook_compliance=compliance,
        visual_evidence=visual_evidence,
    )

    visual_context_payload = (
        visual_evidence.visual_context.model_dump(mode="json", exclude_none=False)
        if visual_evidence.visual_context is not None
        else None
    )
    result = {
        "summary": summary.get("summary", ""),
        "summary_details": summary,
        "scorecard": scorecard,
        "risks": risks,
        "audience_reactions": audience,
        "final_recommendation": recommendation_details["final_recommendation"],
        "final_recommendation_details": recommendation_details,
        "findings": [],
        "overall_score": overall,
        "brandbook_compliance": compliance,
        "visual_context": visual_context_payload,
        "visual_evidence": visual_evidence.model_dump(mode="json", exclude_none=False),
        "visual_evidence_confidence": visual_evidence.evidence_confidence,
    }
    return apply_visual_traceability(
        result,
        visual_evidence,
        provider_is_stub=_provider_is_stub(provider),
    )
