import pytest
from pydantic import ValidationError

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
from src.shared.vision.stub import StubVisionAnalyzer


def _provenance(evidence_key: str = "visual_analysis") -> list[VisualProvenance]:
    return [
        VisualProvenance(
            source_type="vlm",
            provider="local_vlm",
            model="fixture-vlm",
            evidence_key=evidence_key,
        )
    ]


def _extraction() -> VisualExtraction:
    return VisualExtraction(
        provider="local_vlm",
        confidence=0.82,
        provenance=_provenance(),
        warnings=[],
        metadata={"vlm_model": "fixture-vlm"},
    )


def test_full_canonical_visual_context_validates_and_round_trips():
    context = CanonicalVisualContext(
        extraction=_extraction(),
        ocr_text=TextObservation(
            value="Save 20% today",
            confidence=0.91,
            provenance=_provenance("visual_analysis.detected_text"),
        ),
        visual_summary=TextObservation(
            value="A product packshot beside a discount message.",
            confidence=0.84,
            provenance=_provenance("visual_analysis.visual_summary"),
        ),
        brand_logo_prominence=VisualElementObservation(
            presence="present",
            prominence="prominent",
            description="Brand logo in the upper-left corner.",
            confidence=0.88,
            provenance=_provenance("visual_analysis.brand_logo_prominence"),
        ),
        packshot=VisualElementObservation(
            presence="present",
            prominence="dominant",
            confidence=0.93,
            provenance=_provenance("visual_analysis.packshot"),
        ),
        cta=VisualElementObservation(
            presence="present",
            prominence="visible",
            text="Buy now",
            confidence=0.89,
            provenance=_provenance("visual_analysis.cta"),
        ),
        promo_badge=VisualElementObservation(
            presence="present",
            prominence="prominent",
            text="-20%",
            confidence=0.95,
            provenance=_provenance("visual_analysis.promo_badge"),
        ),
        hierarchy=HierarchyObservation(
            ordered_elements=["promo badge", "packshot", "CTA", "brand logo"],
            notes=["The discount is decoded before the brand."],
            confidence=0.78,
            provenance=_provenance("visual_analysis.hierarchy"),
        ),
        message_visual_binding=MessageVisualBindingObservation(
            level="strong",
            explanation="The packshot directly supports the product benefit.",
            confidence=0.8,
            provenance=_provenance("visual_analysis.message_visual_binding"),
        ),
        cognitive_load=CognitiveLoadObservation(
            level="medium",
            drivers=["four competing text blocks"],
            confidence=0.77,
            provenance=_provenance("visual_analysis.cognitive_load"),
        ),
        readability=ReadabilityObservation(
            level="mixed",
            issues=["small legal copy"],
            confidence=0.86,
            provenance=_provenance("visual_analysis.readability"),
        ),
        visual_risks=[
            VisualRiskObservation(
                risk_type="small_qualification",
                level="medium",
                description="Qualification text may be hard to read.",
                mitigation="Increase type size and contrast.",
                confidence=0.83,
                provenance=_provenance("visual_analysis.visual_risks.0"),
            )
        ],
    )

    payload = context.model_dump()
    restored = CanonicalVisualContext.model_validate(payload)

    assert restored.schema_name == "canonical_visual_context"
    assert restored.schema_version == "1.0"
    assert restored.packshot is not None
    assert restored.packshot.presence == "present"
    assert restored.visual_risks is not None
    assert restored.visual_risks[0].confidence == pytest.approx(0.83)


def test_unassessed_features_remain_missing_instead_of_defaulting_to_absent():
    context = CanonicalVisualContext(extraction=_extraction())

    assert context.brand_logo_prominence is None
    assert context.packshot is None
    assert context.cta is None
    assert context.promo_badge is None
    assert context.visual_risks is None

    compact = context.model_dump(exclude_none=True)
    assert "packshot" not in compact
    assert "cta" not in compact
    assert "visual_risks" not in compact


def test_every_populated_observation_requires_non_empty_provenance():
    with pytest.raises(ValidationError):
        TextObservation(value="Visible copy", confidence=0.8, provenance=[])


def test_confidence_is_bounded_for_extraction_and_observations():
    with pytest.raises(ValidationError):
        TextObservation(
            value="Visible copy",
            confidence=1.01,
            provenance=_provenance(),
        )

    with pytest.raises(ValidationError):
        VisualExtraction(
            provider="local_vlm",
            confidence=-0.01,
            provenance=_provenance(),
        )


def test_legacy_vision_result_adapts_without_inventing_new_features():
    result = VisionResult(
        provider="local_vlm",
        visual_summary="A product pack is shown beside a headline.",
        detected_text="Everyday relief",
        layout_notes=["Headline above packshot"],
        visual_risks=[
            {
                "risk_type": "low_contrast",
                "level": "medium",
                "description": "Secondary copy has low contrast.",
                "mitigation": "Increase contrast.",
            }
        ],
        metadata={"vlm_model": "fixture-vlm"},
    )

    context = result.visual_context
    assert context is not None
    assert context.visual_summary is not None
    assert context.visual_summary.value.startswith("A product pack")
    assert context.ocr_text is not None
    assert context.ocr_text.value == "Everyday relief"
    assert context.hierarchy is not None
    assert context.visual_risks is not None

    # The legacy result never represented these features, so the adapter must not guess.
    assert context.brand_logo_prominence is None
    assert context.packshot is None
    assert context.cta is None
    assert context.promo_badge is None
    assert context.message_visual_binding is None
    assert context.cognitive_load is None
    assert context.readability is None

    # Existing consumers keep receiving the legacy fields unchanged.
    assert result.visual_summary == "A product pack is shown beside a headline."
    assert result.detected_text == "Everyday relief"
    assert result.layout_notes == ["Headline above packshot"]


def test_stub_result_has_extraction_provenance_but_no_fabricated_observations():
    result = StubVisionAnalyzer().analyze_image("unused.png")

    assert result.visual_context is not None
    assert result.visual_context.extraction.provider == "stub"
    assert result.visual_context.extraction.confidence == 0.0
    assert result.visual_context.extraction.provenance
    assert result.visual_context.visual_summary is None
    assert result.visual_context.ocr_text is None
    assert result.visual_context.hierarchy is None


def test_canonical_only_result_backfills_legacy_surface_for_old_consumers():
    context = CanonicalVisualContext(
        extraction=_extraction(),
        ocr_text=TextObservation(
            value="Try it today",
            confidence=0.9,
            provenance=_provenance("visual_analysis.detected_text"),
        ),
        visual_summary=TextObservation(
            value="A centered packshot with a CTA below it.",
            confidence=0.85,
            provenance=_provenance("visual_analysis.visual_summary"),
        ),
        hierarchy=HierarchyObservation(
            ordered_elements=["packshot", "CTA"],
            confidence=0.8,
            provenance=_provenance("visual_analysis.hierarchy"),
        ),
        visual_risks=[
            VisualRiskObservation(
                risk_type="crowding",
                level="low",
                description="The footer is visually dense.",
                confidence=0.7,
                provenance=_provenance("visual_analysis.visual_risks.0"),
            )
        ],
    )

    result = VisionResult(visual_context=context)

    assert result.provider == "local_vlm"
    assert result.detected_text == "Try it today"
    assert result.visual_summary == "A centered packshot with a CTA below it."
    assert result.layout_notes == ["packshot", "CTA"]
    assert result.visual_risks[0].risk_type == "crowding"
