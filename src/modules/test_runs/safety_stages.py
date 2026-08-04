"""Brand-safety and brandbook-compliance pipeline stages."""

from __future__ import annotations

from src.modules.brand_profiles.service import get_profile as get_brand
from src.modules.creative_assets.service import get_asset_model
from src.shared.llm.base import LLMProvider

from .pipeline import (
    _asset_text,
    _call_llm_json,
    _is_stub,
    _parse_stage_result,
)
from .prompts import load_prompt
from .visual_context import (
    VisualEvidenceEnvelope,
    resolve_visual_evidence,
    stage_confidence,
)

def _scan_risky_claims(text: str) -> list[dict]:
    if not text:
        return []
    lower = text.lower()
    found = []
    risky_patterns = [
        ("overclaim_absolute", "high", ["only ", " ever need", "the best ", "number one ", "top-rated "],
         "Contains absolute or superlative claims that may exaggerate the product's uniqueness.",
         "Replace absolute claims with specific, verifiable benefits."),
        ("overclaim_guarantee", "high", ["guarantee", "guaranteed", "promise", "assure "],
         "Contains guaranteed outcome language that may overstate what the product delivers.",
         "Frame benefits as product features, not guaranteed outcomes."),
        ("overclaim_zero_risk", "high", ["zero risk", "no risk", "risk-free", "no hassle", "zero hassle"],
         "Contains zero-risk or no-hassle language that may be misleading.",
         "Acknowledge reasonable risks or limitations honestly."),
        ("overclaim_pressure", "medium", ["forget ", "ever again", "stop worrying", "never look back"],
         "Contains pressure language that may create unrealistic expectations.",
         "Use measured, reassuring language instead."),
        ("overclaim_income", "high", ["guaranteed income", "guaranteed return", "make money", "get rich"],
         "Contains income or financial outcome guarantees that violate typical claims policies.",
         "Remove financial guarantees; frame as features."),
        ("overclaim_absolute_pct", "medium", ["100%", "100 percent"],
         "Contains absolute percentage claims that may be hard to substantiate.",
         "Qualify percentage claims with specific conditions or sources."),
    ]
    for risk_type, level, patterns, description, mitigation in risky_patterns:
        for pattern in patterns:
            if pattern in lower:
                found.append({
                    "risk_type": risk_type,
                    "level": level,
                    "description": description,
                    "mitigation": mitigation,
                })
                break
    return found


def _detect_claim_violations(text: str) -> list[dict]:
    return _scan_risky_claims(text)


def _canonical_visual_risks(envelope: VisualEvidenceEnvelope) -> list[dict]:
    context = envelope.visual_context
    if context is None or not context.visual_risks:
        return []
    return [
        {
            "risk_type": risk.risk_type,
            "level": risk.level,
            "description": risk.description,
            "mitigation": risk.mitigation or "",
            "confidence": risk.confidence,
            "provenance": [item.model_dump(mode="json") for item in risk.provenance],
            "visual_evidence_fingerprint": envelope.fingerprint,
        }
        for risk in context.visual_risks
    ]


def brand_safety_review(
    asset_id: str,
    brand_profile_id: str | None,
    provider: LLMProvider,
    visual_evidence: VisualEvidenceEnvelope | dict | None = None,
) -> list[dict]:
    asset = get_asset_model(asset_id)
    envelope = resolve_visual_evidence(asset, visual_evidence)
    asset_text = _asset_text(asset)
    asset_title = asset.title if asset else ""
    asset_type = asset.asset_type if asset else "text"

    if _is_stub(provider):
        confidence = stage_confidence(envelope)
        risks = [
            {"risk_type": "brand_fit", "level": "low", "description": "Creative aligns well with brand identity.", "mitigation": "No action needed.", "confidence": confidence, "provenance": [], "visual_evidence_fingerprint": envelope.fingerprint},
            {"risk_type": "negativity_risk", "level": "low", "description": "Low risk of negative perception.", "mitigation": "Monitor comments.", "confidence": confidence, "provenance": [], "visual_evidence_fingerprint": envelope.fingerprint},
        ]
        for item in _detect_claim_violations(asset_text):
            item.update({"confidence": 1.0, "provenance": [], "visual_evidence_fingerprint": envelope.fingerprint})
            risks.append(item)
        risks.extend(_canonical_visual_risks(envelope))
        return risks

    if brand_profile_id is None:
        return []
    brand = get_brand(brand_profile_id)
    if brand is None:
        return []

    prompt = load_prompt(
        "brand_safety",
        title=asset_title,
        text_content=asset_text,
        asset_type=asset_type,
        brand_name=brand.name,
        tone_of_voice=brand.tone_of_voice or "",
        brand_target_audience=brand.target_audience or "",
        restrictions=brand.restrictions or "",
        claims_policy=brand.claims_policy or "",
        visual_context=envelope.prompt_json(),
    )
    raw = _call_llm_json(provider, prompt, stage_name="brand_safety_review")
    result = _parse_stage_result(raw, {
        "overall_risk_level": "low",
        "risks": [],
        "brand_fit_score": 7.0,
        "claims_compliance": "compliant",
    })
    risks = result.get("risks", [])
    for risk in risks:
        risk.setdefault("confidence", stage_confidence(envelope))
        risk.setdefault("provenance", [])
        risk.setdefault("visual_evidence_fingerprint", envelope.fingerprint)
    return risks


