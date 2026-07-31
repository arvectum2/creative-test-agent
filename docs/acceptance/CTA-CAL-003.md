# CTA-CAL-003 — Calibration Quality Dashboard acceptance

Дата фиксации: 2026-07-31  
Каноническая задача: `CTA-CAL-003`  
Итоговый статус: `DONE`

## Результат

Calibration Quality Dashboard реализован и принят в GitHub и локальном Mac mini/OpenCode контуре. Dashboard объединяет expert review, adjudication, human-added findings, workflow measurements и outcome coverage без claims о validated model accuracy или causal creative lift.

## GitHub acceptance

- [x] project-scoped typed dashboard service;
- [x] все девять канонических метрик;
- [x] value/null, numerator, denominator, coverage, evidence status, definition, interpretation и limitations;
- [x] real/synthetic/unclassified evidence separation;
- [x] included/excluded/deferred case state;
- [x] resolved consensus/adjudication semantics;
- [x] unresolved, stale и insufficient-review coverage остаётся видимым;
- [x] explicit append-only operator-touch/manual-action measurements;
- [x] validation `operator_touch_seconds <= wall_clock_seconds`;
- [x] descriptive campaign-level outcome coverage без causal attribution;
- [x] project API and browser workflow;
- [x] deterministic JSON/XLSX exports and SHA-256 manifest;
- [x] audit events and cross-project filtering;
- [x] Alembic migration and model-registry registration;
- [x] synthetic tests and dedicated CI;
- [x] no real client files committed.

## Local acceptance — Mac mini / OpenCode

- [x] migration replay на копии DB;
- [x] browser layout и навигация;
- [x] case classification и evidence filters;
- [x] append-only workflow measurements;
- [x] review/adjudication coverage semantics;
- [x] JSON/XLSX/manifest downloads;
- [x] SHA-256 и deterministic bytes;
- [x] real/synthetic separation;
- [x] project isolation A/B;
- [x] loopback-only и отсутствие внешнего трафика;
- [x] security headers;
- [x] no client-data commit.

Локальный результат: **PASS**.

- Targeted tests: **16 passed**.
- Controlled full-suite comparison on fresh DB: identical **23 failed / 969 passed / 6 skipped** for pristine and fixed states; introduced regressions: **0**.
- Migration replay: **PASS**.
- Browser/API/exports/security/project isolation: **PASS**.

## Defect fixed during acceptance

Commit `5277bba602d1844d94a072a40f1053e2ee592474` устранил XLSX byte nondeterminism. `docProps/core.xml` timestamps `dcterms:created` и `dcterms:modified` нормализуются в `1970-01-01T00:00:00Z`; regression test проверяет нормализованное значение и падает на предыдущей реализации.

## Mandatory claims boundary

Ни UI, ни API, ни XLSX/JSON не называют метрики validated model accuracy, proven market effectiveness, causal creative lift, numeric uplift prediction или regulatory/medical approval.

Dashboard всегда фиксирует:

- `validated_model_accuracy_claimed=false`;
- `causal_interpretation_allowed=false`;
- `numeric_uplift_prediction_generated=false`;
- `automatic_threshold_tuning_performed=false`;
- `automatic_model_selection_performed=false`;
- `missing_evidence_inferred=false`;
- `real_and_synthetic_evidence_merged=false`.

`expert_supported_finding_rate` описывается только как observed expert support в выбранном calibration evidence set.

## Dependency

CTA-REVIEW-002 прошла GitHub, local и client-process acceptance и должна быть доступна в `main` до merge CTA-CAL-003.

## Итог

Все acceptance gates CTA-CAL-003 пройдены. После доступности dependency в target branch PR может быть retargeted на `main`, повторно проверен CI и merged.
