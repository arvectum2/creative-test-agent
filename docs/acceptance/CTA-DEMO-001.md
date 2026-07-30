# CTA-DEMO-001 — Acceptance

Status: `BLOCKED_LOCAL`  
Implementation mode: `HYBRID`  
GitHub implementation completed: 2026-07-30

## Delivered

- typed, project-scoped Ozon demo state;
- deterministic default selection of the strongest demonstrable contrast case;
- browser and JSON routes for the canonical seven-step path;
- original creative preview with linkage status and confidence;
- canonical visual extraction surface with observation-level confidence, provenance and reference IDs;
- separate asset-level diagnostics and campaign-level CG/TG outcomes;
- report-v2 generation from the demo UI and integrity-checked artifact downloads;
- operator prompts, stop conditions and evidence-boundary reminders;
- synthetic E2E acceptance harness, deterministic bundle and dedicated CI workflow;
- real-project Mac mini/OpenCode smoke-test specification.

## GitHub acceptance checks

- [x] Seven canonical steps are represented in fixed order.
- [x] No manual UUID or JSON entry is required in the browser flow.
- [x] Visual extraction is rebuilt from the canonical `VisualEvidenceEnvelope` and does not infer missing fields.
- [x] Every populated visual observation shows confidence, provenance and visual reference IDs.
- [x] Diagnostics remain asset-level model outputs.
- [x] CG/TG remains campaign-level factual evidence.
- [x] Report v2 is generated through the existing evidence-bound pipeline.
- [x] HTML, PPTX, DOCX, evidence JSON, XLSX and manifest downloads retain SHA-256 integrity checks.
- [x] Synthetic E2E tests and deterministic bundle run in CI.
- [x] No real client file is committed or uploaded as a CI artifact.

## Remaining local acceptance

- [ ] Run the browser path against the real Ozon showcase project on the Mac mini.
- [ ] Verify at least one real contrast case has preview, visual extraction, completed diagnostic and CG/TG outcomes.
- [ ] Verify multi-asset, rejected-link and missing-data cases remain visibly limited.
- [ ] Generate report v2 and open all required formats locally.
- [ ] Confirm local-only posture and absence of external API traffic.
- [ ] Post a sanitized smoke-test summary to issue #52.

## Explicit non-acceptance

The synthetic E2E bundle does not prove model accuracy, causal brand lift, prediction quality or production readiness. `DONE` is prohibited until the real-data local smoke test is recorded.
