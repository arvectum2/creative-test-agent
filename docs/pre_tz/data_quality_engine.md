# CTA-PRE-006 — Data Quality Engine

Status: implemented.

## Purpose

The Data Quality Engine turns the immutable import, inspected schema, analyst-confirmed mappings and latest normalized domain run into a reproducible quality report. It identifies what is usable, what needs review and what prevents the next processing step without requiring the client to restructure its source files.

The assessment chain is:

```text
immutable import session
→ file-integrity verification
→ inspected table and columns
→ current mapping decisions
→ latest normalized run
→ deterministic quality checks
→ aggregated issues and preliminary readiness indicators
```

The engine does not assign a synthetic numeric quality score. Its result is evidence-based and uses one of three statuses:

- `passed` — no warning or blocking issues;
- `review_required` — no blockers, but one or more warnings require analyst review;
- `blocked` — at least one issue prevents safe use of the current materialized data.

Informational issues do not lower the overall status.

## Categories

Every issue belongs to one of the roadmap categories:

- `file_integrity` — existence and SHA-256 verification of immutable originals;
- `schema_detection` — headers, truncation, empty tables and parser warnings;
- `mapping` — confirmation state, unmapped columns and duplicate targets;
- `missing_values` — field coverage and normalization failures;
- `duplicates` — identical files, source rows and performance observations;
- `creative_linking` — normalized creative references that are missing or ambiguous;
- `metric_consistency` — invalid signs, zero-impression clicks and CTR consistency;
- `prediction_readiness` — preliminary presence checks for creatives, media context and performance metrics.

## Severities

- `info` — useful context that does not require correction;
- `warning` — ambiguity or incomplete coverage that should be reviewed;
- `blocking` — corrupted/missing originals, unusable schema, absent confirmed mappings or normalization, no usable rows, or impossible metric values.

Each issue records category, code, severity, affected count, scope, source identifiers, machine-readable details and an optional remediation hint.

## Deterministic checks

### File integrity

The engine verifies every immutable source file in the import session using the stored SHA-256 value. Missing or changed originals are blocking. Identical source files are reported as possible duplicates, but are not deleted.

### Schema detection

Warnings created by the XLSX/CSV/TSV inspector are retained. Empty tables and materialized row truncation are blocking because the normalized layer would be incomplete. Low-confidence headers, duplicate headers, fallback encodings and truncated cell previews remain reviewable warnings.

### Mapping

Only `confirmed` mappings count as available domain fields. Suggested mappings require analyst confirmation. Unmapped and rejected columns remain in `source_payload` and `custom_fields`; they are reported but never discarded.

Several confirmed columns targeting the same internal field produce a warning because normalization uses the leftmost non-empty source value.

### Missing values

Coverage is calculated for every confirmed target field across normalized source rows. The report distinguishes:

- no source value for the field;
- a present raw value that could not be normalized.

Missing optional fields never reject otherwise usable rows. Missing creative/media/performance context is a warning because it limits later analysis.

### Duplicates

The engine reports:

- files with identical SHA-256 content;
- exact duplicate source-row payloads;
- performance observations with the same normalized campaign, creative, media context, date and metrics.

The engine does not remove or merge duplicates automatically.

### Creative linking

`CreativeRecord` entries are counted as linked or unlinked based on their relation to an existing project `CreativeAsset`. Ambiguous matches are reported separately. No fuzzy match is selected automatically.

### Metric consistency

The engine checks supplied source metrics without modifying them:

- negative impressions, clicks or CTR are blocking;
- positive clicks with zero impressions are blocking;
- clicks above impressions are a warning because metric definitions may differ;
- CTR above 1 is a warning unless the source definition confirms percentage units;
- when clicks, impressions and supplied CTR coexist, the engine compares them and reports material differences;
- a value such as `2` that aligns with `0.02` after division by 100 is reported as a possible percentage-scale mismatch.

The comparison is a quality check only. It does not write a derived CTR to the domain layer and does not produce a prediction.

## Preliminary readiness indicators

The report stores boolean indicators for:

- verified originals;
- completed inspection;
- at least one confirmed mapping;
- completed normalization;
- normalized creative references;
- linked creative assets;
- media context;
- performance metrics;
- rows containing both impressions and clicks.

These are inputs for CTA-PRE-008. CTA-PRE-006 does not decide whether CTR prediction, media baselines or synthetic surveys are available.

## Repeatability

Each run stores:

- engine name and version;
- a SHA-256 fingerprint of source files, inspection structure, current mapping state and normalized input semantics;
- source and normalization identifiers;
- coverage and issue counts;
- category/severity summaries;
- preliminary readiness indicators.

Repeated requests with the same semantic inputs return the existing completed run. `force=true` creates a separate explicit run. Mapping or normalizer changes produce a new fingerprint automatically.

## API

```text
POST /import-sessions/{session_id}/files/{file_id}/tables/{table_id}/data-quality
GET  /import-sessions/{session_id}/files/{file_id}/tables/{table_id}/data-quality

GET /data-quality-runs/{run_id}
GET /data-quality-runs/{run_id}/issues
```

Issue listing supports `category`, `severity`, `offset` and `limit`. Report generation is recorded in the audit log.

## Explicit non-goals

CTA-PRE-006 does not:

- change, delete or repair client source files;
- confirm column mappings automatically;
- reject rows solely because optional fields are absent;
- calculate a replacement CTR;
- train or invoke a predictive model;
- declare final prediction availability;
- generate client-facing XLSX/PPT/PDF reports;
- implement a client-specific brand-lift methodology.

Those responsibilities remain in later PRE-TZ stages.
