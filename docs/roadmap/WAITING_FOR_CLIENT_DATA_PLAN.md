# Waiting for client data — execution plan

Source: canonical roadmap v2.3, 2026-08-04.

## Order

1. `CTA-RUNTIME-002` — graceful shutdown completion — **DONE** (issue #78, close-out main `51048c4`).
2. `CTA-PILOT-PREP-001` — controlled-pilot intake orchestration — **DONE** (issue #80, PR #88, main `d612828`).
3. `CTA-PILOT-PREP-002` — implement immutable blind-run freeze and leakage barriers — **NEXT**.
4. `CTA-PILOT-PREP-003` — rehearse the complete controlled pilot on synthetic cases.
5. `CTA-RELEASE-PREP-001` — prepare release manifest, SBOM, install validation and rollback skeleton.
6. `CTA-CLIENT-001` — produce the client launch, reviewer and sign-off pack.

## Execution modes

| Task | Browser/GitHub | OpenCode/Codex | Client input |
|---|---|---|---|
| CTA-RUNTIME-002 | implementation, tests, CI — **DONE** | Mac mini lifecycle acceptance — **DONE** | no |
| CTA-PILOT-PREP-001 | implementation, migrations, API/UI, fixtures, CI — **DONE** | not required | no |
| CTA-PILOT-PREP-002 | complete implementation and synthetic acceptance | optional local role-boundary smoke | no |
| CTA-PILOT-PREP-003 | fixtures, harness, tests, docs | full local model/browser rehearsal | no |
| CTA-RELEASE-PREP-001 | manifest, SBOM, templates, validators | clean-machine install rehearsal | no |
| CTA-CLIENT-001 | complete package and deterministic exports | visual check of office artifacts if used | methodology sign-off later |

## Completed CTA-PILOT-PREP-001 boundary

The completed pre-client intake layer provides:

- project-scoped case register;
- `included`, `excluded`, `deferred`, `needs_clarification` states;
- immutable import/source provenance and canonical package SHA-256;
- append-only decision history;
- deterministic DQ summary and JSON export;
- project-scoped API/UI;
- synthetic valid, invalid, rate-only, missing-linkage and multi-asset coverage;
- no promotion of non-exact linkage to `exact`;
- no reconstruction of counts from rounded rates.

It does not complete `CTA-PILOT-002`: real client cases and local real-data acceptance are still required.

## Stop condition

When the approved client dataset arrives, unfinished waiting-lane work is re-prioritized. The primary path resumes at `CTA-PILOT-002`. No waiting-lane deliverable may be used to claim that a real controlled pilot or validated model accuracy has been completed.