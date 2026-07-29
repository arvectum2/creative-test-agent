# Visual Evidence Traceability

Task: `CTA-019 — Visual Evidence Traceability`  
Canonical roadmap mapping: `CTA-VIS-004 — Visual Evidence Traceability`

## Purpose

Every accepted visual finding must resolve to a concrete populated observation from the canonical visual context. The system does not accept a visual conclusion merely because a model produced plausible wording.

The implementation remains local-first and evidence-bound. It does not validate production accuracy, predict CTR or brand lift, or represent synthetic audience simulation as human research.

## Observation references

`VisualEvidenceEnvelope` schema version `1.1` embeds a registry of `VisualEvidenceReference` objects. One reference is created for every populated canonical observation:

- OCR text;
- visual summary;
- brand/logo prominence;
- packshot;
- CTA;
- promo badge;
- hierarchy;
- message–visual binding;
- cognitive load;
- readability;
- each individual visual risk.

Unassessed `null` fields do not receive references. An explicitly assessed absence such as `presence: "absent"` is a populated observation and therefore receives a citable reference.

Each reference contains:

- a deterministic `reference_id`;
- an integrity fingerprint;
- the creative asset ID;
- the exact observation path;
- the observation type and immutable observation snapshot;
- observation confidence;
- full provenance.

Reference IDs and fingerprints are recomputed during validation. A modified observation, stale ID, foreign-asset reference or corrupted envelope fails validation.

## Finding bindings

The canonical persisted test-run path is `run_traceable_pipeline()`. It executes the same six analytical stages as the existing pipeline and then validates visual references for:

1. creative summary;
2. audience reactions;
3. rubric scorecard findings;
4. brand-safety risks;
5. brandbook-compliance violations and overall conclusion;
6. final recommendation.

Accepted references are stored on the finding under `visual_evidence_refs`. Rejected IDs are preserved separately under `rejected_visual_evidence_refs` for audit. Every item receives `visual_traceability_status` and `traceability_notes`.

Supported statuses are:

- `supported` — all accepted visual premises have valid relevant references;
- `partial` — at least one valid reference exists, but another supplied reference was rejected or an inherited visual finding is unresolved;
- `unsupported` — a visual conclusion attempted to rely on missing, unknown, stale or criterion-unrelated references;
- `unassessed` — the criterion requires visual evidence but no populated relevant observation exists;
- `not_used` — the conclusion is copy-, audience-, brief- or brand-context-based and does not rely on visual evidence;
- `not_applicable` — the asset does not require visual evidence.

## Fail-closed behavior

Visual-dependent score values remain unchanged when extraction is missing, preserving the score-versus-confidence rule introduced in CTA-018. The unsupported visual rationale is not accepted:

- diagnostic confidence becomes zero;
- the visual rationale is replaced with an explicit unsupported or unassessed statement;
- a manual extraction/review action is supplied;
- unknown and criterion-unrelated IDs are rejected;
- copy-only findings remain usable without visual references.

This prevents an extraction gap from silently becoming either an invented negative finding or an invented positive claim.

## Criterion relevance

Rubric findings accept references only from fields relevant to that criterion. Examples:

- `call_to_action` → CTA, hierarchy, readability;
- `brand_fit` → logo prominence, packshot, message–visual binding;
- `readability` → readability and OCR observations;
- `cognitive_load` → cognitive-load and hierarchy observations.

A valid reference from an unrelated field is rejected as `criterion_unrelated_reference`.

## Trace manifest

Every completed test run stores `visual_evidence_trace` in the existing `structured_findings_json` field. No database migration is required.

The trace manifest contains:

- creative asset ID;
- visual evidence fingerprint;
- deterministic trace fingerprint;
- reference count;
- accepted and rejected reference IDs;
- finding-level bindings by stage and key;
- unresolved visual finding count;
- overall trace status: `complete`, `needs_review`, `unassessed` or `not_applicable`.

`TestRunResponse` exposes the envelope registry, trace manifest, finding-level bindings, final-recommendation references and aggregate status.

## Prompt contract

All six analytical prompts receive the same envelope, including its reference registry. They instruct live models to:

- cite exact registry IDs for visual or mixed conclusions;
- return an empty reference list for non-visual conclusions;
- never invent, shorten or reuse IDs from another asset;
- preserve missing-versus-absent semantics;
- avoid causal lift and real-respondent claims.

The application validates output references after generation; prompt compliance alone is not trusted.

## Regression coverage

`tests/test_visual_evidence_traceability.py` verifies:

- deterministic reference generation;
- integrity failure after observation tampering;
- explicit absence as a citable observation;
- no reference for unassessed fields;
- score preservation with zero confidence for unassessed visual criteria;
- rejection of unknown and criterion-unrelated references;
- deterministic stub bindings;
- persistence and API exposure of the reference registry and trace manifest.

## Non-goals

This task does not:

- select or benchmark OCR/VLM models;
- claim validated diagnostic accuracy;
- predict CTR, awareness lift, consideration lift or purchase-intent uplift;
- commit client creative assets;
- add a client-facing traceability UI;
- replace future expert review and adjudication workflows.
