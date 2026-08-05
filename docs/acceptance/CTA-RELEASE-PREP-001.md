# CTA-RELEASE-PREP-001 — Acceptance Record

Issue: #83  
Execution mode: `GITHUB + HYBRID`  
Evidence class: synthetic only

## Goal

Подготовить client-independent on-premise release skeleton: детерминированный пакет, SBOM, frozen model reference, fail-closed configuration, чистая установка, backup/rollback/upgrade и операторская документация.

## GitHub implementation

- deterministic ZIP builder with fixed archive metadata and sorted payload;
- versioned `release-manifest.json` with per-file SHA-256 and source revision;
- CycloneDX 1.5 SBOM and dependency export;
- frozen CTA-MODEL-001 profile binding by file and internal integrity hashes;
- explicit exclusion of client data, secrets, local paths, caches and model weights;
- fail-closed `.env.onprem.example` validator;
- bundle checksum and path-traversal/symlink protection;
- clean-machine installer with migrations, closed-loop, health and rollback rehearsal;
- targeted tests and GitHub Actions workflow;
- Russian operator/troubleshooting/upgrade/rollback runbook;
- Mac mini/OpenCode acceptance specification.

## Automated invariants

- same source revision produces byte-identical ZIP archives;
- every payload file is recorded in the manifest and `SHA256SUMS`;
- SBOM contains application declared dependencies and exact frozen runtime pins where available;
- frozen model profile file SHA-256 and internal profile SHA-256 match the accepted contract;
- model weights are referenced by identity/revision/hash but never included;
- environment template binds to loopback, requires auth, disables cloud LLM and enables fail-closed security;
- secret-like tokens, private keys, user-home paths, databases and model-weight extensions fail validation;
- clean installation uses a new venv and synthetic state only;
- rollback rehearsal proves backup → mutation → restore → original value.

## GitHub acceptance evidence

Status: `PASS` on the implementation head below.

```text
implementation head: 282d05b29269f3418d8ce9fa31ee72d81ce32b73
targeted workflow run: https://github.com/arutyunoveth/creative-test-agent/actions/runs/30956143421 (PASS)
baseline CI run: https://github.com/arutyunoveth/creative-test-agent/actions/runs/30956143451 (PASS)
bundle sha256: a8a293f141b588ede501929b8ea8d571a92c3a878fdca2f333e2d24e74336869
archive files: 566
payload file count: 562
SBOM component count: 22
targeted tests: 5 passed
clean synthetic install: PASS
backup/mutate/restore/verify rollback rehearsal: PASS
```

The acceptance-record commit itself is evidence-only. The attested artifact above is the immutable artifact uploaded by the recorded workflow run; rebuilding with another source revision intentionally produces a different manifest and archive SHA-256.

## Local Mac mini acceptance

Status: `PASS`.

Host: Apple Silicon (arm64), M-series (24 GB), macOS (Darwin) 26.6; CPython 3.11.15. Evidence is synthetic-only; executed from the unzipped release ZIP and the frozen model profile.

```text
local acceptance commit: 79770aba8c6407b3e5b108572713f532df04c308
final local bundle sha256: cef39d6255f305e8d84b2266190ff91791ebd01f203d43d83be2adf169d3dad7
payload file count: 563
SBOM component count: 22
regression tests (targeted): 14 passed
frozen runtime: PASS — vision mlx-community/Qwen3-VL-4B-Instruct-4bit (127.0.0.1:8091),
                llm mlx-community/Qwen3.5-4B-MLX-4bit (127.0.0.1:8093), identity match,
                profile file sha256 6d7781ab…ce6a1a, internal sha256 7796913472bb9de1…
                c107aab473c9698, cloud fallback false
release-bundle E2E: PASS — bootstrap-admin login, synthetic creative upload + vision
                analysis via frozen VLM, test run scored via frozen LLM (avg 6.9/10, revise),
                report/project-history readable, full restart preserves data
degraded path: PASS — LLM endpoint stopped ⇒ request fails closed
                ("Cannot connect to the local OpenAI-compatible server …"), no cloud fallback;
                endpoint restored ⇒ status HEALTHY, run succeeds
clean install: PASS (17 steps, fresh venv + synthetic state only)
rollback rehearsal: PASS
shutdown residual processes: 0 — single stop call releases ports 8091/8093,
                PID files removed, application port released
no client data / secrets / model weights / absolute paths in evidence
```

## Decision

Current verdict: `GO`.

Packaging, deterministic build, clean installation, rollback, frozen runtime and end-to-end local acceptance all pass on commit `79770ab`. This attests the controlled client-independent release artifact only; it does not authorize installation in client infrastructure, which remains `CTA-DEPLOY-001`.

## Claim boundary

This task establishes packaging and operational reproducibility. It does not establish validated model accuracy, causal brand lift, numeric uplift prediction, production SLA, public deployment readiness or completion of a real client pilot.
