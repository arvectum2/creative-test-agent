# Waiting for client data — execution plan

Source: canonical roadmap v2.4, 2026-08-04.

## Order

1. `CTA-RUNTIME-002` — graceful shutdown completion — **DONE** (issue #78, close-out main `51048c4`).
2. `CTA-PILOT-PREP-001` — controlled-pilot intake orchestration — **DONE** (issue #80, PR #88, main `d612828`).
3. `CTA-PILOT-PREP-002` — immutable blind-run freeze and leakage barriers — **DONE** (issue #81, PR #90, main `5ce1de3`).
4. `CTA-PILOT-PREP-003` — rehearse the complete controlled pilot on synthetic cases — **NEXT**.
5. `CTA-RELEASE-PREP-001` — prepare release manifest, SBOM, install validation and rollback skeleton.
6. `CTA-CLIENT-001` — produce the client launch, reviewer and sign-off pack.

## Execution modes

| Task | Browser/GitHub | OpenCode/Codex | Client input |
|---|---|---|---|
| CTA-RUNTIME-002 | implementation, tests, CI — **DONE** | Mac mini lifecycle acceptance — **DONE** | no |
| CTA-PILOT-PREP-001 | implementation, migrations, API/UI, fixtures, CI — **DONE** | not required | no |
| CTA-PILOT-PREP-002 | implementation, migration, leakage/replay tests, CI — **DONE** | not required | no |
| CTA-PILOT-PREP-003 | fixtures, harness, tests, docs | full local model/browser rehearsal — **REQUIRED** | no |
| CTA-RELEASE-PREP-001 | manifest, SBOM, templates, validators | clean-machine install rehearsal | no |
| CTA-CLIENT-001 | complete package and deterministic exports | visual check of office artifacts if used | methodology sign-off later |

## Completed CTA-PILOT-PREP-002 boundary

The completed pre-client blind-run layer provides:

- project/case-scoped immutable diagnostic revisions;
- canonical SHA-256 binding for output, input provenance, prompt/model snapshots, execution metadata and revision manifest;
- hash-linked append-only reruns and execution-ID replay protection;
- separated immutable outcome envelope;
- no outcome access for the diagnostic `analyst` role;
- no outcome plaintext reveal before a diagnostic freeze;
- fail-closed outcome-key leakage checks;
- deterministic diagnostic export and hash-only audit events;
- synthetic leakage, replay, immutability and cross-project acceptance;
- clean migration head `l1m2n3o4p5q6` and model registry `33/33`.

It does not complete `CTA-PILOT-002`: real client cases, actual outcomes and local real-data acceptance are still required.

## Stop condition

When the approved client dataset arrives, unfinished waiting-lane work is re-prioritized. The primary path resumes at `CTA-PILOT-002`. No waiting-lane deliverable may be used to claim that a real controlled pilot or validated model accuracy has been completed.
