# CTA-DEMO-001 — Acceptance

Status: `BLOCKED_VLM`  
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

- [x] Run the browser path against the real Ozon showcase project on the Mac mini.
- [ ] Verify at least one real contrast case has preview, visual extraction, completed diagnostic and CG/TG outcomes.
- [x] Verify multi-asset, rejected-link and missing-data cases remain visibly limited.
- [x] Generate report v2 and open all required formats locally.
- [x] Confirm local-only posture and absence of external API traffic.
- [x] Post a sanitized smoke-test summary to issue #52.

## Local smoke-test outcome (2026-07-30)

**Verdict: Smoke infrastructure: PASS / Full CTA-DEMO-001 acceptance: BLOCKED_VLM**

The pipeline was executed end-to-end against the real Ozon showcase project (`75fed771-...`):

- Report v2 generated (ID: `rpt2-c8f72f2c...`) with 6 verified artifacts (HTML, PPTXs, DOCX, evidence JSON, XLSX)
- Evidence boundaries correctly separate individual_asset diagnostics from campaign_set outcomes
- No causal interpretation, numeric uplift, or individual attribution — all correctly rejected
- No cloud API traffic detected; all requests from loopback only
- SHA-256 integrity verified for all artifacts; repeated download deterministic
- Demo UI correctly shows all 9 campaigns as `limited` with documented reasons
- Limitations section in report documents 17 items (multi_asset, missing_diagnostics, rejected_asset_link, etc.)
- Expert review: all 8 findings `not_reviewed` (fabricated=false)

**Known blockers preventing full DONE:**
1. Stub vision provider — no real visual extraction; visual criteria show "not assessed"
2. No completed diagnostic on the default contrast case (OZON-007)
3. Only OZON-005 has completed diagnostics (non-contrast case)

These are environment limitations, not pipeline defects. Full acceptance requires a configured local VLM or cloud provider for visual extraction.

## Explicit non-acceptance

The synthetic E2E bundle does not prove model accuracy, causal brand lift, prediction quality or production readiness. `DONE` is prohibited until the real-data local smoke test is recorded.
