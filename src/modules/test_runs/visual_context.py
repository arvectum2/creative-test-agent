from __future__ import annotations

import hashlib
import json
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from src.shared.db.repository import json_loads
from src.shared.vision.schemas import (
    CanonicalVisualContext,
    VisionResult,
    VisualProvenance,
)


_VISUAL_ASSET_TYPES = {
    "image",
    "banner",
    "display",
    "social",
    "story",
    "pdf",
    "presentation",
    "slide",
    "video",
}
_OBSERVATION_FIELDS = (
    "ocr_text",
    "visual_summary",
    "brand_logo_prominence",
    "packshot",
    "cta",
    "promo_badge",
    "hierarchy",
    "message_visual_binding",
    "cognitive_load",
    "readability",
    "visual_risks",
)


def _fingerprint_payload(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class VisualEvidenceReference(BaseModel):
    """Immutable reference to one concrete populated visual observation."""

    schema_name: Literal["visual_evidence_reference"] = "visual_evidence_reference"
    schema_version: Literal["1.0"] = "1.0"
    reference_id: str = Field(min_length=1)
    reference_fingerprint: str = Field(min_length=64, max_length=64)
    creative_asset_id: str = Field(min_length=1)
    observation_path: str = Field(min_length=1)
    observation_type: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)
    provenance: list[VisualProvenance] = Field(min_length=1)
    observation: dict[str, Any]

    def integrity_payload(self) -> dict[str, Any]:
        return {
            "schema_name": self.schema_name,
            "schema_version": self.schema_version,
            "creative_asset_id": self.creative_asset_id,
            "observation_path": self.observation_path,
            "observation_type": self.observation_type,
            "confidence": self.confidence,
            "provenance": [item.model_dump(mode="json") for item in self.provenance],
            "observation": self.observation,
        }

    @model_validator(mode="after")
    def validate_integrity(self):
        expected_fingerprint = _fingerprint_payload(self.integrity_payload())
        expected_id = f"ve-{expected_fingerprint[:24]}"
        if self.reference_fingerprint != expected_fingerprint:
            raise ValueError("visual evidence reference fingerprint mismatch")
        if self.reference_id != expected_id:
            raise ValueError("visual evidence reference id mismatch")
        return self


class VisualEvidenceEnvelope(BaseModel):
    """Immutable stage input derived from the canonical visual context.

    The same serialized envelope is reused by every analytical stage. ``None`` values
    stay explicit so downstream prompts cannot confuse unassessed evidence with an
    assessed absence. Version 1.1 adds an integrity-checked registry of concrete
    observation references.
    """

    schema_name: Literal["visual_pipeline_evidence"] = "visual_pipeline_evidence"
    schema_version: Literal["1.0", "1.1"] = "1.1"
    creative_asset_id: str | None = None
    asset_requires_visual_evidence: bool
    status: Literal["not_applicable", "missing", "limited", "available"]
    extraction_confidence: float = Field(ge=0.0, le=1.0)
    evidence_confidence: float = Field(ge=0.0, le=1.0)
    completeness_ratio: float = Field(ge=0.0, le=1.0)
    warnings: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    references: list[VisualEvidenceReference] = Field(default_factory=list)
    fingerprint: str
    visual_context: CanonicalVisualContext | None = None

    @model_validator(mode="after")
    def validate_reference_registry(self):
        reference_ids = [item.reference_id for item in self.references]
        if len(reference_ids) != len(set(reference_ids)):
            raise ValueError("visual evidence reference ids must be unique")
        paths = [item.observation_path for item in self.references]
        if len(paths) != len(set(paths)):
            raise ValueError("visual evidence observation paths must be unique")
        if self.creative_asset_id is not None:
            for item in self.references:
                if item.creative_asset_id != self.creative_asset_id:
                    raise ValueError("visual evidence reference belongs to another creative asset")
        if self.schema_version == "1.1":
            payload = self.model_dump(mode="json", exclude={"fingerprint"}, exclude_none=False)
            if self.fingerprint != _fingerprint_payload(payload):
                raise ValueError("visual evidence envelope fingerprint mismatch")
        return self

    def prompt_json(self) -> str:
        return json.dumps(
            self.model_dump(mode="json", exclude_none=False),
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
        )

    def reference_map(self) -> dict[str, VisualEvidenceReference]:
        return {item.reference_id: item for item in self.references}

    def references_for_fields(self, fields: set[str] | list[str] | tuple[str, ...]) -> list[str]:
        allowed = set(fields)
        return [
            item.reference_id
            for item in self.references
            if _field_from_observation_path(item.observation_path) in allowed
        ]


