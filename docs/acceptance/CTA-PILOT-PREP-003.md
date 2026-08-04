# CTA-PILOT-PREP-003 — Synthetic Controlled Pilot Rehearsal

Issue: #82  
Execution mode: `HYBRID`  
Evidence class: synthetic only

## Goal

Rehearse the complete controlled-pilot workflow before client materials arrive:

`intake/DQ → frozen blind diagnostic → outcome reveal → two independent reviews → disagreement/adjudication → calibration dashboard → pilot summary`.

This acceptance record belongs to the waiting-for-data task `CTA-PILOT-PREP-003`. It does not complete real `CTA-PILOT-002` or `CTA-PILOT-003`.

## Frozen synthetic matrix

The versioned fixture contains six mandatory scenarios:

| Case | Scenario | Intake state | Expected boundary |
|---|---|---|---|
| `SYN-NORMAL-001` | normal | included | blind run, outcome reveal after freeze, reviewer agreement |
| `SYN-MISSING-001` | missing | needs_clarification | missing linkage and metrics remain missing; no blind run |
| `SYN-CONFLICT-001` | conflicting | included | material disagreement, adjudication, separate human omission |
| `SYN-MULTI-ASSET-002` | multi_asset | included | probable linkage stays non-exact; campaign-set outcome only |
| `SYN-RATE-ONLY-002` | rate_only | deferred | counts remain null and are not reconstructed from the rate |
| `SYN-HFP-001` | harmful_false_positive | included | explicit harmful-false-positive adjudication |

## GitHub implementation

- deterministic case-matrix validator and pilot-summary builder;
- executable full-contour synthetic harness over the existing production services;
- project-scoped intake and DQ registration;
- immutable frozen diagnostic revisions and pre-freeze outcome barrier;
- two independent append-only reviewer streams;
- material disagreement and third-party adjudication;
- separate human-added omission without fabricated system finding;
- synthetic calibration classification and explicit workflow measurements;
- deterministic intake, blind-run, review-package, dashboard JSON/XLSX and pilot-summary artifacts;
- dedicated CI workflow and sanitized short-lived workflow artifact;
- operator runbook and Mac mini/OpenCode acceptance specification.

## Automated acceptance invariants

- exactly six required scenarios complete through the intended branch of the workflow;
- four included cases receive frozen blind diagnostic revisions;
- outcome plaintext is unavailable before freeze and absent from diagnostic revision exports;
- missing values remain missing;
- the rate-only case retains `impressions=null` and `clicks=null`;
- probable multi-asset linkage is never promoted to exact;
- two material disagreements are adjudicated;
- exactly one harmful false positive and one human-added omission are captured;
- explicit workflow totals are 2,940 seconds wall clock, 1,260 seconds operator touch and 34 manual actions;
- every export is byte-identical on repeated generation from the same state;
- no metric is described as validated model accuracy;
- no real client file, identifier, outcome, screenshot, local database, model weight or runtime log is committed.

## GitHub acceptance evidence

Accepted branch revision before this evidence-only update:

```text
5b24aebbcfa0eb6799780eb0262379f55e8d4bab
```

GitHub Actions results on that revision:

- `CTA-PILOT-PREP-003`, run `#4`, run ID `30945198760`: **PASS**;
- repository baseline `CI`, run `#432`, run ID `30945198656`: **PASS**;
- Python: `3.11.15`;
- SQLAlchemy model registry: PASS;
- Alembic revision: `l1m2n3o4p5q6`, up to date;
- targeted full synthetic harness and `tests/test_cta_pilot_prep_003.py`: PASS.

Sanitized workflow artifact:

```text
name   = cta-pilot-prep-003-synthetic-evidence
id     = 8906784813
sha256 = a82107b66282557e04bf5a019d4f6810a1cb38aa5e5c128fbee0eadec79e922d
```

Recorded deterministic export hashes:

```text
pilot-intake.json             d701561fe050c361314978a25a08416b1c2ab7907f87560a2b8079fb6c8a2d26
blind-runs.json                be06180d2e756fecf05e2d69198e2a0d908f36e800888121384629583434c16c
independent-review.zip         b759071a94aa2a7b9bc863aca7aee09fc4a9ae8b785068c6f602292f0f87540f
calibration-dashboard.json     d2550807379f7991db6f2f5775e7a12f6652b1d97911f2d16d5771d8c668949a
calibration-dashboard.xlsx     62651bebbdbab423cc5f5e9919fda50e2b3723c1f473c1e7246ac88366c10963
pilot-summary.json             55d58872b00728c705ffb3e1f9fd33c61841116dab1a9169889e759ef06bb9ff
```

