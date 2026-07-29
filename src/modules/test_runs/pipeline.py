"""Structured creative pre-test pipeline with canonical visual evidence propagation.

Orchestrates 6 agent stages:
1. creative_summary
2. audience_simulation
3. brand_safety_review
4. brandbook_compliance_review
5. rubric_scoring
6. final_recommendation

A single :class:`VisualEvidenceEnvelope` is built once per pipeline run and passed
unchanged to every stage. Missing visual observations remain ``null`` and are never
interpreted as assessed absence.
"""

from __future__ import annotations

import json
from typing import Any

from src.modules.audience_profiles.service import get_profile as get_audience
from src.modules.brand_profiles.service import get_profile as get_brand
from src.modules.creative_assets.service import get_asset_model
from src.modules.test_rubrics.service import get_rubric
from src.shared.llm.base import LLMProvider

from .prompts import load_prompt
from .visual_context import (
    VisualEvidenceEnvelope,
    resolve_visual_evidence,
    stage_confidence,
)


STUB_SCORECARD = [
    {"criterion": "message_clarity", "score": 7.5, "rationale": "The core message is reasonably clear.", "recommendation": "Consider sharpening the headline."},
    {"criterion": "memorability", "score": 6.0, "rationale": "Moderate memorability; could use a stronger hook.", "recommendation": "Add a memorable visual or slogan."},
    {"criterion": "audience_fit", "score": 8.0, "rationale": "Good alignment with target audience.", "recommendation": "Maintain current targeting."},
    {"criterion": "call_to_action", "score": 7.0, "rationale": "CTA is present but could be more compelling.", "recommendation": "Make the CTA more urgent."},
    {"criterion": "trust", "score": 8.5, "rationale": "High trust signals.", "recommendation": "Keep trust elements."},
    {"criterion": "brand_fit", "score": 9.0, "rationale": "Strong brand alignment.", "recommendation": "No changes needed."},
    {"criterion": "negativity_risk", "score": 3.0, "rationale": "Low risk of negative perception.", "recommendation": "No changes needed."},
    {"criterion": "distinctiveness", "score": 6.5, "rationale": "Moderately distinct from competitors.", "recommendation": "Add a unique differentiator."},
]


_VISUAL_DEPENDENT_CRITERIA = {
    "memorability",
    "call_to_action",
    "brand_fit",
    "distinctiveness",
    "message_visual_binding",
    "visual_hierarchy",
    "cognitive_load",
    "readability",
}


def _is_stub(provider: LLMProvider) -> bool:
    return provider.__class__.__name__ == "StubProvider"


def _call_llm_json(provider: LLMProvider, prompt: str, stage_name: str = "") -> dict | None:
    result = provider.generate(prompt)
    content = result.get("content", "")
    try:
        return json.loads(content)
    except (json.JSONDecodeError, TypeError):
        pass

    if stage_name:
        import time

        from src.shared.llm.stage_processor import process_stage_output

        start = time.time()
        stage_result = process_stage_output(
            stage_name=stage_name,
            raw_response=content,
            prompt_text=prompt,
            provider=provider,
            latency_ms=(time.time() - start) * 1000,
        )
        if stage_result.success and stage_result.parsed_data is not None:
            return stage_result.parsed_data
    return None


def _parse_stage_result(raw: dict | None, default: dict) -> dict:
    return default if raw is None else raw


def _asset_text(asset) -> str:
    return (asset.text_content or asset.extracted_text or "") if asset else ""


def _visual_observation_value(envelope: VisualEvidenceEnvelope, field: str) -> Any:
    context = envelope.visual_context
    if context is None:
        return None
    return getattr(context, field, None)


def _visual_text_context(envelope: VisualEvidenceEnvelope) -> str:
    context = envelope.visual_context
    if context is None:
        return ""
    parts: list[str] = []
    if context.visual_summary is not None:
        parts.append(f"Visual description: {context.visual_summary.value}")
    if context.ocr_text is not None:
        parts.append(f"Text detected in image: {context.ocr_text.value}")
    if context.hierarchy is not None:
        hierarchy = context.hierarchy.ordered_elements or context.hierarchy.notes
        if hierarchy:
            parts.append("Visual hierarchy:\n" + "\n".join(f"- {item}" for item in hierarchy))
    return "\n".join(parts)


def _stage_evidence_metadata(envelope: VisualEvidenceEnvelope) -> dict[str, Any]:
    return {
        "confidence": stage_confidence(envelope),
        "visual_evidence_status": envelope.status,
        "visual_evidence_fingerprint": envelope.fingerprint,
    }


