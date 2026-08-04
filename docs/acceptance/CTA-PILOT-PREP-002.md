# CTA-PILOT-PREP-002 — Frozen Blind Run Infrastructure

Status: `ACCEPTED`  
Execution mode: `GITHUB`  
Issue: `#81`  
Implementation head: `b6b3590ae20968d681fae9715f42ba41a8c2977b`

## Scope

This acceptance record covers the client-independent frozen blind-run infrastructure only.
All executable evidence uses synthetic fixtures. No client material, real outcome, local model
weight, runtime log, screenshot or generated client report is part of this task.

## Implemented contract

- each diagnostic execution is persisted as an immutable frozen revision;
- the revision binds canonical SHA-256 hashes for diagnostic output, input provenance,
  prompt manifest, model-profile snapshot, execution metadata and the complete revision manifest;
- prompt IDs resolve through the prompt registry and preserve prompt stage, version and template hash;
- the model-profile ID resolves through the model-profile registry and preserves the selected
  provider/model/configuration snapshot;
- the code revision is stored as an exact 40- or 64-character hexadecimal revision hash;
- reruns are append-only and form a hash-linked revision chain;
- an execution identifier is single-use per project/case and replay attempts fail closed;
- outcome plaintext is held in a separate immutable envelope;
- the diagnostic `analyst` role cannot access outcome metadata or plaintext;
- outcome custodians (`admin`, `manager`) cannot reveal plaintext before a diagnostic revision is frozen;
- diagnostic request schemas reject unknown fields, while diagnostic output, execution metadata and resolved prompt/model/input snapshots reject reserved outcome keys;
- input provenance binds the immutable pilot package while excluding reported metrics, plaintext case provenance and outcome fields;
- project-scoped APIs return non-disclosing not-found responses for cross-project access;
- audit events contain hashes and identifiers only, never outcome plaintext;
- deterministic diagnostic export preserves every diagnostic version/hash and excludes outcome plaintext.

## Acceptance matrix

| Gate | Expected | Status |
|---|---|---|
| Frozen revision update/delete | rejected by ORM guards | PASS |
| Same execution ID replay | HTTP 409; no new revision | PASS |
| Legitimate rerun | new `N+1` revision; previous row unchanged | PASS |
| Revision hash chain | previous hash and supersession link preserved | PASS |
| Prompt/model/code/input provenance | all snapshots and hashes exported | PASS |
| Outcome plaintext before freeze | rejected | PASS |
| Outcome access by `analyst` | rejected before and after freeze | PASS |
| Outcome field in diagnostic request/metadata | rejected | PASS |
| Cross-project access | non-disclosing 404 | PASS |
| Deterministic export | identical bytes and SHA-256 header | PASS |
| Model registry and Alembic chain | clean at `l1m2n3o4p5q6` | PASS |
| Dedicated synthetic workflow | run #1; 3 tests passed | PASS |
| Full repository CI | run #424 | PASS |

## Evidence

- dedicated `CTA-PILOT-PREP-002` workflow run `30939143622`: PASS;
- targeted synthetic acceptance: `3 passed in 2.70s`;
- SQLAlchemy model registry: `33/33`, PASS;
- Alembic head/database revision: `l1m2n3o4p5q6`, PASS;
- full repository `CI` run `30939142993` / run #424: PASS;
- related CTA-PILOT-PREP-001, CTA-REVIEW-001, CTA-REVIEW-002 and CTA-CAL-003 workflows: PASS.

## Claim boundary

This task does not complete `CTA-PILOT-002`, `CTA-PILOT-003` or a real controlled pilot.
It does not establish validated model accuracy, causal brand lift or numeric uplift prediction.
The full synthetic controlled-pilot rehearsal remains `CTA-PILOT-PREP-003`.
