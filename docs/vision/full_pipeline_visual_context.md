# Full-Pipeline Visual Context Propagation

Task: `CTA-018 — Visual Context Pipeline Integration`  
Canonical roadmap mapping: `CTA-VIS-003 — Full-Pipeline Visual Context Propagation`

## Purpose

This integration carries one canonical, evidence-bound visual model through the complete creative-analysis pipeline. The visual context is built once for a creative asset and reused unchanged by:

1. creative summary;
2. audience simulation;
3. brand safety;
4. brandbook compliance;
5. rubric scoring;
6. final recommendation.

The pipeline remains local-first. The integration does not select a vision model and does not make production-accuracy, CTR, causal brand-lift or uplift claims.

## Visual evidence envelope

`src/modules/test_runs/visual_context.py` wraps `CanonicalVisualContext` in `VisualEvidenceEnvelope`.

The envelope contains:

- the canonical context with explicit `null` values;
- extraction confidence;
- evidence confidence;
- observation completeness;
- provider warnings;
- evidence limitations;
- a deterministic SHA-256 fingerprint;
- evidence status: `not_applicable`, `missing`, `limited` or `available`.

`null` always means unobserved or unassessed. It must never be interpreted as absence. An assessed absence remains an explicit observation with `presence: "absent"`, confidence and provenance.

## One model for every stage

`run_pipeline()` resolves the visual evidence envelope once. The exact same object and fingerprint are supplied to all six stages. Live prompts receive the same serialized JSON document under `Canonical Visual Evidence`.

Direct calls to individual stage functions remain backward compatible: callers may omit `visual_evidence`, in which case the stage resolves the envelope from the creative asset.

## Confidence behavior

Evidence confidence is derived deterministically from:

- extraction confidence;
- populated-observation coverage;
- extraction warnings;
- unavailable/error provider states.

Poor extraction lowers the confidence of visually dependent conclusions. It does not automatically lower the creative score and does not create a negative finding. Copy-only or otherwise independently supported conclusions remain usable with their own evidence boundary.

The final recommendation confidence is capped by the weakest material evidence component. This is diagnostic confidence, not certainty of market effect.

## Prompt rules

Every analytical prompt states that:

- missing is not absent;
- only populated observations may be used;
- confidence and provenance must be respected;
- missing or limited extraction lowers confidence and can trigger manual review;
- extraction gaps are not automatic score penalties or compliance violations;
- causal lift, percentage-point uplift and real-respondent claims are prohibited.

## Persistence and API

The canonical visual context, envelope, fingerprint, confidence metadata and final-recommendation details are stored in the existing `structured_findings_json` field. No database migration is required.

`TestRunResponse` exposes:

- `visual_context`;
- `visual_evidence`;
- finding and scorecard confidence;
- evidence notes and fingerprints;
- risk provenance;
- brandbook-compliance confidence;
- final-recommendation confidence, rationale and actions.

Legacy test-run fields and the public `final_recommendation()` string return are preserved.

## Regression coverage

`tests/test_visual_context_pipeline.py` verifies that:

- all six live prompts receive the identical visual evidence fingerprint and canonical model;
- explicit assessed absence survives propagation;
- unassessed fields remain `null`;
- partial extraction lowers visual confidence without changing deterministic score values;
- failed extraction produces zero visual confidence without fabricating a creative failure;
- test-run persistence and API responses retain the canonical evidence model.

## Non-goals

This task does not:

- select or benchmark a production OCR/VLM;
- validate real-market predictive accuracy;
- predict CTR, awareness lift, consideration lift or purchase-intent uplift;
- commit client creative assets;
- treat synthetic audience simulations as human research.