def creative_summary(
    asset_id: str,
    provider: LLMProvider,
    visual_evidence: VisualEvidenceEnvelope | dict | None = None,
) -> dict:
    asset = get_asset_model(asset_id)
    if asset is None:
        return {
            "summary": "Creative asset not found.",
            "key_message": "",
            "tone": "",
            "target_audience_vibe": "",
            "confidence": 0.0,
            "visual_evidence_status": "missing",
            "visual_evidence_fingerprint": "",
        }

    envelope = resolve_visual_evidence(asset, visual_evidence)
    text = _asset_text(asset)
    visual_desc = _visual_text_context(envelope)
    combined_text = text
    if visual_desc:
        combined_text = f"{text}\n\n{visual_desc}" if text else visual_desc

    evidence_meta = _stage_evidence_metadata(envelope)
    if _is_stub(provider):
        summary = f"A {asset.asset_type} creative titled '{asset.title}' that communicates a promotional message."
        observation = _visual_observation_value(envelope, "visual_summary")
        if observation is not None:
            summary += f" {observation.value}"
        if envelope.asset_requires_visual_evidence and envelope.status in {"missing", "limited"}:
            summary += " Visual conclusions are limited by incomplete extraction evidence."
        return {
            "summary": summary,
            "key_message": combined_text,
            "tone": "persuasive",
            "target_audience_vibe": "general consumers",
            **evidence_meta,
        }

    prompt = load_prompt(
        "creative_summary",
        title=asset.title,
        asset_type=asset.asset_type,
        text_content=combined_text,
        visual_context=envelope.prompt_json(),
    )
    raw = _call_llm_json(provider, prompt, stage_name="creative_summary")
    result = _parse_stage_result(raw, {
        "summary": f"Creative titled '{asset.title}'.",
        "key_message": combined_text,
        "tone": "neutral",
        "target_audience_vibe": "general",
    })
    result.update({key: result.get(key, value) for key, value in evidence_meta.items()})
    return result


def audience_simulation(
    asset_id: str,
    audience_ids: list[str],
    provider: LLMProvider,
    visual_evidence: VisualEvidenceEnvelope | dict | None = None,
) -> list[dict]:
    asset = get_asset_model(asset_id)
    envelope = resolve_visual_evidence(asset, visual_evidence)
    asset_text = _asset_text(asset)
    asset_title = asset.title if asset else ""
    asset_type = asset.asset_type if asset else "text"
    evidence_meta = _stage_evidence_metadata(envelope)

    if not audience_ids:
        if _is_stub(provider):
            objections = ["Needs more social proof"]
            if envelope.asset_requires_visual_evidence and envelope.status in {"missing", "limited"}:
                objections.append("Visual response is uncertain because extraction evidence is incomplete")
            return [{
                "audience_profile_id": "default",
                "segment_name": "General Audience",
                "reaction": "The creative would likely be well-received, subject to the supplied evidence limitations.",
                "positive_triggers": ["Clear messaging", "Relevant offer"],
                "objections": objections,
                "engagement_probability": 7.0,
                **evidence_meta,
            }]
        return []

    reactions = []
    for audience_id in audience_ids:
        profile = get_audience(audience_id)
        if profile is None:
            continue

        if _is_stub(provider):
            objections: list[str] = []
            if envelope.asset_requires_visual_evidence and envelope.status in {"missing", "limited"}:
                objections.append("Visual response cannot be assessed with high confidence")
            reactions.append({
                "audience_profile_id": audience_id,
                "segment_name": profile.name,
                "reaction": "This segment would respond positively to the creative, with uncertainty bounded by the visual evidence quality.",
                "positive_triggers": ["Relevant messaging"],
                "objections": objections,
                "engagement_probability": 7.0,
                **evidence_meta,
            })
            continue

        prompt = load_prompt(
            "audience_simulation",
            title=asset_title,
            text_content=asset_text,
            asset_type=asset_type,
            segment_name=profile.name,
            segment_description=profile.segment_description,
            pains=profile.pains or "",
            motivations=profile.motivations or "",
            objections=profile.objections or "",
            visual_context=envelope.prompt_json(),
        )
        raw = _call_llm_json(provider, prompt, stage_name="audience_simulation")
        result = _parse_stage_result(raw, {
            "reaction": "Neutral reaction expected.",
            "positive_triggers": [],
            "objections": [],
            "engagement_probability": 5.0,
        })
        result["audience_profile_id"] = audience_id
        result["segment_name"] = profile.name
        result.update({key: result.get(key, value) for key, value in evidence_meta.items()})
        reactions.append(result)

    return reactions


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


