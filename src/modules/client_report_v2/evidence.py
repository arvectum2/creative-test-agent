from __future__ import annotations

import hashlib
import re
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Iterable

REPORT_ID = "evidence-bound-client-report-v2"
REPORT_VERSION = "2.0.0"


def as_dict(value: Any) -> dict[str, Any]:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    return deepcopy(value) if isinstance(value, dict) else {}


def as_list(value: Any) -> list[Any]:
    return deepcopy(value) if isinstance(value, list) else []


def clean(value: Any, limit: int = 1000) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def optional_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def stable_id(prefix: str, *parts: Any) -> str:
    raw = "|".join(clean(item, 500) for item in parts)
    return f"{prefix}:{hashlib.sha256(raw.encode()).hexdigest()[:20]}"


def compose_report_evidence(
    workspace: Any,
    *,
    expert_assessments: Iterable[Any] = (),
    locale: str = "ru",
    generated_at: str | None = None,
) -> dict[str, Any]:
    if locale not in {"ru", "en"}:
        raise ValueError("locale must be 'ru' or 'en'")
    source = as_dict(workspace)
    experts = {clean(as_dict(item).get("finding_id"), 240): as_dict(item) for item in expert_assessments}
    registry: dict[str, dict[str, Any]] = {}
    campaigns: list[dict[str, Any]] = []
    findings: list[dict[str, Any]] = []
    outcomes: list[dict[str, Any]] = []
    limitations: list[dict[str, Any]] = []
    assessments: list[dict[str, Any]] = []
    asset_count = 0

    for ci, raw_campaign in enumerate(as_list(source.get("campaigns"))):
        c = as_dict(raw_campaign)
        campaign_id = clean(c.get("campaign_id") or c.get("case_id") or ci)
        campaign_ref = f"campaign:{campaign_id}"
        registry[campaign_ref] = {"layer": "observed_fact", "scope": "campaign_set", "source_type": "normalized_campaign", "source_id": campaign_id}
        campaign = {
            "campaign_id": campaign_id,
            "case_id": c.get("case_id"), "brand": c.get("brand"), "product": c.get("product"),
            "platform": c.get("platform"), "period_start": c.get("period_start"), "period_end": c.get("period_end"),
            "scope": "campaign_set", "campaign_level_outcomes": True,
            "individual_asset_attribution_allowed": False, "evidence_references": [campaign_ref], "assets": [],
        }
        for raw_limitation in as_list(c.get("limitations")):
            item = as_dict(raw_limitation)
            limitations.append({
                "limitation_id": stable_id("limitation", campaign_id, item.get("code"), item.get("message")),
                "campaign_id": campaign_id, "code": clean(item.get("code") or "campaign_limitation", 120),
                "severity": clean(item.get("severity") or "warning", 40), "message": clean(item.get("message"), 1200),
                "context": as_dict(item.get("context")), "evidence_references": [campaign_ref],
            })
        for ai, raw_asset in enumerate(as_list(c.get("assets"))):
            a = as_dict(raw_asset); asset_count += 1
            record_id = clean(a.get("creative_record_id") or f"{campaign_id}-{ai}")
            asset_ref = f"asset:{record_id}"
            registry[asset_ref] = {"layer": "observed_fact", "scope": "individual_asset", "source_type": "creative_record", "source_id": record_id}
            campaign["assets"].append({
                "creative_record_id": record_id, "creative_asset_id": a.get("creative_asset_id"), "title": a.get("title"),
                "filename": a.get("filename"), "inferred_platform": a.get("inferred_platform"),
                "linkage_status": a.get("linkage_status"), "linkage_confidence": optional_float(a.get("linkage_confidence")),
                "accepted_for_campaign_set": bool(a.get("accepted_for_campaign_set")), "scope": "individual_asset",
                "evidence_references": [asset_ref, campaign_ref],
            })
            diagnostic = as_dict(a.get("diagnostic")); test_run_id = clean(diagnostic.get("test_run_id") or f"missing-{record_id}")
            for fi, raw_finding in enumerate(as_list(diagnostic.get("findings"))):
                f = as_dict(raw_finding); finding_id = f"finding:{test_run_id}:{fi + 1}"
                run_ref = f"test-run:{test_run_id}:finding:{fi + 1}"
                registry[run_ref] = {"layer": "agent_diagnostic", "scope": "individual_asset", "source_type": "test_run_finding", "source_id": test_run_id, "source_index": fi}
                refs = [asset_ref, run_ref]; visual_refs: list[str] = []
                for raw_ref in as_list(f.get("visual_evidence_refs")):
                    ref = clean(raw_ref, 240)
                    if ref and ref not in visual_refs:
                        visual_refs.append(ref); refs.append(ref)
                        registry.setdefault(ref, {"layer": "visual_observation_reference", "scope": "individual_asset", "source_type": "visual_evidence_reference", "source_id": test_run_id, "resolution_status": "referenced_by_test_run"})
                findings.append({
                    "finding_id": finding_id, "campaign_id": campaign_id, "creative_record_id": record_id,
                    "creative_asset_id": a.get("creative_asset_id"), "test_run_id": diagnostic.get("test_run_id"),
                    "diagnostic_status": diagnostic.get("status") or "missing",
                    "criterion": clean(f.get("criterion") or f.get("risk_type") or "finding", 240),
                    "score": optional_float(f.get("score")),
                    "text": clean(f.get("explanation") or f.get("rationale") or f.get("description") or f.get("recommendation"), 1200),
                    "scope": "individual_asset", "confidence": optional_float(f.get("confidence")),
                    "visual_confidence": optional_float(f.get("visual_confidence_score")),
                    "visual_confidence_band": f.get("visual_confidence_band"),
                    "visual_abstention_status": f.get("visual_abstention_status"),
                    "visual_traceability_status": f.get("visual_traceability_status"),
                    "evidence_references": refs, "visual_evidence_references": visual_refs,
                    "rejected_visual_evidence_references": as_list(f.get("rejected_visual_evidence_refs")),
                })
                expert = experts.get(finding_id)
                assessments.append({
                    "finding_id": finding_id,
                    "verdict": expert.get("verdict") if expert else "not_reviewed",
                    "rationale": clean(expert.get("rationale"), 2000) if expert else "",
                    "reviewer_role": clean(expert.get("reviewer_role"), 160) if expert else "",
                    "confidence": optional_float(expert.get("confidence")) if expert else None,
                    "status": "reviewed" if expert and expert.get("verdict") != "not_reviewed" else "not_reviewed",
                    "evidence_references": [asset_ref, run_ref],
                })
        for raw_outcome in as_list(c.get("outcomes")):
            o = as_dict(raw_outcome); observation_id = clean(o.get("observation_id") or stable_id("observation", campaign_id, o))
            outcome_ref = f"outcome:{observation_id}"
            registry[outcome_ref] = {"layer": "factual_outcome", "scope": "campaign_set", "source_type": "performance_observation", "source_id": observation_id, "source_sheet": o.get("source_sheet"), "source_row_number": o.get("source_row_number")}
            outcomes.append({
                "observation_id": observation_id, "campaign_id": campaign_id, "metric": o.get("metric"),
                "metric_label": o.get("metric_label"), "control_n": o.get("control_n"), "test_n": o.get("test_n"),
                "cg_rate": optional_float(o.get("cg_rate")), "tg_rate": optional_float(o.get("tg_rate")),
                "uplift_pp_descriptive": optional_float(o.get("uplift_pp_descriptive")), "evidence_status": o.get("evidence_status"),
                "period_start": o.get("period_start"), "period_end": o.get("period_end"), "platform": o.get("platform"),
                "scope": "campaign_set", "individual_asset_attribution_allowed": False,
                "causal_interpretation_allowed": False, "numeric_prediction_generated": False,
                "notes": as_list(o.get("notes")), "evidence_references": [campaign_ref, outcome_ref],
            })
        campaigns.append(campaign)

    reviewed = sum(item["status"] == "reviewed" for item in assessments)
    unreviewed = len(assessments) - reviewed
    abstained = sum(str(item.get("visual_abstention_status") or "") not in {"", "accepted", "not_applicable"} for item in findings)
    low_trace = sum(str(item.get("visual_traceability_status") or "") in {"unsupported", "unassessed", "invalid", "missing"} for item in findings)
    release_status = "evidence_limited" if not findings or not outcomes else ("manual_review_required" if unreviewed or abstained or low_trace else "controlled_client_release")
    boundary_message = (
        "Campaign-level outcomes нельзя атрибутировать отдельному креативу. Descriptive difference не является causal lift или прогнозом."
        if locale == "ru" else
        "Campaign-level outcomes must not be attributed to an individual creative. Descriptive difference is not causal lift or a prediction."
    )
    limitations.append({"limitation_id": "boundary:campaign-outcome-attribution", "campaign_id": None, "code": "campaign_outcomes_not_asset_attributable", "severity": "blocking_claim_boundary", "message": boundary_message, "context": {}, "evidence_references": []})
    if unreviewed:
        limitations.append({"limitation_id": "boundary:unreviewed-findings", "campaign_id": None, "code": "expert_review_incomplete", "severity": "warning", "message": f"{unreviewed} finding(s) have no expert verdict and remain explicitly not_reviewed.", "context": {"unreviewed_finding_count": unreviewed}, "evidence_references": []})
    if not outcomes:
        limitations.append({"limitation_id": "boundary:missing-outcomes", "campaign_id": None, "code": "factual_outcomes_missing", "severity": "high", "message": "No factual CG/TG outcomes are available.", "context": {}, "evidence_references": []})

    return {
        "report_id": REPORT_ID, "report_version": REPORT_VERSION,
        "generated_at": generated_at or datetime.now(timezone.utc).isoformat(), "locale": locale,
        "project": {"id": source.get("project_id"), "name": source.get("project_name"), "normalization_run_id": source.get("normalization_run_id"), "source_fingerprint": source.get("source_fingerprint"), "mapping_version": source.get("mapping_version"), "generated_from_loader": source.get("generated_from_loader")},
        "summary": {"campaign_count": len(campaigns), "asset_count": asset_count, "finding_count": len(findings), "reviewed_finding_count": reviewed, "unreviewed_finding_count": unreviewed, "outcome_count": len(outcomes), "limitation_count": len(limitations), "release_status": release_status},
        "observed_facts": {"campaigns": campaigns}, "agent_diagnostics": {"findings": findings},
        "factual_outcomes": {"outcomes": outcomes}, "expert_assessment": {"assessments": assessments},
        "limitations_and_confidence": {"limitations": limitations, "confidence_summary": {"finding_count": len(findings), "findings_with_numeric_confidence": sum(item.get("confidence") is not None for item in findings), "visual_abstention_count": abstained, "low_traceability_count": low_trace, "unreviewed_finding_count": unreviewed}},
        "evidence_registry": registry,
        "claim_boundary": {"causal_interpretation_allowed": False, "numeric_uplift_prediction_generated": False, "individual_asset_outcome_attribution_allowed": False, "missing_values_inferred": False, "diagnostics_are_model_outputs_not_factual_outcomes": True, "expert_assessment_fabricated": False, "campaign_set_and_individual_asset_scopes_separated": True},
    }


