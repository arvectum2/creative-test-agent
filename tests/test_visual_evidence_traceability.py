import pytest

from src.modules.creative_assets.schemas import CreateCreativeAssetRequest
from src.modules.creative_assets.service import create_asset, get_asset_model
from src.modules.test_runs.pipeline import STUB_SCORECARD
from src.modules.test_runs.schemas import CreateTestRunRequest
from src.modules.test_runs.service import create_test_run, run_test_run
from src.modules.test_runs.traceability import apply_visual_traceability, run_traceable_pipeline
from src.modules.test_runs.visual_context import VisualEvidenceEnvelope, build_visual_evidence
from src.shared.llm.stub import StubProvider
from src.shared.vision.schemas import (
    CanonicalVisualContext,
    CognitiveLoadObservation,
    HierarchyObservation,
    MessageVisualBindingObservation,
    ReadabilityObservation,
    TextObservation,
    VisionResult,
    VisualElementObservation,
    VisualExtraction,
    VisualProvenance,
    VisualRiskObservation,
)


def _provenance(key: str):
    return [
        VisualProvenance(
            source_type="vlm",
            provider="local_vlm",
            model="trace-test-vlm",
            evidence_key=key,
        )
    ]


def _full_visual_result(*, cta_presence: str = "present") -> dict:
    context = CanonicalVisualContext(
        extraction=VisualExtraction(
            provider="local_vlm",
            confidence=0.92,
            provenance=_provenance("visual_analysis"),
            metadata={"model": "trace-test-vlm"},
        ),
        ocr_text=TextObservation(
            value="Try it today",
            confidence=0.95,
            provenance=_provenance("visual_analysis.ocr_text"),
        ),
        visual_summary=TextObservation(
            value="A centered product pack with a CTA below it.",
            confidence=0.91,
            provenance=_provenance("visual_analysis.visual_summary"),
        ),
        brand_logo_prominence=VisualElementObservation(
            presence="present",
            prominence="prominent",
            description="Logo in the upper-left corner",
            confidence=0.9,
            provenance=_provenance("visual_analysis.brand_logo_prominence"),
        ),
        packshot=VisualElementObservation(
            presence="present",
            prominence="dominant",
            description="Centered product pack",
            confidence=0.93,
            provenance=_provenance("visual_analysis.packshot"),
        ),
        cta=VisualElementObservation(
            presence=cta_presence,
            prominence="visible" if cta_presence == "present" else "not_visible",
            text="Try it today" if cta_presence == "present" else None,
            confidence=0.92,
            provenance=_provenance("visual_analysis.cta"),
        ),
        promo_badge=VisualElementObservation(
            presence="absent",
            prominence="not_visible",
            confidence=0.88,
            provenance=_provenance("visual_analysis.promo_badge"),
        ),
        hierarchy=HierarchyObservation(
            ordered_elements=["packshot", "benefit", "CTA"],
            confidence=0.9,
            provenance=_provenance("visual_analysis.hierarchy"),
        ),
        message_visual_binding=MessageVisualBindingObservation(
            level="strong",
            explanation="The product image supports the benefit copy.",
            confidence=0.87,
            provenance=_provenance("visual_analysis.message_visual_binding"),
        ),
        cognitive_load=CognitiveLoadObservation(
            level="low",
            drivers=["single focal point"],
            confidence=0.85,
            provenance=_provenance("visual_analysis.cognitive_load"),
        ),
        readability=ReadabilityObservation(
            level="good",
            issues=[],
            confidence=0.89,
            provenance=_provenance("visual_analysis.readability"),
        ),
        visual_risks=[
            VisualRiskObservation(
                risk_type="small_disclaimer",
                level="medium",
                description="The disclaimer is visually small.",
                mitigation="Increase disclaimer size.",
                confidence=0.82,
                provenance=_provenance("visual_analysis.visual_risks"),
            )
        ],
    )
    return VisionResult(visual_context=context).model_dump(mode="json")


def _asset_with_visual_result(result: dict, title: str = "Traceable visual"):
    return create_asset(CreateCreativeAssetRequest(
        title=title,
        asset_type="image",
        text_content="Try it today",
        metadata={"visual_analysis": result},
    ))