def _scorecard_with_evidence(
    scorecard: list[dict],
    envelope: VisualEvidenceEnvelope,
) -> list[dict]:
    enriched: list[dict] = []
    for raw in scorecard:
        item = dict(raw)
        criterion = str(item.get("criterion") or "")
        confidence = 1.0
        if envelope.asset_requires_visual_evidence and criterion in _VISUAL_DEPENDENT_CRITERIA:
            confidence = envelope.evidence_confidence
        elif envelope.asset_requires_visual_evidence:
            confidence = max(envelope.evidence_confidence, 0.7)
        item.setdefault("confidence", round(confidence, 4))
        item.setdefault("evidence_notes", list(envelope.limitations) if confidence < 0.65 else [])
        item.setdefault("visual_evidence_fingerprint", envelope.fingerprint)
        enriched.append(item)
    return enriched


def rubric_scoring(
    asset_id: str,
    rubric_id: str | None,
    provider: LLMProvider,
    visual_evidence: VisualEvidenceEnvelope | dict | None = None,
) -> tuple[list[dict], float]:
    asset = get_asset_model(asset_id)
    envelope = resolve_visual_evidence(asset, visual_evidence)
    asset_text = _asset_text(asset)
    asset_title = asset.title if asset else ""
    asset_type = asset.asset_type if asset else "text"

    if _is_stub(provider):
        scores = _scorecard_with_evidence(STUB_SCORECARD, envelope)
        average = sum(item["score"] for item in scores) / len(scores)
        return scores, average

    rubric = get_rubric(rubric_id) if rubric_id else None
    if rubric is None:
        scores = _scorecard_with_evidence(STUB_SCORECARD, envelope)
        average = sum(item["score"] for item in scores) / len(scores)
        return scores, average

    criteria_lines = "\n".join(f"- {criterion.name}: {criterion.description}" for criterion in rubric.criteria)
    prompt = load_prompt(
        "rubric_scoring",
        title=asset_title,
        text_content=asset_text,
        asset_type=asset_type,
        rubric_name=rubric.name,
        scale_min=str(rubric.scale_min),
        scale_max=str(rubric.scale_max),
        criteria_list=criteria_lines,
        visual_context=envelope.prompt_json(),
    )
    raw = _call_llm_json(provider, prompt, stage_name="rubric_scoring")
    result = _parse_stage_result(raw, {"scorecard": [], "overall_score": 5.0})
    scores = result.get("scorecard", [])
    average = result.get("overall_score", 5.0)
    if not scores:
        scores = STUB_SCORECARD
        average = sum(item["score"] for item in scores) / len(scores)
    return _scorecard_with_evidence(scores, envelope), average


def _confidence_label(value: float) -> str:
    if value >= 0.75:
        return "high"
    if value >= 0.45:
        return "medium"
    return "low"


def _numeric_confidence(value: Any, default: float) -> float:
    if isinstance(value, str):
        return {"high": 0.85, "medium": 0.6, "low": 0.3}.get(value.lower(), default)
    try:
        return min(max(float(value), 0.0), 1.0)
    except (TypeError, ValueError):
        return default


def _final_recommendation_result(
    asset_id: str,
    summary: dict,
    scorecard: list[dict],
    risks: list[dict],
    audience_reactions: list[dict],
    provider: LLMProvider,
    brandbook_compliance: dict | None = None,
    visual_evidence: VisualEvidenceEnvelope | dict | None = None,
) -> dict:
    asset = get_asset_model(asset_id)
    envelope = resolve_visual_evidence(asset, visual_evidence)
    asset_title = asset.title if asset else ""

    score_confidences = [_numeric_confidence(item.get("confidence"), 1.0) for item in scorecard]
    audience_confidences = [_numeric_confidence(item.get("confidence"), 1.0) for item in audience_reactions]
    components = [*score_confidences, *audience_confidences]
    if envelope.asset_requires_visual_evidence:
        components.append(envelope.evidence_confidence)
    diagnostic_confidence = min(components) if components else stage_confidence(envelope)

    if _is_stub(provider):
        average = sum(item["score"] for item in scorecard) / max(len(scorecard), 1)
        if average >= 7.5:
            recommendation = "show_to_client"
        elif average >= 5.0:
            recommendation = "revise"
        else:
            recommendation = "reject"
        rationale = "Decision uses diagnostic scores without treating them as predicted market lift."
        if envelope.asset_requires_visual_evidence and envelope.status in {"missing", "limited"}:
            rationale += " Visual conclusions require review because extraction evidence is incomplete."
        return {
            "final_recommendation": recommendation,
            "rationale": rationale,
            "top_actions": list(envelope.limitations[:3]),
            "confidence": _confidence_label(diagnostic_confidence),
            "confidence_score": round(diagnostic_confidence, 4),
            "visual_evidence_fingerprint": envelope.fingerprint,
        }

    prompt = load_prompt(
        "final_recommendation",
        title=asset_title,
        summary=json.dumps(summary, ensure_ascii=False),
        scorecard=json.dumps(scorecard, ensure_ascii=False),
        risks=json.dumps(risks, ensure_ascii=False),
        audience_reactions=json.dumps(audience_reactions, ensure_ascii=False),
        brandbook_compliance=json.dumps(brandbook_compliance or {}, ensure_ascii=False),
        visual_context=envelope.prompt_json(),
    )
    raw = _call_llm_json(provider, prompt, stage_name="final_recommendation")
    result = _parse_stage_result(raw, {"final_recommendation": "revise"})
    recommendation = result.get("final_recommendation", "revise")
    if recommendation not in {"show_to_client", "revise", "reject"}:
        recommendation = "revise"
    model_confidence = _numeric_confidence(result.get("confidence"), diagnostic_confidence)
    confidence_score = min(model_confidence, diagnostic_confidence)
    return {
        "final_recommendation": recommendation,
        "rationale": str(result.get("rationale") or ""),
        "top_actions": list(result.get("top_actions") or []),
        "confidence": _confidence_label(confidence_score),
        "confidence_score": round(confidence_score, 4),
        "visual_evidence_fingerprint": envelope.fingerprint,
    }


