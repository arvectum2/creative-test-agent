# Waiting for client data — execution plan

Source: canonical roadmap v2.2, 2026-08-04.

## Order

1. `CTA-RUNTIME-002` — fix graceful shutdown false negative.
2. `CTA-PILOT-PREP-001` — implement synthetic controlled-pilot intake orchestration.
3. `CTA-PILOT-PREP-002` — implement immutable blind-run freeze and leakage barriers.
4. `CTA-PILOT-PREP-003` — rehearse the complete controlled pilot on synthetic cases.
5. `CTA-RELEASE-PREP-001` — prepare release manifest, SBOM, install validation and rollback skeleton.
6. `CTA-CLIENT-001` — produce the client launch, reviewer and sign-off pack.

## Execution modes

| Task | Browser/GitHub | OpenCode/Codex | Client input |
|---|---|---|---|
| CTA-RUNTIME-002 | implementation, tests, CI | final Mac mini lifecycle acceptance | no |
| CTA-PILOT-PREP-001 | complete implementation and synthetic acceptance | optional browser smoke | no |
| CTA-PILOT-PREP-002 | complete implementation and synthetic acceptance | optional local role-boundary smoke | no |
| CTA-PILOT-PREP-003 | fixtures, harness, tests, docs | full local model/browser rehearsal | no |
| CTA-RELEASE-PREP-001 | manifest, SBOM, templates, validators | clean-machine install rehearsal | no |
| CTA-CLIENT-001 | complete package and deterministic exports | visual check of office artifacts if used | methodology sign-off later |

## Stop condition

When the approved client dataset arrives, unfinished waiting-lane work is re-prioritized. The primary path resumes at `CTA-PILOT-002`. No waiting-lane deliverable may be used to claim that a real controlled pilot has been completed.