def _reference_by_path(envelope: VisualEvidenceEnvelope, path: str):
    return next(item for item in envelope.references if item.observation_path == path)


def test_observation_references_are_stable_integrity_checked_and_include_absence():
    asset = _asset_with_visual_result(_full_visual_result())
    model = get_asset_model(asset.id)

    first = build_visual_evidence(model)
    second = build_visual_evidence(model)

    assert first.schema_version == "1.1"
    assert first.fingerprint == second.fingerprint
    assert [item.reference_id for item in first.references] == [item.reference_id for item in second.references]
    assert len(first.references) == 11

    absent = _reference_by_path(first, "visual_context.promo_badge")
    assert absent.observation["presence"] == "absent"
    assert absent.provenance[0].evidence_key == "visual_analysis.promo_badge"

    tampered = first.model_dump(mode="json", exclude_none=False)
    tampered["references"][0]["observation"]["confidence"] = 0.01
    with pytest.raises(ValueError):
        VisualEvidenceEnvelope.model_validate(tampered)


def test_traceable_stub_pipeline_binds_visual_findings_to_registry():
    asset = _asset_with_visual_result(_full_visual_result())

    result = run_traceable_pipeline(
        creative_asset_id=asset.id,
        brand_profile_id=None,
        audience_profile_ids=[],
        rubric_id=None,
        provider=StubProvider(),
    )

    reference_ids = {item["reference_id"] for item in result["visual_evidence"]["references"]}
    cta_score = next(item for item in result["scorecard"] if item["criterion"] == "call_to_action")
    assert cta_score["visual_traceability_status"] == "supported"
    assert cta_score["visual_evidence_refs"]
    assert set(cta_score["visual_evidence_refs"]) <= reference_ids
    assert cta_score["score"] == next(
        item["score"] for item in STUB_SCORECARD if item["criterion"] == "call_to_action"
    )

    visual_risk = next(item for item in result["risks"] if item["risk_type"] == "small_disclaimer")
    assert visual_risk["visual_traceability_status"] == "supported"
    assert len(visual_risk["visual_evidence_refs"]) == 1
    assert visual_risk["visual_evidence_refs"][0] in reference_ids

    assert result["visual_traceability_status"] == "complete"
    assert result["unresolved_visual_finding_count"] == 0
    assert result["visual_evidence_trace"]["fingerprint"]
    assert set(result["visual_evidence_trace"]["accepted_reference_ids"]) <= reference_ids


def test_missing_observation_blocks_visual_conclusion_without_changing_score():
    partial = VisionResult(
        provider="local_vlm",
        detected_text="Try it today",
        metadata={"extraction_confidence": 0.8, "model": "partial-vlm"},
    ).model_dump(mode="json")
    asset = _asset_with_visual_result(partial, title="Partial visual")

    result = run_traceable_pipeline(
        creative_asset_id=asset.id,
        brand_profile_id=None,
        audience_profile_ids=[],
        rubric_id=None,
        provider=StubProvider(),
    )

    cta_score = next(item for item in result["scorecard"] if item["criterion"] == "call_to_action")
    original_score = next(item["score"] for item in STUB_SCORECARD if item["criterion"] == "call_to_action")
    assert cta_score["score"] == original_score
    assert cta_score["confidence"] == 0.0
    assert cta_score["visual_traceability_status"] == "unassessed"
    assert cta_score["visual_evidence_refs"] == []
    assert "not assessed" in cta_score["rationale"].lower()

    copy_score = next(item for item in result["scorecard"] if item["criterion"] == "message_clarity")
    assert copy_score["visual_traceability_status"] == "not_used"
    assert copy_score["confidence"] == 0.7
    assert result["visual_traceability_status"] == "needs_review"
    assert result["unresolved_visual_finding_count"] > 0