def final_recommendation(
    asset_id: str,
    summary: dict,
    scorecard: list[dict],
    risks: list[dict],
    audience_reactions: list[dict],
    provider: LLMProvider,
    brandbook_compliance: dict | None = None,
    visual_evidence: VisualEvidenceEnvelope | dict | None = None,
) -> str:
    """Backward-compatible public wrapper returning only the decision string."""

    return _final_recommendation_result(
        asset_id=asset_id,
        summary=summary,
        scorecard=scorecard,
        risks=risks,
        audience_reactions=audience_reactions,
        provider=provider,
        brandbook_compliance=brandbook_compliance,
        visual_evidence=visual_evidence,
    )["final_recommendation"]


def _build_brandbook_context(brand_profile_id: str | None) -> str:
    if brand_profile_id is None:
        return ""
    try:
        from src.modules.brandbooks.service import get_brandbook_context

        context = get_brandbook_context(brand_profile_id=brand_profile_id)
        if context.snippets:
            return "\n\n".join(context.snippets[:3])
    except Exception:
        pass
    return ""


def run_pipeline(
    creative_asset_id: str,
    brand_profile_id: str | None,
    audience_profile_ids: list[str],
    rubric_id: str | None,
    provider: LLMProvider,
) -> dict:
    asset = get_asset_model(creative_asset_id)
    visual_evidence = resolve_visual_evidence(asset)

    summary = creative_summary(creative_asset_id, provider, visual_evidence=visual_evidence)
    audience = audience_simulation(
        creative_asset_id,
        audience_profile_ids,
        provider,
        visual_evidence=visual_evidence,
    )
    risks = brand_safety_review(
        creative_asset_id,
        brand_profile_id,
        provider,
        visual_evidence=visual_evidence,
    )

    brandbook_context = _build_brandbook_context(brand_profile_id)
    compliance = brandbook_compliance_review(
        creative_asset_id,
        brand_profile_id,
        provider,
        context_text=brandbook_context,
        visual_evidence=visual_evidence,
    )

    scorecard, overall = rubric_scoring(
        creative_asset_id,
        rubric_id,
        provider,
        visual_evidence=visual_evidence,
    )
    recommendation_details = _final_recommendation_result(
        creative_asset_id,
        summary,
        scorecard,
        risks,
        audience,
        provider,
        brandbook_compliance=compliance,
        visual_evidence=visual_evidence,
    )

    findings = [
        {
            "criterion": item["criterion"],
            "score": item["score"],
            "explanation": item.get("rationale", ""),
            "confidence": item.get("confidence", 1.0),
            "evidence_notes": item.get("evidence_notes", []),
        }
        for item in scorecard
    ]

    visual_context_payload = (
        visual_evidence.visual_context.model_dump(mode="json", exclude_none=False)
        if visual_evidence.visual_context is not None
        else None
    )
    return {
        "summary": summary.get("summary", ""),
        "scorecard": scorecard,
        "risks": risks,
        "audience_reactions": audience,
        "final_recommendation": recommendation_details["final_recommendation"],
        "final_recommendation_details": recommendation_details,
        "findings": findings,
        "overall_score": overall,
        "brandbook_compliance": compliance,
        "visual_context": visual_context_payload,
        "visual_evidence": visual_evidence.model_dump(mode="json", exclude_none=False),
        "visual_evidence_confidence": visual_evidence.evidence_confidence,
    }
