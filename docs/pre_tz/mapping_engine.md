# CTA-PRE-004 — Mapping Engine

Status: implemented.

## Purpose

The Mapping Engine converts structural information from CTA-PRE-003 into reviewable hypotheses about client-column meaning. It does not require the client to rename columns or fill a prescribed workbook.

The engine is deterministic and local. It does not call an LLM or an external API. Every suggested mapping contains a confidence score and an explanation that records the lexical, type and sample-value signals used.

## Target-field catalog

The initial internal catalog contains:

```text
campaign_reference
creative_reference
platform
placement_type
format
date
impressions
clicks
ctr
audience
brand
product
```

The catalog is deliberately small. Unknown client columns remain available in the inspected source layer and receive `unmapped` status rather than being discarded.

## Suggestion process

For every `SourceColumn`, the engine evaluates:

1. the original and normalized header;
2. Russian and English weighted synonyms;
3. the inferred source type;
4. bounded sample values saved by the inspector;
5. an optional confirmed mapping profile.

A run persists up to three candidates per column. The result includes:

```text
target_field
rank
confidence
method
explanation
```

The leading candidate becomes a review suggestion only when its confidence reaches the configured internal threshold. It is never automatically confirmed.

Typical explanation fields include:

```text
matched_alias
lexical_score
lexical_method
source_type
expected_types
type_adjustment
sample_adjustment
sample_reasons
```

## Analyst decisions

An analyst can:

- confirm a suggested target;
- choose another valid target manually;
- reject the proposed interpretation;
- leave the column unmapped.

Analyst decisions survive later forced suggestion runs. A target field cannot be confirmed for two source columns in the same table unless the caller explicitly permits a duplicate. This prevents accidental double use of metrics such as `clicks` or `impressions` while still allowing unusual client exports to be handled deliberately.

## Mapping profiles

A profile is created only from analyst-confirmed mappings. It is:

- project-scoped;
- versioned by profile name;
- linked to the table from which it was created;
- optionally described by source label, format and sheet-name pattern;
- composed of exact normalized source-column keys and confirmed target fields.

Applying a profile to a later export produces high-confidence suggestions. Profile rules still do not auto-confirm mappings. A profile cannot be applied to a different project.

If the file format or sheet name differs from the profile metadata, processing continues with an explicit warning so that imperfect client exports do not become an artificial blocker.

## Persistence

The stage introduces:

- `mapping_run` — one versioned engine execution for a source table;
- `mapping_suggestion` — ranked, explainable candidates;
- `column_mapping` — current review state for each source column;
- `mapping_profile` — reusable project-scoped configuration;
- `mapping_profile_rule` — confirmed source-key-to-target rules.

Suggestion runs are reusable by engine version and profile. `force=true` creates a new run number while preserving analyst-owned decisions.

## API

```text
GET  /mapping-fields

POST /import-sessions/{session_id}/files/{file_id}/tables/{table_id}/mapping/suggest
GET  /import-sessions/{session_id}/files/{file_id}/tables/{table_id}/mapping
PATCH /import-sessions/{session_id}/files/{file_id}/tables/{table_id}/mapping/columns/{column_id}
POST /import-sessions/{session_id}/files/{file_id}/tables/{table_id}/mapping/apply-profile

POST /mapping-profiles
GET  /mapping-profiles?project_id=...
GET  /mapping-profiles/{profile_id}
```

All write actions use the existing application authentication middleware and produce audit events.

## Explicit non-goals

CTA-PRE-004 does not:

- transform source values;
- create Campaign, Placement or PerformanceObservation records;
- calculate or reconcile CTR;
- link banner files to campaign rows;
- judge data quality beyond mapping-specific ambiguity;
- assess prediction readiness;
- define client brand-lift methodology;
- learn profile rules from unconfirmed suggestions.

Those capabilities belong to later normalization, data-quality and forecasting stages.
