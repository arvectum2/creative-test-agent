import json

from src.modules.audience_profiles.schemas import CreateAudienceProfileRequest
from src.modules.audience_profiles.service import create_profile as create_audience
from src.modules.brand_profiles.schemas import CreateBrandProfileRequest
from src.modules.brand_profiles.service import create_profile as create_brand
from src.modules.creative_assets.schemas import CreateCreativeAssetRequest
from src.modules.creative_assets.service import create_asset
from src.modules.test_rubrics.schemas import CreateTestRubricRequest
from src.modules.test_rubrics.service import create_rubric
from src.modules.test_runs.pipeline import STUB_SCORECARD, run_pipeline
from src.modules.test_runs.schemas import CreateTestRunRequest
from src.modules.test_runs.service import create_test_run, run_test_run
from src.shared.llm.base import LLMProvider
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
            model="test-vlm",
            evidence_key=key,
        )
    ]


def _full_visual_result(extraction_confidence: float = 0.9) -> dict:
    context = CanonicalVisualContext(
        extraction=VisualExtraction(
            provider="local_vlm",
            confidence=extraction_confidence,
            provenance=_provenance("visual_analysis"),
            warnings=[],
            metadata={"model": "test-vlm"},
        ),
        ocr_text=TextObservation(
            value="Try it today",
            confidence=0.94,
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
            presence="present",
            prominence="visible",
            text="Try it today",
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


class RecordingProvider(LLMProvider):
    def __init__(self):
        self.prompts: list[str] = []

    def generate(self, prompt: str, metadata: dict | None = None) -> dict:
        self.prompts.append(prompt)
        if "creative intake agent" in prompt:
            payload = {
                "summary": "Evidence-based summary",
                "key_message": "Try it today",
                "tone": "confident",
                "target_audience_vibe": "general consumers",
                "confidence": 0.8,
            }
        elif "audience simulation agent" in prompt:
            payload = {
                "reaction": "The message is understandable.",
                "positive_triggers": ["clear CTA"],
                "objections": [],
                "engagement_probability": 7.0,
                "confidence": 0.8,
            }
        elif "brand safety agent" in prompt:
            payload = {
                "overall_risk_level": "medium",
                "risks": [{
                    "risk_type": "small_disclaimer",
                    "level": "medium",
                    "description": "Disclaimer is small.",
                    "mitigation": "Increase its size.",
                    "confidence": 0.8,
                }],
                "brand_fit_score": 8.0,
                "claims_compliance": "needs_review",
                "confidence": 0.8,
            }
        elif "brandbook compliance agent" in prompt:
            payload = {
                "overall_verdict": "needs_revision",
                "violations": [],
                "recommendations": ["Review disclaimer size"],
                "compliance_score": 8.0,
                "confidence": 0.8,
            }
        elif "rubric scoring agent" in prompt:
            payload = {
                "scorecard": [{
                    "criterion": "message_clarity",
                    "score": 8.0,
                    "rationale": "The CTA is readable.",
                    "recommendation": "Keep the CTA.",
                    "confidence": 0.8,
                }],
                "overall_score": 8.0,
                "strengths": ["message_clarity"],
                "weaknesses": [],
            }
        else:
            payload = {
                "final_recommendation": "revise",
                "rationale": "The disclaimer needs revision.",
                "top_actions": ["Increase disclaimer size"],
                "confidence": "medium",
            }
        return {"content": json.dumps(payload)}


def _build_live_dependencies():
    audience = create_audience(CreateAudienceProfileRequest(
        name="Segment",
        segment_description="Test audience",
    ))
    brand = create_brand(CreateBrandProfileRequest(
        name="Brand",
        tone_of_voice="clear",
        restrictions="Disclaimers must be readable",
    ))
    rubric = create_rubric(CreateTestRubricRequest(name="Rubric"))
    return audience, brand, rubric


def test_every_live_stage_receives_identical_visual_evidence_model():
    asset = create_asset(CreateCreativeAssetRequest(
        title="Visual creative",
        asset_type="image",
        text_content="Try it today",
        metadata={"visual_analysis": _full_visual_result()},
    ))
    audience, brand, rubric = _build_live_dependencies()
    provider = RecordingProvider()

    result = run_pipeline(
        creative_asset_id=asset.id,
        brand_profile_id=brand.id,
        audience_profile_ids=[audience.id],
        rubric_id=rubric.id,
        provider=provider,
    )

    assert len(provider.prompts) == 6
    fingerprint = result["visual_evidence"]["fingerprint"]
    for prompt in provider.prompts:
        assert fingerprint in prompt
        assert '"schema_name": "visual_pipeline_evidence"' in prompt
        assert '"schema_name": "canonical_visual_context"' in prompt

    assert result["visual_context"]["packshot"]["presence"] == "present"
    assert result["visual_context"]["promo_badge"]["presence"] == "absent"
    assert result["audience_reactions"][0]["visual_evidence_fingerprint"] == fingerprint
    assert result["scorecard"][0]["visual_evidence_fingerprint"] == fingerprint
    assert result["brandbook_compliance"]["visual_evidence_fingerprint"] == fingerprint
    assert result["final_recommendation_details"]["visual_evidence_fingerprint"] == fingerprint


def test_missing_visual_fields_remain_unassessed_and_lower_confidence_not_scores():
    partial = VisionResult(
        provider="local_vlm",
        detected_text="Try it today",
        metadata={"extraction_confidence": 0.8, "model": "partial-vlm"},
    ).model_dump(mode="json")
    asset = create_asset(CreateCreativeAssetRequest(
        title="Partial visual creative",
        asset_type="image",
        text_content="Try it today",
        metadata={"visual_analysis": partial},
    ))

    result = run_pipeline(
        creative_asset_id=asset.id,
        brand_profile_id=None,
        audience_profile_ids=[],
        rubric_id=None,
        provider=StubProvider(),
    )

    assert result["visual_context"]["packshot"] is None
    assert result["visual_context"]["cta"] is None
    assert result["visual_evidence"]["status"] == "limited"
    assert result["visual_evidence_confidence"] < 0.8
    assert [item["score"] for item in result["scorecard"]] == [item["score"] for item in STUB_SCORECARD]
    visual_criteria = {
        item["criterion"]: item["confidence"]
        for item in result["scorecard"]
        if item["criterion"] in {"memorability", "call_to_action", "brand_fit", "distinctiveness"}
    }
    assert visual_criteria
    assert all(confidence < 0.8 for confidence in visual_criteria.values())
    assert '"presence": "absent"' not in json.dumps(result["visual_context"])


def test_failed_extraction_sets_zero_visual_confidence_without_penalizing_score():
    failed = VisionResult(
        provider="error",
        warnings=["visual_analysis_errored"],
    ).model_dump(mode="json")
    asset = create_asset(CreateCreativeAssetRequest(
        title="Failed extraction creative",
        asset_type="image",
        text_content="A clear text message",
        metadata={"visual_analysis": failed},
    ))

    result = run_pipeline(
        creative_asset_id=asset.id,
        brand_profile_id=None,
        audience_profile_ids=[],
        rubric_id=None,
        provider=StubProvider(),
    )

    assert result["visual_evidence_confidence"] == 0.0
    assert result["visual_evidence"]["status"] == "limited"
    assert [item["score"] for item in result["scorecard"]] == [item["score"] for item in STUB_SCORECARD]
    assert result["final_recommendation_details"]["confidence_score"] == 0.0
    assert result["brandbook_compliance"]["compliance_score"] == 9.0


def test_test_run_persists_canonical_visual_evidence_and_decision_confidence():
    asset = create_asset(CreateCreativeAssetRequest(
        title="Persisted visual creative",
        asset_type="image",
        text_content="Try it today",
        metadata={"visual_analysis": _full_visual_result()},
    ))
    created = create_test_run(CreateTestRunRequest(creative_asset_id=asset.id))

    completed = run_test_run(created.id)

    assert completed.status == "completed"
    assert completed.visual_context is not None
    assert completed.visual_context["schema_name"] == "canonical_visual_context"
    assert completed.visual_evidence is not None
    assert completed.visual_evidence["fingerprint"]
    assert 0.0 <= completed.final_recommendation_confidence <= 1.0
    assert completed.scorecard[0].visual_evidence_fingerprint == completed.visual_evidence["fingerprint"]