def _field_from_observation_path(path: str) -> str:
    value = path.removeprefix("visual_context.")
    return value.split("[", 1)[0]


def _asset_requires_visual_evidence(asset: Any, has_visual_payload: bool) -> bool:
    if has_visual_payload:
        return True
    asset_type = str(getattr(asset, "asset_type", "") or "").strip().lower()
    return asset_type in _VISUAL_ASSET_TYPES or any(
        token in asset_type for token in ("image", "banner", "visual", "video", "slide")
    )


def _load_visual_context(asset: Any) -> tuple[CanonicalVisualContext | None, list[str], bool]:
    if asset is None:
        return None, ["creative_asset_missing"], False

    metadata = json_loads(getattr(asset, "metadata_json", None)) or {}
    raw = metadata.get("visual_analysis")
    if not isinstance(raw, dict) or not raw:
        return None, [], False

    try:
        result = VisionResult.model_validate(raw)
        return result.visual_context, [], True
    except Exception:
        nested = raw.get("visual_context")
        if isinstance(nested, dict):
            try:
                return CanonicalVisualContext.model_validate(nested), ["legacy_visual_surface_invalid"], True
            except Exception:
                pass
        return None, ["visual_context_invalid"], True


def _build_reference(
    *,
    creative_asset_id: str,
    observation_path: str,
    observation: Any,
) -> VisualEvidenceReference:
    observation_payload = observation.model_dump(mode="json", exclude_none=False)
    provenance = list(observation.provenance)
    payload = {
        "schema_name": "visual_evidence_reference",
        "schema_version": "1.0",
        "creative_asset_id": creative_asset_id,
        "observation_path": observation_path,
        "observation_type": observation.__class__.__name__,
        "confidence": float(observation.confidence),
        "provenance": [item.model_dump(mode="json") for item in provenance],
        "observation": observation_payload,
    }
    digest = _fingerprint_payload(payload)
    return VisualEvidenceReference(
        **payload,
        reference_id=f"ve-{digest[:24]}",
        reference_fingerprint=digest,
    )


def _build_references(asset: Any, context: CanonicalVisualContext) -> list[VisualEvidenceReference]:
    creative_asset_id = str(getattr(asset, "id", "") or "").strip()
    if not creative_asset_id:
        return []

    references: list[VisualEvidenceReference] = []
    for field in _OBSERVATION_FIELDS:
        observation = getattr(context, field, None)
        if observation is None:
            continue
        if isinstance(observation, list):
            for index, item in enumerate(observation):
                references.append(
                    _build_reference(
                        creative_asset_id=creative_asset_id,
                        observation_path=f"visual_context.{field}[{index}]",
                        observation=item,
                    )
                )
            continue
        references.append(
            _build_reference(
                creative_asset_id=creative_asset_id,
                observation_path=f"visual_context.{field}",
                observation=observation,
            )
        )
    return sorted(references, key=lambda item: item.observation_path)