def _detect_tone_violations(text: str) -> list[dict]:
    if not text:
        return []
    lower = text.lower()
    violations = []
    aggressive_words = ["must", "have to", "you need", "urgent", "immediately", "act now", "don't miss"]
    casual_markers = ["gonna", "wanna", "hey", "yo", "sup", "cool", "awesome", "guys"]
    formal_markers = ["hereby", "henceforth", "hereinafter", "thereto", "whereas"]

    aggressive_count = sum(1 for word in aggressive_words if word in lower)
    casual_count = sum(1 for word in casual_markers if word in lower)
    formal_count = sum(1 for word in formal_markers if word in lower)

    if aggressive_count >= 2:
        violations.append({
            "rule": "tone_aggressive",
            "severity": "medium",
            "details": f"Contains {aggressive_count} aggressive/pressure words that may conflict with a friendly tone of voice.",
        })
    if casual_count >= 3:
        violations.append({
            "rule": "tone_too_casual",
            "severity": "low",
            "details": f"Contains {casual_count} casual language markers that may undercut brand authority.",
        })
    if formal_count >= 3:
        violations.append({
            "rule": "tone_too_formal",
            "severity": "low",
            "details": f"Contains {formal_count} formal/legalistic terms that may feel distant to the audience.",
        })
    return violations


_STUB_FORBIDDEN_CLAIMS = [
    "cure", "instant", "overnight", "miracle", "guaranteed results",
    "secret", "hidden", "exclusive access", "limited time",
    "act fast", "supplies running out",
]


def _detect_forbidden_claims(text: str) -> list[dict]:
    if not text:
        return []
    lower = text.lower()
    violations = []
    for claim in _STUB_FORBIDDEN_CLAIMS:
        if claim in lower:
            violations.append({
                "rule": f"forbidden_claim_{claim.replace(' ', '_')}",
                "severity": "high",
                "details": f"Contains forbidden claim: '{claim}'. This violates standard brandbook guidelines.",
            })
    return violations


def brandbook_compliance_review(
    asset_id: str,
    brand_profile_id: str | None,
    provider: LLMProvider,
    context_text: str = "",
    visual_evidence: VisualEvidenceEnvelope | dict | None = None,
) -> dict:
    asset = get_asset_model(asset_id)
    envelope = resolve_visual_evidence(asset, visual_evidence)
    asset_text = _asset_text(asset)
    asset_title = asset.title if asset else ""
    asset_type = asset.asset_type if asset else "text"

    if _is_stub(provider):
        violations = [*_detect_forbidden_claims(asset_text), *_detect_tone_violations(asset_text)]
        if not violations:
            compliance_score = 9.0
            overall_verdict = "compliant"
            recommendations = ["Creative aligns well with brandbook guidelines."]
        else:
            high_count = sum(1 for violation in violations if violation["severity"] == "high")
            medium_count = sum(1 for violation in violations if violation["severity"] == "medium")
            compliance_score = max(1.0, 9.0 - high_count * 3.0 - medium_count * 1.5)
            overall_verdict = "non_compliant" if high_count > 0 else "needs_revision"
            recommendations = [f"Fix {violation['rule']}: {violation['details']}" for violation in violations]

        if envelope.asset_requires_visual_evidence and envelope.status in {"missing", "limited"}:
            recommendations.append(
                "Complete a manual visual brandbook review; missing visual evidence is not treated as a violation."
            )
        return {
            "overall_verdict": overall_verdict,
            "violations": violations,
            "recommendations": recommendations[:5],
            "compliance_score": compliance_score,
            "confidence": stage_confidence(envelope),
            "visual_evidence_fingerprint": envelope.fingerprint,
        }

    if brand_profile_id is None:
        return {
            "overall_verdict": "compliant",
            "violations": [],
            "recommendations": [],
            "compliance_score": 10.0,
            "confidence": stage_confidence(envelope),
            "visual_evidence_fingerprint": envelope.fingerprint,
        }
    brand = get_brand(brand_profile_id)
    if brand is None:
        return {
            "overall_verdict": "compliant",
            "violations": [],
            "recommendations": [],
            "compliance_score": 10.0,
            "confidence": stage_confidence(envelope),
            "visual_evidence_fingerprint": envelope.fingerprint,
        }

    compliance_rules = (
        f"Tone of voice: {brand.tone_of_voice or 'Not specified'}\n"
        f"Restrictions: {brand.restrictions or 'None'}\n"
        f"Claims policy: {brand.claims_policy or 'None'}\n"
    )
    prompt = load_prompt(
        "brandbook_compliance",
        title=asset_title,
        text_content=asset_text,
        asset_type=asset_type,
        brand_context=context_text or f"Brand: {brand.name}",
        compliance_rules=compliance_rules,
        visual_context=envelope.prompt_json(),
    )
    raw = _call_llm_json(provider, prompt, stage_name="brandbook_compliance_review")
    result = _parse_stage_result(raw, {
        "overall_verdict": "compliant",
        "violations": [],
        "recommendations": [],
        "compliance_score": 7.0,
    })
    result.setdefault("confidence", stage_confidence(envelope))
    result.setdefault("visual_evidence_fingerprint", envelope.fingerprint)
    return result
