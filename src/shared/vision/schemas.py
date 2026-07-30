from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


VisualPresence = Literal["present", "absent", "uncertain"]
VisualProminence = Literal[
    "dominant",
    "prominent",
    "visible",
    "subtle",
    "not_visible",
    "unclear",
]


class VisualProvenance(BaseModel):
    """Machine-readable evidence reference for a visual observation."""

    source_type: str = Field(min_length=1)
    provider: str = Field(min_length=1)
    evidence_key: str = Field(min_length=1)
    model: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class EvidenceBoundObservation(BaseModel):
    """Base contract for every populated visual observation."""

    confidence: float = Field(ge=0.0, le=1.0)
    provenance: list[VisualProvenance] = Field(min_length=1)


class TextObservation(EvidenceBoundObservation):
    value: str = Field(min_length=1)


class VisualElementObservation(EvidenceBoundObservation):
    presence: VisualPresence
    prominence: VisualProminence | None = None
    text: str | None = None
    description: str | None = None


class HierarchyObservation(EvidenceBoundObservation):
    ordered_elements: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def require_hierarchy_evidence(self):
        if not self.ordered_elements and not self.notes:
            raise ValueError("hierarchy observation requires ordered_elements or notes")
        return self


class MessageVisualBindingObservation(EvidenceBoundObservation):
    level: Literal["strong", "moderate", "weak", "conflicting", "unclear"]
    explanation: str = Field(min_length=1)


class CognitiveLoadObservation(EvidenceBoundObservation):
    level: Literal["low", "medium", "high", "unclear"]
    drivers: list[str] = Field(default_factory=list)


class ReadabilityObservation(EvidenceBoundObservation):
    level: Literal["good", "mixed", "poor", "unclear"]
    issues: list[str] = Field(default_factory=list)


class VisualRiskObservation(EvidenceBoundObservation):
    risk_type: str = Field(min_length=1)
    level: Literal["low", "medium", "high", "unclear"]
    description: str = Field(min_length=1)
    mitigation: str | None = None


class VisualExtraction(BaseModel):
    """Provenance and confidence for the extraction operation itself."""

    provider: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)
    provenance: list[VisualProvenance] = Field(min_length=1)
    warnings: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class CanonicalVisualContext(BaseModel):
    """Canonical, evidence-bound visual context for one creative asset.

    Optional fields deliberately default to ``None``. ``None`` means the feature was
    not observed or not assessed. It must not be interpreted as an absent feature.
    An assessed absence is represented explicitly by ``presence='absent'``.
    """

    schema_name: Literal["canonical_visual_context"] = "canonical_visual_context"
    schema_version: Literal["1.0"] = "1.0"
    extraction: VisualExtraction
    ocr_text: TextObservation | None = None
    visual_summary: TextObservation | None = None
    brand_logo_prominence: VisualElementObservation | None = None
    packshot: VisualElementObservation | None = None
    cta: VisualElementObservation | None = None
    promo_badge: VisualElementObservation | None = None
    hierarchy: HierarchyObservation | None = None
    message_visual_binding: MessageVisualBindingObservation | None = None
    cognitive_load: CognitiveLoadObservation | None = None
    readability: ReadabilityObservation | None = None
    visual_risks: list[VisualRiskObservation] | None = None


class VisionRisk(BaseModel):
    """Legacy top-level risk shape retained for backward compatibility."""

    risk_type: str
    level: str  # low | medium | high
    description: str
    mitigation: str = ""


def _normalized_confidence(value: Any) -> float | None:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if numeric > 1.0 and numeric <= 100.0:
        numeric /= 100.0
    return min(max(numeric, 0.0), 1.0)


def _default_extraction_confidence(
    provider: str,
    metadata: dict[str, Any],
    warnings: list[str],
    has_observations: bool,
) -> float:
    for key in ("extraction_confidence", "confidence", "avg_confidence"):
        normalized = _normalized_confidence(metadata.get(key))
        if normalized is not None:
            return normalized

    unavailable_markers = ("unavailable", "failed", "errored", "disabled")
    if provider in {"stub", "error"} or any(
        marker in warning for warning in warnings for marker in unavailable_markers
    ):
        return 0.0
    return 0.5 if has_observations else 0.0


def _provider_provenance(
    provider: str,
    metadata: dict[str, Any],
    evidence_key: str,
) -> list[VisualProvenance]:
    if provider == "hybrid":
        refs: list[VisualProvenance] = []
        if metadata.get("ocr_engine"):
            refs.append(
                VisualProvenance(
                    source_type="ocr",
                    provider=str(metadata.get("ocr_engine")),
                    evidence_key=evidence_key,
                )
            )
        if metadata.get("vlm_model"):
            refs.append(
                VisualProvenance(
                    source_type="vlm",
                    provider="local_vlm",
                    model=str(metadata.get("vlm_model")),
                    evidence_key=evidence_key,
                )
            )
        if refs:
            return refs

    source_type = {
        "local_ocr": "ocr",
        "local_vlm": "vlm",
        "hybrid": "hybrid",
        "stub": "stub",
        "error": "system",
    }.get(provider, "legacy_adapter")
    model = metadata.get("vlm_model") or metadata.get("model")
    return [
        VisualProvenance(
            source_type=source_type,
            provider=provider or "unknown",
            model=str(model) if model else None,
            evidence_key=evidence_key,
        )
    ]


