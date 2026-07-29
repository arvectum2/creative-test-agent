import pytest

from src.modules.creative_assets.schemas import CreateCreativeAssetRequest
from src.modules.creative_assets.service import create_asset
from src.modules.test_runs.confidence_policy import (
    apply_visual_confidence_policy,
    run_confidence_aware_pipeline,
    validate_visual_confidence_policy_manifest,
)
from src.modules.test_runs.pipeline import STUB_SCORECARD
from src.modules.test_runs.schemas import CreateTestRunRequest
from src.modules.test_runs.service import create_test_run, run_test_run
from src.modules.test_runs.traceability import run_traceable_pipeline
from src.modules.test_runs.visual_context import VisualEvidenceEnvelope
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
            model="confidence-test-vlm",
            evidence_key=key,
        )
    ]


def _visual_result(*, extraction_confidence: float = 0.92, cta_presence: str = "present") -> dict:
    context = CanonicalVisualContext(
        extraction=VisualExtraction(
            provider="local_vlm",
            confidence=extraction_confidence,
            provenance=_provenance("visual_analysis"),
            metadata={"model": "confidence-test-vlm"},
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


def _asset(result: dict, title: str = "Confidence policy visual"):
    return create_asset(CreateCreativeAssetRequest(
        title=title,
        asset_type="image",
        text_content="Try it today",
        metadata={"visual_analysis": result},
    ))


def _score(result: dict, criterion: str) -> dict:
    return next(item for item in result["scorecard"] if item["criterion"] == criterion)


def test_complete_visual_evidence_is_released_with_reproducible_policy_manifest():
    asset = _asset(_visual_result())

    first = run_confidence_aware_pipeline(asset.id, None, [], None, StubProvider())
    second = run_confidence_aware_pipeline(asset.id, None, [], None, StubProvider())

    assert first["visual_decision_status"] == "released"
    assert first["effective_recommendation"] == first["final_recommendation"]
    assert first["visual_abstention_count"] == 0
    assert _score(first, "call_to_action")["visual_abstention_status"] == "accepted"
    assert _score(first, "message_clarity")["visual_abstention_status"] == "not_applicable"
    assert first["visual_confidence_policy"]["fingerprint"] == second["visual_confidence_policy"]["fingerprint"]
    validate_visual_confidence_policy_manifest(first["visual_confidence_policy"])


def test_limited_visual_evidence_requires_manual_review_without_score_penalty():
    asset = _asset(_visual_result(extraction_confidence=0.6), title="Limited confidence visual")

    result = run_confidence_aware_pipeline(asset.id, None, [], None, StubProvider())

    cta = _score(result, "call_to_action")
    original_score = next(item["score"] for item in STUB_SCORECARD if item["criterion"] == "call_to_action")
    assert cta["score"] == original_score
    assert cta["visual_abstention_status"] == "review_required"
    assert result["visual_decision_status"] == "manual_review_required"
    assert result["effective_recommendation"] == "manual_review"
    assert result["final_recommendation"] in {"show_to_client", "revise", "reject"}


def test_missing_visual_evidence_hard_abstains_without_score_penalty():
    partial = VisionResult(
        provider="local_vlm",
        detected_text="Try it today",
        metadata={"extraction_confidence": 0.8, "model": "partial-vlm"},
    ).model_dump(mode="json")
    asset = _asset(partial, title="Missing observations")

    result = run_confidence_aware_pipeline(asset.id, None, [], None, StubProvider())

    cta = _score(result, "call_to_action")
    original_score = next(item["score"] for item in STUB_SCORECARD if item["criterion"] == "call_to_action")
    assert cta["score"] == original_score
    assert cta["visual_abstention_status"] == "abstained"
    assert cta["visual_assessment_allowed"] is False
    assert result["visual_decision_status"] == "abstained"
    assert result["effective_recommendation"] == "abstain"


def test_supported_finding_below_hard_floor_abstains_and_preserves_score():
    asset = _asset(_visual_result(), title="Low finding confidence")
    traced = run_traceable_pipeline(asset.id, None, [], None, StubProvider())
    envelope = VisualEvidenceEnvelope.model_validate(traced["visual_evidence"])
    cta = _score(traced, "call_to_action")
    original_score = cta["score"]
    cta["confidence"] = 0.3

    result = apply_visual_confidence_policy(traced, envelope)

    governed_cta = _score(result, "call_to_action")
    assert governed_cta["score"] == original_score
    assert governed_cta["visual_abstention_status"] == "abstained"
    assert "finding_confidence_below_hard_floor" in governed_cta["visual_abstention_reasons"]
    assert result["effective_recommendation"] == "abstain"


def test_assessed_absence_remains_citable_and_can_be_accepted():
    asset = _asset(_visual_result(cta_presence="absent"), title="Assessed CTA absence")

    result = run_confidence_aware_pipeline(asset.id, None, [], None, StubProvider())

    reference_map = {
        item["reference_id"]: item
        for item in result["visual_evidence"]["references"]
    }
    cta = _score(result, "call_to_action")
    assert cta["visual_abstention_status"] == "accepted"
    assert any(
        reference_map[reference_id]["observation"].get("presence") == "absent"
        for reference_id in cta["visual_evidence_refs"]
    )
    assert "assessed absence" in cta["rationale"].lower()
    assert "cta is present" not in cta["rationale"].lower()


def test_non_visual_asset_is_not_subject_to_visual_abstention():
    asset = create_asset(CreateCreativeAssetRequest(
        title="Copy only",
        asset_type="text",
        text_content="Clear text-only offer",
    ))

    result = run_confidence_aware_pipeline(asset.id, None, [], None, StubProvider())

    assert result["visual_decision_status"] == "not_applicable"
    assert result["effective_recommendation"] == result["final_recommendation"]
    assert result["visual_confidence_policy"]["envelope"]["status"] == "not_applicable"
    assert all(item["visual_abstention_status"] == "not_applicable" for item in result["scorecard"])


def test_policy_manifest_is_integrity_checked():
    asset = _asset(_visual_result(), title="Manifest integrity")
    result = run_confidence_aware_pipeline(asset.id, None, [], None, StubProvider())
    tampered = dict(result["visual_confidence_policy"])
    tampered["decision"] = dict(tampered["decision"])
    tampered["decision"]["effective_recommendation"] = "show_to_client"

    with pytest.raises(ValueError):
        validate_visual_confidence_policy_manifest(tampered)


def test_test_run_persists_policy_manifest_and_effective_recommendation():
    asset = _asset(_visual_result(extraction_confidence=0.6), title="Persisted confidence policy")
    created = create_test_run(CreateTestRunRequest(creative_asset_id=asset.id))

    completed = run_test_run(created.id)

    assert completed.status == "completed"
    assert completed.visual_confidence_policy is not None
    assert completed.visual_confidence_policy["fingerprint"]
    assert completed.visual_decision_status == "manual_review_required"
    assert completed.effective_recommendation == "manual_review"
    assert completed.visual_review_required_count > 0
    assert completed.final_recommendation in {"show_to_client", "revise", "reject"}
    cta = next(item for item in completed.scorecard if item.criterion == "call_to_action")
    assert cta.visual_abstention_status == "review_required"
