# CTA-PRE-007 — progressive clarification questions

Status: implemented.

## Purpose

The clarification layer converts persisted Data Quality Engine evidence into a short, ranked batch of questions. It is designed for the agreed operating principle: accept the client’s files as supplied, inspect them locally, and ask only the questions that materially affect the next step.

The chain is:

```text
immutable originals
→ inspected tables
→ confirmed mappings
→ normalized domain
→ data-quality run
→ ranked clarification candidates
→ up to 3–5 questions
→ recorded responses
→ next progressive batch
```

The generator is deterministic and local. It does not use a cloud model and does not create generic questionnaires.

## Progressive batch size

A generation request specifies a maximum between three and five questions. The generator may return fewer than three when fewer evidence-backed gaps exist. It never pads a batch with filler questions.

Candidate ranking prioritizes:

1. corrupted or missing source evidence;
2. impossible or ambiguous metric definitions;
3. inability to join historical rows to creatives;
4. missing media context or comparable clicks/impressions;
5. duplicate and missing-value policies.

Only the highest-ranked unresolved candidates are materialized in a run. Lower-ranked candidates remain available for a later batch.

## Audiences

Questions are separated by audience:

- `client` — facts only the client or data owner can resolve, such as metric definitions, join keys, missing creative files and whether duplicates are intentional;
- `analyst` — internal actions such as confirming headers, approving mappings, increasing inspection limits or selecting among ambiguous local assets.

This separation prevents internal implementation problems from being sent to the client as unnecessary questions.

## Evidence requirements

Every question stores:

- the originating data-quality run and its input fingerprint;
- the relevant data-quality issue IDs and codes;
- affected counts and severities;
- source file and table identifiers;
- bounded samples of issue details or column evidence;
- the workflow capabilities affected by the answer;
- an explicit `automatic_mutation=false` guarantee.

A question cannot be generated without a completed `DataQualityRun`.

## Question structure

Each `ClarificationQuestion` contains:

- a stable `question_key`;
- rank and priority score;
- `critical`, `high` or `medium` priority;
- category and audience;
- question text and a separate explanation of why it is needed;
- answer type;
- allowed options when applicable;
- evidence and impact payloads;
- lifecycle status.

Supported answer types are:

- `single_choice`;
- `multiple_choice`;
- `text`;
- `boolean`;
- `integer`.

Choice responses are validated against the options stored with the question. The API rejects invented option values.

## Response lifecycle

A response uses one of four resolutions:

- `answered` — a concrete answer was supplied;
- `deferred` — the question remains unresolved and the run stays open;
- `not_available` — the requested fact or material cannot be supplied;
- `not_applicable` — the question does not apply to the confirmed scope.

Responses are append-only and numbered. A later response may revise an earlier decision without deleting the history. Each question points to its latest response.

A clarification run becomes `resolved` only when it has no `open` or `deferred` questions.

## Progressive suppression

For the same source table and audience, terminally resolved question keys are remembered. A subsequent generation run:

- includes the resolution history in its SHA-256 input fingerprint;
- suppresses already answered, unavailable or not-applicable questions;
- selects the next highest-ranked unresolved candidates;
- does not suppress deferred questions.

This prevents the client from receiving the same resolved question repeatedly while preserving reproducibility.

## Idempotency

Each run stores:

- generator name and version;
- data-quality run and fingerprint;
- audience and requested limit;
- the complete candidate snapshot;
- terminal resolution history;
- a SHA-256 input fingerprint.

Repeated generation with identical inputs returns the existing run. `force=true` creates an explicit separate run. A new answer changes the resolution-history fingerprint and therefore allows the next progressive batch to be generated.

## No automatic data mutation

Clarification responses are evidence, not commands. Recording a response does not automatically:

- alter an immutable source file;
- confirm or change a column mapping;
- rewrite normalized values;
- remove duplicates;
- link a creative asset;
- calculate or replace CTR;
- enable a prediction capability.

Any resulting data or mapping change must occur through its own explicit workflow and produce a new quality assessment.

## API

```text
POST /data-quality-runs/{data_quality_run_id}/clarifications
GET  /data-quality-runs/{data_quality_run_id}/clarifications/latest

GET /clarification-runs/{run_id}
GET /clarification-runs/{run_id}/questions

POST /clarification-questions/{question_id}/responses
GET  /clarification-questions/{question_id}/responses
```

Question listing supports status filtering and pagination. Generation and response submission are written to the audit log.

## Persisted entities

```text
ClarificationRun
ClarificationQuestion
ClarificationResponse
```

Runs preserve batch-level counts and status. Questions preserve evidence and impact. Responses preserve the complete revision history.

## Explicit non-goals

CTA-PRE-007 does not:

- generate a full discovery questionnaire;
- ask questions unsupported by current data-quality evidence;
- guarantee that exactly three questions always exist;
- apply answers to mappings or normalized data automatically;
- decide final prediction availability;
- implement the quantitative synthetic survey;
- generate the client-facing XLSX/PPT/PDF report;
- define a client-specific brand-lift methodology.

Those concerns remain in later PRE-TZ stages.
