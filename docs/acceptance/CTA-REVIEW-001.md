# CTA-REVIEW-001 — Acceptance

Status: `DONE`  
Implementation mode: `HYBRID`  
GitHub implementation completed: 2026-07-30

## Delivered in repository

- append-only `FindingReview` model and Alembic migration;
- immutable system-finding JSON snapshot and SHA-256 on every review revision;
- six canonical decisions, including separate human omissions;
- project-scoped service and API;
- campaign/report workflow browser UI without UUID or JSON entry;
- audit events and stale-snapshot protection;
- dedicated evidence JSON and deterministic calibration ZIP;
- synthetic fixtures, regression tests and CI gate;
- operator documentation and Mac mini/OpenCode acceptance specification.

## Automated acceptance

- [x] A system finding can be listed and opened by project/campaign context.
- [x] Review writes create revisions and never replace earlier rows.
- [x] ORM update/delete attempts are rejected.
- [x] The system snapshot hash is validated before save.
- [x] `missed_by_system` creates a human finding without a system snapshot.
- [x] Cross-project finding/review access is rejected.
- [x] Evidence JSON retains all revisions and claim boundaries.
- [x] Calibration ZIP contains review CSV, evidence JSON and SHA-256 manifest.
- [x] Existing client report v2 can consume the latest persisted system reviews.
- [x] No client files are committed.

## Local acceptance still required

The task becomes `DONE` only after the browser/usability checklist in
`docs/local/CTA-REVIEW-001_MAC_MINI_OPENCODE.md` is completed on the Mac mini with a real or approved synthetic project and a sanitized result is recorded.

## Explicit non-acceptance

This task does not provide multi-reviewer adjudication, validated accuracy, causal creative lift, automatic threshold tuning or a calibration dashboard.
