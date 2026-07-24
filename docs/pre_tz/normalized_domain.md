# CTA-PRE-005 — normalized minimal domain layer

Status: implemented.

## Purpose

The normalized domain layer converts confirmed column mappings from immutable inspected tables into a small, nullable-first campaign model. It does not require a complete client export and does not calculate or predict CTR.

The processing chain is:

```text
immutable source file
→ inspected source table and rows
→ confirmed column mappings
→ versioned normalization run
→ normalized domain records
→ field-level provenance
```

## Domain records

A normalization run may create:

- `Campaign` — source campaign reference, brand and product;
- `CreativeRecord` — a source creative reference and an optional link to an existing `CreativeAsset`;
- `Platform` — a deduplicated platform name inside the run;
- `AudienceSegment` — a deduplicated audience label inside the run;
- `Placement` — row-level media context linking the campaign, creative, platform and audience;
- `PerformanceObservation` — the source date, impressions, clicks and supplied CTR;
- `NormalizedSourceRow` — the row-level bridge between source data and all created domain records;
- `NormalizedFieldValue` — provenance for every selected mapped value.

All business fields are optional. The only required data is technical provenance identifying the immutable source and the normalization run.

## Mapping precondition

Only mappings with `status=confirmed` are used. Suggested mappings are never silently promoted during normalization.

At least one confirmed mapping is required to start a run. Missing target fields, missing media context, missing metrics and missing creative files do not reject the remaining rows.

If several confirmed source columns point to the same target field, the leftmost non-empty value is used for each row and the conflict is recorded as a non-blocking issue.

## Repeatability and idempotency

Each run stores:

- normalizer name and version;
- a complete snapshot of the confirmed mappings;
- a SHA-256 fingerprint of that snapshot;
- source table, file, import session and project identifiers;
- row and entity counts;
- run-level warnings.

Calling normalization again with the same source table, normalizer version and mapping fingerprint returns the existing completed run. `force=true` creates an explicit new run. A changed confirmed mapping produces a different fingerprint and therefore a new run without needing `force=true`.

Domain records are unique inside a run, and each source row produces at most one placement, one performance observation and one normalized row in that run. Intentional forced or changed-mapping runs remain separately reproducible rather than overwriting history.

## Value normalization

Version `1.0.0` uses deterministic rules:

- text values are trimmed and bounded to the domain-column size while the full raw value remains in provenance;
- impressions and clicks accept integers and integral numeric text;
- a CTR value with `%` is converted to a ratio (`2.1%` → `0.021`);
- a numeric CTR without `%` is preserved as supplied and is not guessed to be a percentage;
- supported dates are converted to a date value;
- parse failures leave the normalized field empty, preserve the raw value and mark the row `partial`.

CTR is never derived from clicks and impressions at this stage.

## Creative assets

`CreativeRecord` does not copy or replace an uploaded creative. It stores the source reference and attempts an exact, case-insensitive match against the current project's `CreativeAsset` id, title or original filename.

- one match: `creative_asset_id` is linked;
- no match: the normalized creative remains usable and an informational issue is recorded;
- several matches: no asset is selected and a warning is recorded.

## Provenance

Every non-empty confirmed mapped value creates a `NormalizedFieldValue` containing:

- source file, table, row and column identifiers;
- original row number and source column name;
- column mapping and optional mapping profile identifiers;
- raw and normalized values;
- transformation name;
- normalization version;
- resulting entity type and identifier.

The entire source row is retained in `source_payload`. Columns that were not confirmed are retained in `custom_fields`; they are not discarded.

## Row statuses

- `normalized` — at least one mapped value was processed without warning-level issues;
- `partial` — useful records were created, but one or more mapped values could not be parsed or an ambiguity was found;
- `skipped` — the row contains no non-empty confirmed mapped value;
- `failed` — reserved for a future persisted row-level fatal failure path.

Missing optional fields alone do not make a row partial.

## API

```text
POST /import-sessions/{session_id}/files/{file_id}/tables/{table_id}/normalize
GET  /import-sessions/{session_id}/files/{file_id}/tables/{table_id}/normalization

GET /normalization-runs/{run_id}
GET /normalization-runs/{run_id}/rows
GET /normalization-runs/{run_id}/campaigns
GET /normalization-runs/{run_id}/creatives
GET /normalization-runs/{run_id}/platforms
GET /normalization-runs/{run_id}/audience-segments
GET /normalization-runs/{run_id}/placements
GET /normalization-runs/{run_id}/performance-observations
```

The POST endpoint is audited. Responses expose source identifiers and provenance but never expose internal storage paths.

## Explicit non-goals

CTA-PRE-005 does not:

- calculate CTR from clicks and impressions;
- validate metric consistency or business plausibility;
- merge duplicate campaigns across separate client deliveries;
- infer missing platform or placement context;
- automatically link creative files using fuzzy similarity;
- determine prediction readiness;
- train or invoke a predictive model;
- implement a client-specific brand-lift methodology.

Those concerns belong to data quality, clarification and prediction-readiness stages.
