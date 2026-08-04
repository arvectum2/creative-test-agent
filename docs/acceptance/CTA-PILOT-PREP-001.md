# CTA-PILOT-PREP-001 — Controlled Pilot Intake Orchestration

Status: `GITHUB ACCEPTED / PR READY`  
Issue: `#80`  
Pull request: `#88`  
Execution mode: `GITHUB`  
Dependency: `CTA-RUNTIME-002 — DONE`  
Real pilot dependency: `CTA-PILOT-002 — BLOCKED_CLIENT`

## Scope

- project-scoped controlled-pilot case register;
- states `included`, `excluded`, `deferred`, `needs_clarification`;
- immutable source-file SHA-256 and canonical package provenance;
- append-only state-decision history;
- orchestration over completed import sessions, persisted mapping coverage and Data Quality runs;
- deterministic project DQ summary and JSON export;
- project-scoped API and browser UI;
- synthetic valid, invalid, rate-only, missing-linkage and multi-asset fixtures.

## Safety invariants

- non-exact source linkage cannot be promoted to `exact`;
- `probable` and `uncertain` remain non-exact in persistence, API, summaries and exports;
- missing counts remain `null`;
- rounded rates never reconstruct impressions or clicks;
- source provenance fields cannot be updated and cases cannot be deleted;
- decision rows cannot be updated or deleted;
- every nested case read/write is filtered by `project_id`;
- no client files or identifiers are committed;
- completion of this task does not complete `CTA-PILOT-002`.

## API

- `POST /pilot-intake/projects/{project_id}/cases`
- `GET /pilot-intake/projects/{project_id}/cases`
- `GET /pilot-intake/projects/{project_id}/cases/{case_id}`
- `POST /pilot-intake/projects/{project_id}/cases/{case_id}/decisions`
- `GET /pilot-intake/projects/{project_id}/cases/{case_id}/history`
- `GET /pilot-intake/projects/{project_id}/data-quality-summary`
- `GET /pilot-intake/projects/{project_id}/export.json`
- `GET /ui/projects/{project_id}/pilot-intake`

## Acceptance evidence

Accepted on implementation head `9379fc21c00df45a583f88225677439c92522cee`:

- [x] targeted `tests/test_pilot_intake_register.py` PASS — `CTA-PILOT-PREP-001` run `#2`;
- [x] SQLAlchemy runtime/Alembic registry parity PASS;
- [x] clean migration to head PASS;
- [x] full repository CI PASS — `CI` run `#419`;
- [x] deterministic export verified byte-for-byte;
- [x] append-only and immutable-provenance regression tests PASS;
- [x] cross-project isolation PASS;
- [x] no client data committed;
- [x] issue and PR remain explicit that `CTA-PILOT-002` is not complete.

The roadmap defines browser smoke as optional. The synthetic acceptance test exercises the project-scoped UI route after the PR exists; no Mac mini/model/runtime acceptance is required for this GitHub-only task.