def validate_evidence(evidence: dict[str, Any]) -> list[str]:
    errors: list[str] = []; registry = evidence.get("evidence_registry") or {}
    findings = (evidence.get("agent_diagnostics") or {}).get("findings") or []
    outcomes = (evidence.get("factual_outcomes") or {}).get("outcomes") or []
    assessments = (evidence.get("expert_assessment") or {}).get("assessments") or []
    for item in findings:
        refs = item.get("evidence_references") or []
        if not refs: errors.append(f"finding {item.get('finding_id')} has no evidence reference")
        for ref in refs:
            if ref not in registry: errors.append(f"finding {item.get('finding_id')} references unknown evidence {ref}")
        if item.get("scope") != "individual_asset": errors.append(f"finding {item.get('finding_id')} has invalid scope")
    for item in outcomes:
        if item.get("scope") != "campaign_set": errors.append(f"outcome {item.get('observation_id')} must be campaign_set")
        if item.get("individual_asset_attribution_allowed") is not False: errors.append("outcome permits individual attribution")
        if item.get("causal_interpretation_allowed") is not False: errors.append("outcome permits causal interpretation")
    if {item.get("finding_id") for item in assessments} != {item.get("finding_id") for item in findings}: errors.append("expert assessment must contain exactly one row per finding")
    boundary = evidence.get("claim_boundary") or {}
    for key in ("causal_interpretation_allowed", "numeric_uplift_prediction_generated", "individual_asset_outcome_attribution_allowed", "missing_values_inferred", "expert_assessment_fabricated"):
        if boundary.get(key) is not False: errors.append(f"claim boundary {key} must be false")
    return errors