Observed synthetic summary:

```text
cases                         6
frozen blind-run cases        4
outcomes revealed after freeze 4
adjudicated disagreements     2
harmful false positives       1
human-added omissions         1
wall clock seconds             2940
operator touch seconds         1260
manual actions                 34
```

Claim-boundary flags remained false for validated model accuracy, causal brand lift, numeric uplift prediction, real-client evidence inclusion, missing-value inference, count reconstruction from rounded rates and non-exact-to-exact linkage promotion.

## Local Mac mini browser/production-model gate

Executed per `docs/local/CTA-PILOT-PREP-003_MAC_MINI_OPENCODE.md` from a clean
worktree (no stash/WIP):

```text
worktree head   4e81a57eacfa411fd8b3ae0b738861d3c0a12dd0
os              macOS (Apple Silicon), Mac mini M4 Pro 24 GB
app python      3.14.6  (fastapi 0.141.1, sqlalchemy 2.0.51, pytest 9.1.1)
model profile   cta_model_001.mac_mini_m4pro_24gb.frozen.json
profile sha256  7796913472bb9de1f789c7a7ebaa0a0fab096c48f46e32580c107aab473c9698
model endpoints loopback only 127.0.0.1:8091 (VLM) and 127.0.0.1:8093 (LLM)
```

Gate results (all PASS):

- Stub gate: migrations, model registry (33/33), fixture validation
  (`validated 6 synthetic cases`), full-contour runtime harness and
  `tests/test_cta_pilot_prep_003.py` (2 passed).
- Frozen model gate: `validate --mode frozen`, `start`, `preflight --require-runtime`
  and `status` HEALTHY with exact model identity and loopback-only endpoints.
- Browser rehearsal: 107 checks PASS, 0 FAIL across all seven scenarios
  (intake/DQ; frozen blind diagnostics for the four included cases driven by
  real frozen-VLM diagnostic runs, including N+1 rerun and execution replay
  block; two independent declared reviewers `Pilot Rehearsal Reviewer A/B` and
  a third declared `Pilot Rehearsal Adjudicator` identity; adjudication + stale
  round; human omission; dashboard/exports; browser usability and cross-project
  isolation). App served on loopback port 8001.
- Shutdown: single `cta_model_001.py stop` call; vision and llm stopped
  gracefully (no force kill), pid files removed, ports 8001/8091/8093 free,
  zero residual CTA processes.

Sanitized local evidence bundle (uncommitted):

```text
artifacts/local-acceptance/CTA-PILOT-PREP-003/20260804T211920Z/
```

Local export hashes (byte-identical on repeat):

```text
pilot-intake export.json        977f72bad7075b3706cee09da270c6c191c62bdecd58688898a358d29cec5aee
blind-runs export.json           0d85e1c2b9dd7c5f4b43b8f63fafc82c44a3c38c020ddfd7a56281846b25916f
finding-reviews evidence.json    25c163ba6602cedb904e2889118643b9fb8734396e619e85c148985803a1d2c4
calibration-package.zip          d52e9385a69654135482aba89fa3a9804c74e789a641b10fa84344d0d991637a
calibration-dashboard export.json
                                 6e2922f44e44a92cfd96c9029565b57e09bfc5ed4317f6d25f92b98b7bfff794
calibration-dashboard export.xlsx
                                 8378bece315672d1f4d960a2054cfecead774329fddcf1587a1c8ddd7fdecfad
```

## Status

- GitHub implementation and synthetic CI gate: **PASS**.
- Mac mini browser/production-model rehearsal: **PASS** (107/107 checks).
- Final task status: **DONE once green GitHub CI is confirmed on the acceptance revision**.
- Real client-data tasks `CTA-PILOT-002` and `CTA-PILOT-003`: **remain blocked on client data**.

## Claim boundary

The rehearsal proves workflow integration and guardrail behavior on synthetic fixtures. It does not establish validated model accuracy, causal brand lift, numeric uplift prediction, real-pilot completion or methodology v2 validation.