def build_canonical_visual_context(
    *,
    provider: str,
    visual_summary: str = "",
    detected_text: str = "",
    layout_notes: list[str] | None = None,
    visual_risks: list[VisionRisk | dict[str, Any]] | None = None,
    warnings: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
) -> CanonicalVisualContext:
    """Adapt the legacy ``VisionResult`` surface to the canonical context.

    The adapter only maps evidence that exists in the legacy payload. Features that
    were never represented by the legacy contract remain ``None``.
    """

    clean_summary = (visual_summary or "").strip()
    clean_text = (detected_text or "").strip()
    clean_layout = [str(item).strip() for item in (layout_notes or []) if str(item).strip()]
    clean_warnings = [str(item) for item in (warnings or [])]
    clean_metadata = dict(metadata or {})
    has_observations = bool(clean_summary or clean_text or clean_layout or visual_risks)
    confidence = _default_extraction_confidence(
        provider,
        clean_metadata,
        clean_warnings,
        has_observations,
    )
    extraction_provenance = _provider_provenance(
        provider,
        clean_metadata,
        "visual_analysis",
    )
    unavailable = provider in {"stub", "error"} or confidence == 0.0

    ocr_observation = None
    if clean_text and not unavailable:
        ocr_observation = TextObservation(
            value=clean_text,
            confidence=confidence,
            provenance=_provider_provenance(
                provider,
                clean_metadata,
                "visual_analysis.detected_text",
            ),
        )

    summary_observation = None
    if clean_summary and not unavailable and provider != "local_ocr":
        summary_observation = TextObservation(
            value=clean_summary,
            confidence=confidence,
            provenance=_provider_provenance(
                provider,
                clean_metadata,
                "visual_analysis.visual_summary",
            ),
        )

    hierarchy_observation = None
    if clean_layout and not unavailable and provider != "local_ocr":
        hierarchy_observation = HierarchyObservation(
            notes=clean_layout,
            confidence=confidence,
            provenance=_provider_provenance(
                provider,
                clean_metadata,
                "visual_analysis.layout_notes",
            ),
        )

    canonical_risks: list[VisualRiskObservation] | None = None
    if visual_risks and not unavailable:
        canonical_risks = []
        for risk in visual_risks:
            payload = risk.model_dump() if isinstance(risk, BaseModel) else dict(risk)
            level = str(payload.get("level") or "unclear").lower()
            if level not in {"low", "medium", "high", "unclear"}:
                level = "unclear"
            description = str(payload.get("description") or "").strip()
            risk_type = str(payload.get("risk_type") or "visual_risk").strip()
            if not description:
                continue
            canonical_risks.append(
                VisualRiskObservation(
                    risk_type=risk_type or "visual_risk",
                    level=level,
                    description=description,
                    mitigation=str(payload.get("mitigation") or "").strip() or None,
                    confidence=confidence,
                    provenance=_provider_provenance(
                        provider,
                        clean_metadata,
                        "visual_analysis.visual_risks",
                    ),
                )
            )
        if not canonical_risks:
            canonical_risks = None

    return CanonicalVisualContext(
        extraction=VisualExtraction(
            provider=provider or "unknown",
            confidence=confidence,
            provenance=extraction_provenance,
            warnings=clean_warnings,
            metadata=clean_metadata,
        ),
        ocr_text=ocr_observation,
        visual_summary=summary_observation,
        hierarchy=hierarchy_observation,
        visual_risks=canonical_risks,
    )


class VisionResult(BaseModel):
    """Vision result with the legacy surface plus canonical visual context."""

    provider: str = "stub"
    visual_summary: str = ""
    detected_text: str = ""
    layout_notes: list[str] = Field(default_factory=list)
    visual_risks: list[VisionRisk] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    visual_context: CanonicalVisualContext | None = None

    @model_validator(mode="after")
    def synchronize_legacy_and_canonical_shapes(self):
        if self.visual_context is None:
            self.visual_context = build_canonical_visual_context(
                provider=self.provider,
                visual_summary=self.visual_summary,
                detected_text=self.detected_text,
                layout_notes=self.layout_notes,
                visual_risks=self.visual_risks,
                warnings=self.warnings,
                metadata=self.metadata,
            )
            return self

        context = self.visual_context
        if self.provider == "stub" and context.extraction.provider != "stub":
            self.provider = context.extraction.provider
        if not self.visual_summary and context.visual_summary is not None:
            self.visual_summary = context.visual_summary.value
        if not self.detected_text and context.ocr_text is not None:
            self.detected_text = context.ocr_text.value
        if not self.layout_notes and context.hierarchy is not None:
            self.layout_notes = context.hierarchy.notes or context.hierarchy.ordered_elements
        if not self.visual_risks and context.visual_risks:
            self.visual_risks = [
                VisionRisk(
                    risk_type=risk.risk_type,
                    level=risk.level,
                    description=risk.description,
                    mitigation=risk.mitigation or "",
                )
                for risk in context.visual_risks
            ]
        if not self.warnings:
            self.warnings = list(context.extraction.warnings)
        if not self.metadata:
            self.metadata = dict(context.extraction.metadata)
        return self


class VisionProviderHealth(BaseModel):
    provider: str = "stub"
    api_style: str = "ollama"
    local_ocr_enabled: bool = False
    local_vlm_enabled: bool = False
    available: bool = True
    warnings: list[str] = Field(default_factory=list)
    vlm_model_found: str | None = None
