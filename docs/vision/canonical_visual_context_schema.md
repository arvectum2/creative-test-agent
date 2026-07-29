# Canonical Visual Context Schema

Task: `CTA-017 — Canonical Visual Context Schema`  
Canonical roadmap mapping: `CTA-VIS-002 — Unified Creative Visual Context`  
Schema name: `canonical_visual_context`  
Schema version: `1.0`

## Purpose

The canonical visual context is the single typed evidence contract between local visual extraction and downstream creative analysis.

It does not claim that a feature is absent merely because a provider did not extract it. An unobserved or unassessed feature is represented by `null` (or omitted when serializing with `exclude_none=True`). An assessed absence is represented explicitly by an element observation with `presence: "absent"`.

## Storage and backward compatibility

Visual analysis remains stored at `creative_asset.metadata.visual_analysis`.

The existing top-level fields are retained:

- `provider`;
- `visual_summary`;
- `detected_text`;
- `layout_notes`;
- `visual_risks`;
- `warnings`;
- `metadata`.

A new sibling field, `visual_context`, contains the canonical contract. `VisionResult` synchronizes the two surfaces:

- legacy-only payloads are adapted to `visual_context` without guessing fields that did not exist in the legacy payload;
- canonical-only payloads backfill the legacy fields needed by current consumers;
- existing report and test-run code can continue reading the top-level fields until `CTA-VIS-003` propagates the canonical context through every stage.

## Canonical fields

`CanonicalVisualContext` contains:

- `extraction` — provider, overall extraction confidence, provenance, warnings and provider metadata;
- `ocr_text`;
- `visual_summary`;
- `brand_logo_prominence`;
- `packshot`;
- `cta`;
- `promo_badge`;
- `hierarchy`;
- `message_visual_binding`;
- `cognitive_load`;
- `readability`;
- `visual_risks`.

Every populated observation inherits the same evidence contract:

```json
{
  "confidence": 0.84,
  "provenance": [
    {
      "source_type": "vlm",
      "provider": "local_vlm",
      "model": "qwen3-vl:8b",
      "evidence_key": "visual_analysis.visual_summary",
      "details": {}
    }
  ]
}
```

Confidence is bounded to `[0, 1]`. Provenance must contain at least one reference.

## Missing versus absent

```json
{
  "packshot": null
}
```

means that packshot presence was not assessed or could not be extracted.

```json
{
  "packshot": {
    "presence": "absent",
    "prominence": "not_visible",
    "confidence": 0.91,
    "provenance": [
      {
        "source_type": "vlm",
        "provider": "local_vlm",
        "model": "local-model",
        "evidence_key": "visual_analysis.packshot",
        "details": {}
      }
    ]
  }
}
```

means that the provider explicitly assessed the packshot and found it absent.

## Legacy adaptation boundary

The legacy contract can safely populate only:

- OCR text from `detected_text`;
- visual summary from `visual_summary` for VLM/hybrid providers;
- hierarchy notes from `layout_notes` for VLM/hybrid providers;
- visual risks from `visual_risks`.

It cannot infer brand/logo prominence, packshot, CTA, promo badge, message–visual binding, cognitive load or readability. Those fields remain `null` until a provider or human reviewer supplies evidence-bound observations.

Stub, unavailable and failed extraction results contain extraction provenance and warnings but do not convert placeholder text into visual observations.

## Validation

Regression coverage is in `tests/test_canonical_visual_context_schema.py` and verifies:

- complete schema round-trip;
- missing-field semantics;
- mandatory provenance;
- bounded confidence;
- legacy-to-canonical adaptation;
- canonical-to-legacy compatibility;
- no fabricated observations in stub mode.

## Non-goals

This task does not:

- propagate the canonical context through all prompts and reports;
- select a local OCR/VLM model;
- establish production accuracy;
- predict CTR, causal brand lift or uplift;
- convert missing evidence into a creative conclusion.
