# CTA-MODEL-001 Acceptance Record

- Task: `CTA-MODEL-001` — freeze production model profile `cta-model-001-mac-mini-m4pro-24gb` (VLM-MLX-4B + LLM-MLX-4B, TOPOLOGY-U unified path) and run local application-path acceptance.
- Verdict: **PASS** (profile freeze + application-path acceptance on the Mac mini M4 Pro / 24 GB host).
- Claim boundary: no validated production accuracy, no causal brand-lift, no numeric-uplift prediction, no cloud fallback, no client data committed (`claim_boundary` in the frozen profile).

## Commits

- Base (main): `bd3bf6e2e166f38e9024b66a3aa8bb144be4fcc2`
- Branch (feat/cta-model-001): `7f598f41f474d87a6ce5cef355ec8179ca08aea4` (pre-freeze HEAD; this record accompanies the freeze commit)
- Benchmark commit: `5277bba602d1844d94a072a40f1053e2ee592474`

## Benchmark source of truth

- Benchmark: `cta-bench-002-target-hardware-llm-vlm-ocr` `1.0.0`
- Artifact revision: `20260801-091536` (run_records: 211, candidate_count: 11)
- Integrity manifest SHA-256: `dbf635a3bbc190ced05868acb18d3168eed8df50554a3c4f305c687f83075ddc`

## Frozen profile

- File: `config/model_profiles/production/cta_model_001.mac_mini_m4pro_24gb.frozen.json`
- File SHA-256: `6d7781ab249219dd8bbd93abd71dd96aac7fa094eb84f02aa1e861b8cfce6a1a`
- Internal integrity self-hash (`integrity.profile_sha256`): `7796913472bb9de1f789c7a7ebaa0a0fab096c48f46e32580c107aab473c9698`

## Hardware / OS

- Platform: `darwin-arm64`, Mac model `Mac16,11`
- Machine: Mac mini, Apple M4 Pro, 24 GB unified memory (25,769,803,776 bytes)
- macOS `26.6` (build `25G72`), Darwin `25.6.0` arm64

## Runtimes

| Role | Server | Python | Packages | Model |
|---|---|---|---|---|
| Vision | `mlx_vlm.server` (port 8091) | 3.14.6 | mlx 0.32.0, mlx-vlm 0.6.8 | `mlx-community/Qwen3-VL-4B-Instruct-4bit` (4bit) |
| LLM | `app.cli launch` (port 8093) | 3.11.15 | mlx 0.32.0, mlx-openai-server 1.3.12, mlx-lm 0.31.3 | `mlx-community/Qwen3.5-4B-MLX-4bit` (4bit) |

Runtimes are owned by dedicated Python environments referenced via `CTA_VLM_PYTHON` / `CTA_LLM_PYTHON` (not committed). Tesseract `5.5.3` with `rus`,`eng`; language-data aggregate SHA-256 `4f6059e4a09c1a6b4cfb196e1d1ba5f079579aee303b150014bf6350d49a678e`.

## Model identity

| Field | Vision (VLM-MLX-4B) | LLM (LLM-MLX-4B) |
|---|---|---|
| MLflow candidate | `VLM-MLX-4B` | `LLM-MLX-4B` |
| Model ID | `mlx-community/Qwen3-VL-4B-Instruct-4bit` | `mlx-community/Qwen3.5-4B-MLX-4bit` |
| Quantization | 4bit | 4bit |
| Source revision | `2fd8dacbdb8f1e54b8c005f081ec5bf79c56376b` | `32f3e8ecf65426fc3306969496342d504bfa13f3` |
| Local dir SHA-256 | `5febfeb53f098b178fef3e85e9ff1f931e5f61d147ba3917894da857b58715c8` | `e639fca7a46120db434dd9c0c5ead867ccccbe7b849eea543a9423b2cf36c18f` |
| Disk bytes | 3,109,732,071 | 3,061,132,920 |

Identity gate: `/v1/models` plus `/health` `loaded_model` must equal the frozen model ID (exact match, no alias/autodetect). Verified via CLI `status` / `preflight --require-runtime` (`identity_match=true` for both components).

## Endpoints

- Vision: `http://127.0.0.1:8091` — `/v1/models`, `/v1/chat/completions`
- LLM: `http://127.0.0.1:8093/v1` — `/v1/models`, `/v1/chat/completions`
- App: uvicorn `src.main:app` on `127.0.0.1` (port 8001 used for this acceptance because an unrelated process held 8000)
- All loopback-only; no external endpoints.

## Topology / reconciliation

- Benchmark label: `TOPOLOGY-U` (unified analytical data flow).
- Operational mode: `dual_server_resident` (both servers resident simultaneously; TOPOLOGY-R co-residency allowed, `resident_headroom_fraction 0.564`, no swap thrash, graceful shutdown, `residual=[]`).
- Vision server (8091) performs visual extraction; LLM server (8093) performs the analytical structured-output stages on the VLM-extracted text.
- Sequential/manual fallback only if memory/swap exceeds the frozen envelope or model identity drifts; then load vision first, stop both before unloading.

## Limits / generation / timeouts / concurrency

- Vision: context tokens 262,144; max_output_tokens 2048; max_images_per_request 1; max_image_bytes 15,728,640 (15 MiB); max_image_pixels 4,194,304; temperature 0.0; seed 42; policy `json_only_validate_fail_closed`.
- LLM: context tokens 262,144; max_output_tokens 4096; temperature 0.2; policy `json_extract_repair_validate_fallback`.
- Application: `local_only_mode=true`, `allow_cloud_llm=false`, `request_timeout_seconds=240`, `max_concurrency=2`.
- Image byte/pixel guard enforced fail-closed in the VLM analyzer before any request (`CTA_VISION_MAX_IMAGE_BYTES` / `CTA_VISION_MAX_IMAGE_PIXELS`).