def test_explicit_assessed_absence_is_citable_but_not_converted_to_presence():
    asset = _asset_with_visual_result(_full_visual_result(cta_presence="absent"), title="CTA absent")

    result = run_traceable_pipeline(
        creative_asset_id=asset.id,
        brand_profile_id=None,
        audience_profile_ids=[],
        rubric_id=None,
        provider=StubProvider(),
    )

    reference_map = {
        item["reference_id"]: item
        for item in result["visual_evidence"]["references"]
    }
    cta_score = next(item for item in result["scorecard"] if item["criterion"] == "call_to_action")
    assert cta_score["visual_traceability_status"] == "supported"
    assert any(reference_map[item]["observation"].get("presence") == "absent" for item in cta_score["visual_evidence_refs"])
    assert "assessed absence" in cta_score["rationale"].lower()
    assert "cta is present" not in cta_score["rationale"].lower()


def test_unknown_and_criterion_unrelated_references_are_rejected_fail_closed():
    asset = _asset_with_visual_result(_full_visual_result())
    envelope = build_visual_evidence(get_asset_model(asset.id))
    logo_ref = _reference_by_path(envelope, "visual_context.brand_logo_prominence").reference_id
    original_score = 7.0
    raw_result = {
        "summary": "Copy-only summary",
        "summary_details": {
            "summary": "Copy-only summary",
            "key_message": "Try it today",
            "confidence": 0.9,
            "evidence_scope": "non_visual",
            "visual_evidence_refs": [],
        },
        "scorecard": [
            {
                "criterion": "call_to_action",
                "score": original_score,
                "rationale": "The CTA is visually prominent.",
                "recommendation": "Keep it.",
                "confidence": 0.9,
                "visual_evidence_refs": [logo_ref, "ve-does-not-exist"],
            },
            {
                "criterion": "message_clarity",
                "score": 8.0,
                "rationale": "The copy is clear.",
                "recommendation": "Keep it.",
                "confidence": 0.9,
            },
        ],
        "risks": [],
        "audience_reactions": [],
        "brandbook_compliance": {},
        "final_recommendation": "revise",
        "final_recommendation_details": {"final_recommendation": "revise", "confidence_score": 0.7},
        "overall_score": 7.5,
        "visual_context": envelope.visual_context.model_dump(mode="json", exclude_none=False),
        "visual_evidence": envelope.model_dump(mode="json", exclude_none=False),
    }

    result = apply_visual_traceability(raw_result, envelope, provider_is_stub=False)

    cta_score = result["scorecard"][0]
    assert cta_score["score"] == original_score
    assert cta_score["confidence"] == 0.0
    assert cta_score["visual_traceability_status"] == "unsupported"
    assert cta_score["visual_evidence_refs"] == []
    assert set(cta_score["rejected_visual_evidence_refs"]) == {logo_ref, "ve-does-not-exist"}
    assert "not accepted" in cta_score["rationale"].lower()

    copy_score = result["scorecard"][1]
    assert copy_score["visual_traceability_status"] == "not_used"
    assert copy_score["confidence"] == 0.9
    assert logo_ref in result["visual_evidence_trace"]["rejected_reference_ids"]
    assert "ve-does-not-exist" in result["visual_evidence_trace"]["rejected_reference_ids"]


def test_test_run_persists_reference_registry_bindings_and_trace_manifest():
    asset = _asset_with_visual_result(_full_visual_result(), title="Persisted trace")
    created = create_test_run(CreateTestRunRequest(creative_asset_id=asset.id))

    completed = run_test_run(created.id)

    assert completed.status == "completed"
    assert completed.visual_evidence is not None
    assert completed.visual_evidence["schema_version"] == "1.1"
    assert completed.visual_evidence["references"]
    assert completed.visual_evidence_trace is not None
    assert completed.visual_evidence_trace["fingerprint"]
    assert completed.visual_traceability_status == "complete"
    assert completed.unresolved_visual_finding_count == 0

    reference_ids = {item["reference_id"] for item in completed.visual_evidence["references"]}
    cta_score = next(item for item in completed.scorecard if item.criterion == "call_to_action")
    assert cta_score.visual_traceability_status == "supported"
    assert set(cta_score.visual_evidence_refs) <= reference_ids
    assert set(completed.final_recommendation_visual_evidence_refs) <= reference_ids
