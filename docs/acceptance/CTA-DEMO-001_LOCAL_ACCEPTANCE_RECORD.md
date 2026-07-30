# CTA-DEMO-001 — Local Acceptance Record

Date: 2026-07-30  
Status: `PASS`  
Scope: sanitized operator record; no client binaries or raw model output

## Runtime

- local multimodal model: `Qwen2.5-VL-7B`;
- serving runtime: llama.cpp with matching multimodal projector;
- API style: OpenAI-compatible `/v1/chat/completions`;
- bind address: `127.0.0.1:8083`;
- image transport: base64 data URL;
- cloud fallback: disabled;
- external calls during client-data processing: none observed.

The previously installed Gemma model was rejected by the multimodal gate because it was text-only. It was not used to fabricate visual evidence.

## Real contrast case

- case: `OZON-007`;
- original preview: PASS;
- real visual extraction: PASS;
- detected evidence included product text, layout observations and visual risks;
- completed diagnostic: PASS;
- diagnostic findings: 8;
- proposed/final recommendation: `revise`;
- effective recommendation: `abstain`;
- factual CG/TG remained campaign-level and separate from asset-level diagnostics.

## Report and tests

- Report v2 generated for 9 campaigns;
- report contained 24 findings;
- previous artifact-family integrity and deterministic-download checks remained PASS;
- targeted and regression checks: 29/29 PASS;
- client files, reports, screenshots, model files and the local database were not committed.

## Evidence boundaries

- causal interpretation remains forbidden;
- individual-asset outcome attribution remains forbidden;
- missing values are not inferred;
- diagnostics remain model outputs rather than factual outcomes;
- completion does not assert validated model accuracy or production readiness.