## Measured envelope

- cold_start_seconds: 6.1 (both servers ready with exact identity, parallel launch)
- warm_p50_seconds / warm_p90_seconds / warm_max_seconds: 39.5 / 39.6 / 39.6 (representative full request: vision stage ~7.0 s, LLM analytical stage ~27–32 s incl. reasoning)
- peak_rss_bytes: 3,365,158,912 (largest resident model process; VLM ~2,963 MB, LLM ~3,286 MB)
- peak_memory_pressure: `normal` (system free 61–79 % during replay)
- swap_used_bytes: 1,294,267,843 (1,234.31 MiB; unchanged during replay)
- disk_footprint_bytes: 6,170,864,991 (both model directories)
- concurrency_1_pass: true; concurrency_2_pass: true (no cross-request contamination)
- shutdown_residual_processes: 0

Fixed benchmark constants (unchanged, not re-fit to profile): `visual_text_f1=0.731`, `visual_p95_seconds=5.2`, `structured_schema_valid_rate=0.941`, `end_to_end_wall_seconds=101.5`, `resident_headroom_fraction=0.564`.

## Three-case application E2E

Real `OpenAiCompatibleVlmAnalyzer` → 6 analytical LLM stages → evidence-bound findings → Client Report v2 → deterministic export, on synthetic CTA-BENCH-002 case-pack evidence only.

| Case | Vision | Pipeline | Findings | Report/Export |
|---|---|---|---|---|
| E2E-001 normal | local_vlm, wall 8.6 s, warnings `[]`, text extracted (`NOVALEN Support for everyday routines…`) | completed, final `revise` (conf 0.2932) | evidence `limited`, decision `abstained`, abstention 4, review_required 0 | generated, validation_errors `[]`, export sha `6ae12995…` |
| E2E-002 missing/unreadable (blank) | local_vlm, wall 1.2 s, `detected_text=""` (missing preserved) | completed | evidence `limited`, `abstained`, abstention 6 | generated, validation_errors `[]`, export sha `d551c2e6…` |
| E2E-003 conflicting/unsupported | local_vlm, text extracted | completed | evidence `limited`, `abstained`, abstention 2 (unsupported claims not published) | generated, validation_errors `[]`, export sha `d8349937…` |

- Canonical `VisionResult` / evidence envelope: present for all cases; model metadata exact; provider `local_vlm`.
- Schema-valid or explicit fail-closed fallback: satisfied — invalid/insufficient evidence abstains (`visual_decision_status=abstained`, evidence `limited`); no invalid output published.
- Report/export: Client Report v2 generated for all 3 cases with no validation errors; deterministic exports produced; on-disk bundles validated with no SHA mismatches (6 artifacts each).
- No real client assets used.

## Health / runtime lifecycle

- `render-env` PASS, `check-env` PASS; `start` → `STARTED`; `status` → `HEALTHY`; `preflight --require-runtime` → PASS (identity_match=true).
- `/health`, `/llm/health`, `/vision/health` on the app: all PASS (`local_only_mode=true`).
- Cache/warm replay: cold start, warm-up (unscored), representative single request (39.5 s), concurrency=2 (both independent requests completed, no cross-contamination), full E2E normal case, shutdown.

## Process cleanup

- CLI `stop` → `STOPPED`; PID files removed; 0 residual model processes; ports 8091/8093 free; memory pressure returned toward baseline.

## Targeted / full suite

- Targeted suite (doc section 12): `test_cta_model_001_profile.py`, `test_model_profiles_openai_compatible_local.py`, `test_openai_compatible_local_provider.py`, `test_vlm_analyzer_normalization.py`, `test_pipeline_structured_recovery.py` — **48 passed**.
- `python -m compileall` PASS; `scripts/check_model_registry.py` PASS; frozen `validate --mode frozen` PASS.
- Full suite: 7 pre-existing failures, **identical** between clean `origin/main` (`bd3bf6e`) and this branch under the same isolated environment (no `.env`, fresh data, same venv):
  - `tests/test_backup_restore_scripts.py::test_backup_creates_zip`
  - `tests/test_prompt_registry.py::{test_list_empty, test_get_active_prompt_not_active}`
  - `tests/test_users_admin_api.py::{test_create_user, test_get_user, test_update_user, test_deactivate_user}`
- Controlled comparison: no new failures introduced by the branch. (A gitignored local `.env` setting `CTA_VISION_PROVIDER=local_vlm` additionally breaks the stub-default vision tests; this affects base and branch identically and is an environment artifact, not a code regression.)

## No-client-data confirmation

- Evidence used in this acceptance is synthetic CTA-BENCH-002 case-pack/blank content only. No real client assets, client names/IDs/content, prompts/model outputs with client data, tokens/API keys, home paths, or cache paths are committed. Absolute home paths (Python envs) are referenced only via env vars in the local `.local/` (gitignored) artifacts and are not committed.

## Claim boundary confirmation

- `validated_model_accuracy=false`, `causal_brand_lift=false`, `numeric_uplift_prediction=false`, `cloud_fallback=false`, `client_data_committed=false`. This acceptance is a hardware/runtime/profile freeze plus local application-path integration check, not a validated production-accuracy claim.