def build_visual_evidence(asset: Any) -> VisualEvidenceEnvelope:
    context, adapter_warnings, has_visual_payload = _load_visual_context(asset)
    requires_visual = _asset_requires_visual_evidence(asset, has_visual_payload)
    creative_asset_id = str(getattr(asset, "id", "") or "").strip() or None

    if context is None:
        status = "missing" if requires_visual else "not_applicable"
        limitations = [
            "visual_evidence_missing: no canonical visual context is available; do not infer absence"
        ] if requires_visual else [
            "visual_analysis_not_applicable: the asset has no required visual evidence"
        ]
        payload = {
            "schema_name": "visual_pipeline_evidence",
            "schema_version": "1.1",
            "creative_asset_id": creative_asset_id,
            "asset_requires_visual_evidence": requires_visual,
            "status": status,
            "extraction_confidence": 0.0 if requires_visual else 1.0,
            "evidence_confidence": 0.0 if requires_visual else 1.0,
            "completeness_ratio": 0.0,
            "warnings": adapter_warnings,
            "limitations": limitations,
            "references": [],
            "visual_context": None,
        }
        return VisualEvidenceEnvelope(
            **payload,
            fingerprint=_fingerprint_payload(payload),
        )

    context_payload = context.model_dump(mode="json", exclude_none=False)
    populated = sum(context_payload.get(field) is not None for field in _OBSERVATION_FIELDS)
    completeness = populated / len(_OBSERVATION_FIELDS)
    extraction_confidence = float(context.extraction.confidence)
    warnings = list(dict.fromkeys([*context.extraction.warnings, *adapter_warnings]))

    unavailable = context.extraction.provider in {"stub", "error"} or extraction_confidence <= 0.0
    warning_penalty = 0.85 ** min(len(warnings), 3)
    coverage_factor = 0.35 + (0.65 * completeness)
    evidence_confidence = 0.0 if unavailable else extraction_confidence * coverage_factor * warning_penalty
    evidence_confidence = round(min(max(evidence_confidence, 0.0), 1.0), 4)

    missing_fields = [field for field in _OBSERVATION_FIELDS if context_payload.get(field) is None]
    limitations: list[str] = []
    if missing_fields:
        limitations.append("unassessed_visual_fields: " + ", ".join(missing_fields))
    if warnings:
        limitations.append("extraction_warnings: " + ", ".join(warnings))
    if extraction_confidence < 0.5:
        limitations.append("low_extraction_confidence: conclusions requiring visual evidence must be low-confidence")

    status = "available"
    if unavailable or evidence_confidence < 0.65 or completeness < 0.4 or warnings:
        status = "limited"

    references = _build_references(asset, context)
    payload = {
        "schema_name": "visual_pipeline_evidence",
        "schema_version": "1.1",
        "creative_asset_id": creative_asset_id,
        "asset_requires_visual_evidence": requires_visual,
        "status": status,
        "extraction_confidence": extraction_confidence,
        "evidence_confidence": evidence_confidence,
        "completeness_ratio": round(completeness, 4),
        "warnings": warnings,
        "limitations": limitations,
        "references": [item.model_dump(mode="json") for item in references],
        "visual_context": context_payload,
    }
    return VisualEvidenceEnvelope(
        **payload,
        fingerprint=_fingerprint_payload(payload),
    )


def resolve_visual_evidence(
    asset: Any,
    visual_evidence: VisualEvidenceEnvelope | dict[str, Any] | None = None,
) -> VisualEvidenceEnvelope:
    if isinstance(visual_evidence, VisualEvidenceEnvelope):
        return visual_evidence
    if isinstance(visual_evidence, dict):
        return VisualEvidenceEnvelope.model_validate(visual_evidence)
    return build_visual_evidence(asset)


def stage_confidence(envelope: VisualEvidenceEnvelope) -> float:
    if not envelope.asset_requires_visual_evidence:
        return 1.0
    return envelope.evidence_confidence


def render_visual_evidence_notes(envelope: VisualEvidenceEnvelope) -> str:
    parts = [
        f"Visual evidence status: {envelope.status}",
        f"Visual evidence confidence: {envelope.evidence_confidence:.2f}",
        f"Visual evidence fingerprint: {envelope.fingerprint}",
        f"Traceable visual observations: {len(envelope.references)}",
    ]
    context = envelope.visual_context
    if context is not None:
        parts.append(f"Analysis provider: {context.extraction.provider}")
        if context.visual_summary is not None:
            parts.append(f"Visual summary: {context.visual_summary.value}")
        if context.ocr_text is not None:
            parts.append(f"Detected text: {context.ocr_text.value}")
        if context.hierarchy is not None:
            hierarchy = context.hierarchy.ordered_elements or context.hierarchy.notes
            if hierarchy:
                parts.append("Visual hierarchy:")
                parts.extend(f"- {item}" for item in hierarchy)
        if context.visual_risks:
            parts.append("Visual risks:")
            parts.extend(
                f"- [{risk.level.upper()}] {risk.description} (confidence {risk.confidence:.2f})"
                for risk in context.visual_risks
            )
    if envelope.limitations:
        parts.append("Visual evidence limitations:")
        parts.extend(f"- {item}" for item in envelope.limitations)
    return "\n".join(parts)
