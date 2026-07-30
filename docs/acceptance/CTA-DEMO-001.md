# CTA-DEMO-001 — Acceptance

Status: `DONE`  
Implementation mode: `HYBRID`  
GitHub implementation completed: 2026-07-30  
Local real-data acceptance completed: 2026-07-30

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
- local OpenAI-compatible vision adapter for llama.cpp with loopback enforcement and base64 image transport;
- real-project Mac mini/OpenCode acceptance procedure and sanitized result recording.

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
- [x] llama.cpp OpenAI-compatible adapter accepts only loopback endpoints and has no cloud fallback.

## Local acceptance checks

- [x] Run the browser path against the real Ozon showcase project on the Mac mini.
- [x] Verify at least one real contrast case has preview, visual extraction, completed diagnostic and CG/TG outcomes.
- [x] Verify multi-asset, rejected-link and missing-data cases remain visibly limited.
- [x] Generate report v2 and open the required formats locally.
- [x] Confirm local-only posture and absence of external API traffic.
- [x] Post a sanitized smoke-test summary to issue #52.

## Final local acceptance outcome (2026-07-30)

**Verdict: PASS**

The final acceptance rerun used the real Ozon contrast case `OZON-007` and the merged local vision path:

- the installed Gemma model was correctly rejected at the multimodal gate because it was text-only;
- the already cached `Qwen2.5-VL-7B` model was used through llama.cpp with a matching multimodal projector;
- llama.cpp served the OpenAI-compatible API on `127.0.0.1:8083`;
- images were transmitted as base64 data URLs, without file paths or remote image URLs;
- real visual extraction identified product text, layout observations and visual risks for the accepted OZON-007 asset;
- the completed diagnostic produced 8 findings, with `final_recommendation=revise` and `effective_recommendation=abstain`;
- factual CG/TG outcomes remained campaign-level and separate from individual-asset diagnostics;
- Report v2 was generated for 9 campaigns and contained 24 findings;
- all 29 targeted and regression checks passed;
- application and model traffic remained loopback-only, with no external API calls observed;
- no client binaries, reports, screenshots, model files or local database files were committed.

## Evidence boundaries retained

- `causal_interpretation_allowed=false`;
- `individual_asset_outcome_attribution_allowed=false`;
- diagnostics remain model outputs rather than factual campaign outcomes;
- missing values are not inferred;
- descriptive CG/TG deltas are not presented as causal uplift;
- the effective recommendation may abstain even when the proposed recommendation is `revise`.

## Non-claims

Completion of this task proves reproducibility of the local evidence-bound demonstration path. It does not prove validated model accuracy, causal brand lift, numeric uplift prediction quality or production readiness.
