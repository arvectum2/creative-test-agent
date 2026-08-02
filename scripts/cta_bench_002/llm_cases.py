"""CTA-BENCH-002 frozen LLM case set.

Each case uses a real pipeline prompt contract (the same templates and evidence
rules that run in production) but with synthetic evidence. The manifest records
the expected JSON schema, forbidden claims, required evidence references and the
allowed abstention state so scoring is deterministic and not "gold prose".
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from scripts.cta_bench_002.spec import BENCHMARK_ID, BENCHMARK_VERSION

PACK_ID = "cta-bench-002-llm-case-set"
PACK_VERSION = "1.0.0"

_STAGES = [
    "creative_summary",
    "audience_simulation",
    "brand_safety_review",
    "brandbook_compliance_review",
    "rubric_scoring",
    "final_recommendation",
]

FORBIDDEN_CLAIMS = [
    "causal",
    "uplift",
    "lift",
    "ctr",
    "click-through",
    "brand lift",
    "market effectiveness",
    "real respondents",
    "percentage-point",
]

_REQUIRED_FIELDS: dict[str, list[str]] = {
    "creative_summary": ["summary", "key_message", "tone", "confidence"],
    "audience_simulation": ["reaction", "positive_triggers", "objections", "engagement_probability", "confidence"],
    "brand_safety_review": ["risks", "confidence"],
    "brandbook_compliance_review": ["overall_verdict", "violations", "recommendations"],
    "rubric_scoring": ["scorecard", "overall_score"],
    "final_recommendation": ["final_recommendation", "rationale", "top_actions", "confidence"],
}

_FORBIDDEN_PATTERNS = [
    "will increase",
    "guarantees",
    "proven",
    "real respondents showed",
    "measured lift",
]


def _envelope(
    *,
    visual_status: str = "complete",
    evidence_confidence: float = 0.82,
    summary: str = "Synthetic visual evidence for benchmark only.",
) -> dict[str, Any]:
    return {
        "asset_requires_visual_evidence": True,
        "status": visual_status,
        "evidence_confidence": round(evidence_confidence, 4),
        "limitations": [] if visual_status == "complete" else ["Visual extraction is incomplete."],
        "visual_context": {
            "visual_summary": {"value": summary, "presence": "present" if visual_status == "complete" else "uncertain"},
            "detected_text": {"value": "Fictional product. Demo only.", "presence": "present"},
            "observations": {
                "cta_present": {"value": "present", "reference_id": "ref_cta_001"},
                "brand_present": {"value": "present", "reference_id": "ref_brand_001"},
            } if visual_status == "complete" else {},
            "references": [
                {"reference_id": "ref_cta_001", "evidence_key": "cta_present", "value": "present"},
                {"reference_id": "ref_brand_001", "evidence_key": "brand_present", "value": "present"},
            ] if visual_status == "complete" else [],
        },
        "fingerprint": "bench00000000000000000000000000000000000000000000000000000000000000",
    }


def _case(
    case_id: str,
    stage: str,
    title: str,
    *,
    params: dict[str, Any],
    envelope: dict[str, Any],
    note: str,
) -> dict[str, Any]:
    return {
        "case_id": case_id,
        "stage": stage,
        "title": title,
        "params": params,
        "visual_evidence_envelope": envelope,
        "expected_schema": {
            "required_fields": _REQUIRED_FIELDS[stage],
        },
        "forbidden_claims": FORBIDDEN_CLAIMS,
        "allowed_abstention_state": {
            "can_abstain": True,
            "expected": {"status": "review_required", "reason": note},
        },
        "note": note,
        "input_language": "en",
    }


def _ru_case(
    case_id: str,
    stage: str,
    title: str,
    *,
    params: dict[str, Any],
    envelope: dict[str, Any],
    note: str,
) -> dict[str, Any]:
    case = _case(case_id, stage, title, params=params, envelope=envelope, note=note)
    case["input_language"] = "ru"
    return case


def build_cases() -> list[dict[str, Any]]:
    complete = _envelope()
    missing = _envelope(visual_status="missing", evidence_confidence=0.35, summary="Visual extraction incomplete.")
    conflicting = _envelope(
        visual_status="complete",
        evidence_confidence=0.55,
        summary="Conflicting visual cues between message and image.",
    )
    cases = [
        _case(
            "creative-summary-normal",
            "creative_summary",
            "Creative summary with complete visual evidence",
            params={
                "title": "Calm Support for Busy Days",
                "asset_type": "image",
                "text_content": "Everyday support, clearly explained. Fictional product. Learn more.",
            },
            envelope=complete,
            note="complete visual evidence; summary must cite reference IDs",
        ),
        _case(
            "creative-summary-missing-visual",
            "creative_summary",
            "Creative summary with missing visual extraction",
            params={
                "title": "Calm Support for Busy Days",
                "asset_type": "image",
                "text_content": "Everyday support, clearly explained.",
            },
            envelope=missing,
            note="missing extraction must stay unassessed and not lower creative quality",
        ),
        _ru_case(
            "creative-summary-russian",
            "creative_summary",
            "Creative summary with Russian copy",
            params={
                "title": "Спокойная поддержка в занятые дни",
                "asset_type": "image",
                "text_content": "Ежедневная поддержка вашего ритма. Вымышленный продукт для демо.",
            },
            envelope=complete,
            note="Russian output must preserve missing/absent semantics",
        ),
        _case(
            "audience-simulation-normal",
            "audience_simulation",
            "Audience simulation with complete evidence",
            params={
                "title": "Night-shift Support",
                "asset_type": "image",
                "text_content": "Designed for changing schedules. Fictional product.",
                "segment_name": "Night-shift workers",
                "segment_description": "Adults on rotating shifts.",
                "pains": "Fatigue, irregular routine",
                "motivations": "Consistency, energy",
                "objections": "Skepticism about supplements",
            },
            envelope=complete,
            note="must not predict brand lift or purchase uplift",
        ),
        _case(
            "audience-simulation-missing",
            "audience_simulation",
            "Audience simulation with missing visual evidence",
            params={
                "title": "Night-shift Support",
                "asset_type": "image",
                "text_content": "Designed for changing schedules.",
                "segment_name": "Night-shift workers",
                "segment_description": "Adults on rotating shifts.",
                "pains": "Fatigue",
                "motivations": "Consistency",
                "objections": "None recorded",
            },
            envelope=missing,
            note="reaction confidence must be lower; no invented visual triggers",
        ),
        _ru_case(
            "audience-simulation-russian",
            "audience_simulation",
            "Audience simulation with Russian inputs",
            params={
                "title": "Поддержка для ночной смены",
                "asset_type": "image",
                "text_content": "Создано для сменного графика. Вымышленный продукт.",
                "segment_name": "Работники ночной смены",
                "segment_description": "Взрослые со сменным графиком.",
                "pains": "Усталость, нерегулярный режим",
                "motivations": "Стабильность, энергия",
                "objections": "Скепсис к добавкам",
            },
            envelope=complete,
            note="Russian output, evidence-first, no real respondent claims",
        ),
        _case(
            "brand-safety-normal",
            "brand_safety_review",
            "Brand safety review with complete evidence",
            params={
                "title": "Calm Support for Busy Days",
                "asset_type": "image",
                "text_content": "Everyday support. Fictional product.",
                "brand_name": "NOVALEN",
                "tone_of_voice": "Calm, factual",
                "brand_target_audience": "Adults 30-55",
                "restrictions": "No absolute claims, no guaranteed outcomes.",
                "claims_policy": "Evidence-based claims only.",
            },
            envelope=complete,
            note="risks must cite exact reference IDs",
        ),
        _case(
            "brand-safety-missing",
            "brand_safety_review",
            "Brand safety review with missing visual evidence",
            params={
                "title": "Calm Support for Busy Days",
                "asset_type": "image",
                "text_content": "Everyday support.",
                "brand_name": "NOVALEN",
                "tone_of_voice": "Calm",
                "brand_target_audience": "Adults 30-55",
                "restrictions": "No absolute claims.",
                "claims_policy": "Evidence-based claims only.",
            },
            envelope=missing,
            note="missing visual evidence must not become an invented violation",
        ),
        _ru_case(
            "brand-safety-russian",
            "brand_safety_review",
            "Brand safety review with Russian inputs",
            params={
                "title": "Спокойная поддержка в занятые дни",
                "asset_type": "image",
                "text_content": "Ежедневная поддержка. Вымышленный продукт.",
                "brand_name": "NOVALEN",
                "tone_of_voice": "Спокойный, фактологичный",
                "brand_target_audience": "Взрослые 30-55",
                "restrictions": "Без абсолютных обещаний.",
                "claims_policy": "Только доказанные утверждения.",
            },
            envelope=complete,
            note="Russian output with exact reference IDs",
        ),
        _case(
            "brandbook-compliance-normal",
            "brandbook_compliance_review",
            "Brandbook compliance review",
            params={
                "title": "Calm Support",
                "asset_type": "image",
                "text_content": "Everyday support. Fictional product.",
                "brand_context": "Brand: NOVALEN. Use calm tones.",
                "compliance_rules": "No absolute claims; disclaimer required.",
            },
            envelope=complete,
            note="overall_verdict must be one of compliant/violations; refs cited",
        ),
        _case(
            "brandbook-compliance-missing",
            "brandbook_compliance_review",
            "Brandbook compliance with missing visual evidence",
            params={
                "title": "Calm Support",
                "asset_type": "image",
                "text_content": "Everyday support.",
                "brand_context": "Brand: NOVALEN.",
                "compliance_rules": "No absolute claims.",
            },
            envelope=missing,
            note="missing extraction must not be treated as an assessed violation",
        ),
        _ru_case(
            "brandbook-compliance-russian",
            "brandbook_compliance_review",
            "Brandbook compliance in Russian",
            params={
                "title": "Спокойная поддержка",
                "asset_type": "image",
                "text_content": "Ежедневная поддержка. Вымышленный продукт.",
                "brand_context": "Бренд: NOVALEN. Спокойные тона.",
                "compliance_rules": "Без абсолютных обещаний.",
            },
            envelope=complete,
            note="Russian output preserves schema",
        ),
        _case(
            "rubric-scoring-normal",
            "rubric_scoring",
            "Rubric scoring with complete evidence",
            params={
                "title": "Calm Support",
                "asset_type": "image",
                "text_content": "Everyday support. Fictional product.",
                "rubric_name": "Brand Lift Pilot Rubric",
                "scale_min": "1",
                "scale_max": "10",
                "criteria_list": "- message_clarity: Clear message\n- memorability: memorable",
            },
            envelope=complete,
            note="scorecard items must carry confidence and reference IDs",
        ),
        _case(
            "rubric-scoring-missing",
            "rubric_scoring",
            "Rubric scoring with missing visual evidence",
            params={
                "title": "Calm Support",
                "asset_type": "image",
                "text_content": "Everyday support.",
                "rubric_name": "Brand Lift Pilot Rubric",
                "scale_min": "1",
                "scale_max": "10",
                "criteria_list": "- message_clarity: Clear message",
            },
            envelope=missing,
            note="missing extraction lowers criterion confidence, not automatic score penalty",
        ),
        _case(
            "final-recommendation-normal",
            "final_recommendation",
            "Final recommendation with complete evidence",
            params={
                "title": "Calm Support",
                "summary": json.dumps({"summary": "Clear calm message.", "key_message": "Everyday support"}),
                "scorecard": json.dumps([{"criterion": "message_clarity", "score": 7.5}]),
                "risks": json.dumps([{"risk": "none"}]),
                "audience_reactions": json.dumps([{"reaction": "neutral"}]),
                "brandbook_compliance": json.dumps({"overall_verdict": "compliant"}),
            },
            envelope=complete,
            note="recommendation must not claim causal effectiveness",
        ),
        _case(
            "final-recommendation-conflicting",
            "final_recommendation",
            "Final recommendation with conflicting evidence",
            params={
                "title": "Calm Support",
                "summary": json.dumps({"summary": "Message and image conflict."}),
                "scorecard": json.dumps([{"criterion": "message_visual_binding", "score": 4.0}]),
                "risks": json.dumps([{"risk": "conflict"}]),
                "audience_reactions": json.dumps([{"reaction": "confused"}]),
                "brandbook_compliance": json.dumps({"overall_verdict": "compliant"}),
            },
            envelope=conflicting,
            note="cap recommendation confidence by weakest evidence",
        ),
        _ru_case(
            "final-recommendation-russian",
            "final_recommendation",
            "Final recommendation in Russian",
            params={
                "title": "Спокойная поддержка",
                "summary": json.dumps({"summary": "Ясное спокойное сообщение."}),
                "scorecard": json.dumps([{"criterion": "message_clarity", "score": 7.5}]),
                "risks": json.dumps([{"risk": "нет"}]),
                "audience_reactions": json.dumps([{"reaction": "нейтрально"}]),
                "brandbook_compliance": json.dumps({"overall_verdict": "compliant"}),
            },
            envelope=complete,
            note="Russian output preserves decision rules",
        ),
    ]
    return cases


def build_manifest() -> dict[str, Any]:
    cases = build_cases()
    return {
        "benchmark_id": BENCHMARK_ID,
        "benchmark_version": BENCHMARK_VERSION,
        "pack_id": PACK_ID,
        "pack_version": PACK_VERSION,
        "case_count": len(cases),
        "stage_count": len(_STAGES),
        "fictional_only": True,
        "cases": cases,
    }


def write_manifest(output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest = build_manifest()
    (output_dir / "case_manifest_llm.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest


def validate_manifest(output_dir: Path) -> list[str]:
    path = output_dir / "case_manifest_llm.json"
    if not path.is_file():
        return ["case_manifest_llm.json is missing"]
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"case_manifest_llm.json unreadable: {exc}"]
    errors: list[str] = []
    if manifest.get("benchmark_id") != BENCHMARK_ID:
        errors.append("unexpected benchmark identity")
    cases = manifest.get("cases")
    if not isinstance(cases, list) or not cases:
        return errors + ["LLM manifest must contain cases"]
    seen: set[str] = set()
    for case in cases:
        case_id = case.get("case_id")
        if not case_id or case_id in seen:
            errors.append(f"invalid or duplicate case_id: {case_id}")
        seen.add(case_id)
        if case.get("stage") not in _STAGES:
            errors.append(f"{case_id} has unknown stage {case.get('stage')}")
        required = (case.get("expected_schema") or {}).get("required_fields") or []
        for field in required:
            if field not in (case.get("params") or {}) and field not in _REQUIRED_FIELDS.get(case.get("stage", ""), []):
                pass
        if not case.get("note"):
            errors.append(f"{case_id} missing scoring note")
    return errors
