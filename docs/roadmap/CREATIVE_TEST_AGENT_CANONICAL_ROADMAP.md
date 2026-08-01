# Creative Test Agent — каноническая дорожная карта

Версия: 2.0  
Дата фиксации: 2026-07-31  
Статус документа: `canonical / single source of truth`

## Назначение

Документ фиксирует канонический порядок задач, зависимости и фактический статус Creative Test Agent. Детализированная историческая редакция v1.8 сохранена в `docs/roadmap/archive/CREATIVE_TEST_AGENT_CANONICAL_ROADMAP_v1.8_2026-07-30.md`, но не является источником текущих статусов.

Изменение v2.0 расширяет ближайшую локальную задачу `CTA-BENCH-002` до полного model-contour benchmark: LLM, VLM, OCR, hybrid и deployment topology на целевом Apple Silicon. Код задачи и её место в dependency chain не меняются.

Правила:

1. Код и каноническое имя задачи не переиспользуются.
2. Статус `DONE` ставится только после прохождения всех обязательных GitHub, local и client gates.
3. Реальные клиентские файлы, локальная БД, модели, screenshots и generated reports не коммитятся.
4. До завершения controlled pilot запрещены заявления о validated model accuracy, causal brand lift и numeric uplift prediction.
5. Реальные и synthetic evidence не объединяются скрыто.
6. Missing evidence остаётся missing.

## Статусы и контуры

Статусы: `DONE`, `PARTIAL`, `PLANNED`, `BLOCKED_CLIENT`, `BLOCKED_LOCAL`.

Контуры: `GITHUB`, `HYBRID`, `LOCAL_IDE`, `CLIENT`.

---

# Текущий рабочий контур

На 2026-07-31 собран насыщенный локальный контур клиентской демонстрации:

`intake → mapping/DQ → campaign evidence → visual extraction → traceable diagnostics → confidence/abstention → client report → finding-level review → independent review → adjudication → calibration dashboard → deterministic exports`.

Ключевые свойства:

- приложение, БД и модели могут работать только через loopback;
- визуальные findings связаны с evidence references и provenance;
- factual CG/TG outcomes показаны отдельно от диагностики;
- individual asset и campaign-set conclusions разделены;
- single review, unresolved disagreement и stale adjudication блокируют controlled release;
- экспертные оценки и adjudication append-only;
- dashboard показывает качество evidence/process, а не «точность модели»;
- JSON/XLSX/report artifacts имеют integrity metadata;
- реальные клиентские материалы остаются в локальном закрытом контуре.

Основной сценарий: `docs/demo/CLIENT_DEMO_FULL_CONTOUR_RU.md`.  
Операторский preflight: `docs/demo/CLIENT_DEMO_OPERATOR_CHECKLIST_RU.md`.

---

# Канонический реестр задач

## Блок A. Завершённый фундамент

| Порядок | Код | Каноническое имя | Статус | Контур | Зависит от |
|---:|---|---|---|---|---|
| 01 | CTA-CORE-001 | Local-First Application Foundation | `DONE` | GITHUB | — |
| 02 | CTA-DATA-001 | Deterministic Tabular Intake | `DONE` | GITHUB | CTA-CORE-001 |
| 03 | CTA-GOLD-001 | Synthetic Creative Golden Pack | `DONE` | GITHUB | CTA-DATA-001 |
| 04 | CTA-VISION-001 | Local Vision Benchmark Harness | `DONE` | GITHUB | CTA-GOLD-001 |
| 05 | CTA-PILOT-INTAKE-001 | Controlled Pilot Intake Package | `DONE` | GITHUB | CTA-DATA-001 |
| 06 | CTA-REPORT-001 | Provisional Evidence-Bound One-Page Report | `DONE` | GITHUB | CTA-PILOT-INTAKE-001 |
| 07 | CTA-OPS-001 | Operator Recovery Rehearsal | `DONE` | GITHUB | CTA-CORE-001 |
| 08 | CTA-CAL-001 | Pilot Calibration Protocol | `DONE` | GITHUB | CTA-PILOT-INTAKE-001, CTA-REPORT-001 |
| 09 | CTA-DQ-001 | Strict Data Quality Lineage Binding | `DONE` | GITHUB | CTA-DATA-001 |
| 10 | CTA-UI-001 | Unified Pilot Workspace | `DONE` | GITHUB | CTA-DATA-001, CTA-DQ-001, CTA-REPORT-001 |
| 11 | CTA-CAL-002 | Ozon Brand-Lift Diagnostic Calibration v1 | `DONE` | GITHUB | CTA-CAL-001 |

## Блок B. Клиентская демонстрация v1

| Порядок | Код | Каноническое имя | Статус | Контур | Зависит от |
|---:|---|---|---|---|---|
| 12 | CTA-VIS-002 | Unified Creative Visual Context | `DONE` | GITHUB | CTA-VISION-001, CTA-CAL-002 |
| 13 | CTA-VIS-003 | Full-Pipeline Visual Context Propagation | `DONE` | GITHUB | CTA-VIS-002 |
| 14 | CTA-VIS-004 | Visual Evidence Traceability | `DONE` | GITHUB | CTA-VIS-003 |
| 15 | CTA-VIS-005 | Visual Confidence and Abstention Policy | `DONE` | GITHUB | CTA-VIS-004 |
| 16 | CTA-OZON-001 | Ozon Showcase Data Loader | `DONE` | HYBRID | CTA-DATA-001, CTA-CAL-002 |
| 17 | CTA-OZON-002 | Ozon Campaign Evidence Workspace | `DONE` | HYBRID | CTA-OZON-001, CTA-VIS-005 |
| 18 | CTA-REPORT-002 | Evidence-Bound Client Report v2 | `DONE` | HYBRID | CTA-VIS-005, CTA-OZON-002 |
| 19 | CTA-DEMO-001 | Ozon End-to-End Client Demo | `DONE` | HYBRID | CTA-OZON-002, CTA-REPORT-002 |
| 20 | CTA-DATA-002 | Client Calibration Data Request Pack | `DONE` | GITHUB | CTA-DEMO-001 |

### Контрольная точка клиентской демонстрации

Статус: `ДОСТИГНУТА И РАСШИРЕНА` 2026-07-31.

В локальном Ozon showcase доступны campaign cards, creative previews, visual evidence, traceable findings, factual CG/TG outcomes, linkage confidence, evidence-bound Client Report v2, независимая экспертная проверка, adjudication и Calibration Quality Dashboard.

## Блок C. Экспертная калибровка

### 21. CTA-REVIEW-001 — Finding-Level Expert Review

- Статус: `DONE`
- Контур: `HYBRID`
- Результат: finding-level оценки, human-added findings, immutable system finding, UI/API/audit/exports и local usability acceptance.

### 22. CTA-REVIEW-002 — Independent Review Adjudication

- Статус: `DONE`
- Контур: `HYBRID + CLIENT`
- Зависит от: CTA-REVIEW-001
- Результат:
  - независимые append-only reviewer streams;
  - deterministic disagreement;
  - immutable basis review IDs и SHA-256 fingerprint;
  - stale-basis protection;
  - отдельная append-only adjudication;
  - Client Report v2 release boundary;
  - утверждённая operational policy v1.0.
- Утверждённые правила:
  - минимум два distinct reviewers;
  - material disagreement при различном decision, различном severity correctness или spread dimension ≥ 2;
  - adjudicator — `manager`/`admin`, отличный от basis reviewers;
  - single/incomplete review, unresolved disagreement и stale adjudication блокируют controlled release.
- Acceptance:
  - GitHub CI: PASS;
  - Mac mini/OpenCode: PASS;
  - client-process sign-off: PASS;
  - targeted tests: 29 passed;
  - migration replay: PASS;
  - no client data committed.
- Merge: PR #64, main commit `4de0c6328905318ceb5bf8d28ac26682c1117a4e`.

### 23. CTA-CAL-003 — Calibration Quality Dashboard

- Статус: `DONE`
- Контур: `HYBRID`
- Зависит от: CTA-REVIEW-002
- Реализованные метрики:
  - expert-supported finding rate;
  - actionability rate;
  - traceability rate;
  - human-added findings;
  - harmful false positives;
  - reviewer disagreement;
  - operator touch time;
  - manual action count;
  - outcome coverage.
- Результат:
  - project-scoped browser/API dashboard;
  - явные numerator, denominator, coverage, definitions и limitations;
  - `real_client`, `synthetic`, `unclassified` filters;
  - included/excluded/deferred cases;
  - resolved agreement/adjudication и видимые coverage gaps;
  - append-only workflow measurements;
  - deterministic JSON/XLSX/manifest и SHA-256 headers.
- Acceptance:
  - GitHub CI: PASS;
  - Mac mini/OpenCode: PASS;
  - targeted tests: 16 passed;
  - controlled full-suite comparison: zero introduced regressions;
  - migration/browser/API/exports/security/project isolation: PASS;
  - claim boundary: validated accuracy, causal lift, prediction, auto-thresholding и auto-model-selection = false;
  - no client data committed.
- Merge: PR #66, main commit `80c48520264247ca335632d1cb29c37f91c97885`.

---

## Блок D. Локальные модели и целевая инфраструктура

| Порядок | Код | Каноническое имя | Статус | Контур | Зависит от |
|---:|---|---|---|---|---|
| 24 | CTA-BENCH-002 | Target Hardware LLM/VLM/OCR Benchmark | `BLOCKED_LOCAL` | LOCAL_IDE | CTA-VIS-003, CTA-VISION-001 |
| 25 | CTA-MODEL-001 | Production Local Model Profile | `BLOCKED_LOCAL` | HYBRID | CTA-BENCH-002 |

### 24. CTA-BENCH-002 — ближайшая задача

На Mac mini Apple M4 Pro с 24 GB unified memory нужно сравнить текущий рабочий baseline и MLX-кандидатов для полного модельного контура:

- OCR-only, VLM-only и OCR + VLM hybrid;
- LLM analytical stages и structured output;
- существующий `Qwen2.5-VL-7B + llama.cpp` как обязательный proven baseline;
- MLX VLM 8B/4B и MLX LLM 9B/4B как challengers;
- минимум две deployment topology: единая модель и последовательная/резидентная пара VLM + LLM;
- extraction/analysis quality, schema compliance, evidence references, hallucination, abstention, repeatability;
- cold/warm wall-clock, first non-empty token, single-request, concurrency=2, load/unload;
- CPU/GPU/RAM, memory pressure/swap и корректное освобождение model processes.

Результатом становится выбранный воспроизводимый профиль для demo/pilot, разные профили по сценариям либо документированное отсутствие приемлемого кандидата. MLX не считается победителем заранее; он должен доказать преимущество относительно уже принятого llama.cpp contour.

Полное локальное ТЗ: `docs/local/CTA-BENCH-002_MAC_MINI_OPENCODE.md`.

### 25. CTA-MODEL-001 — следующий dependency gate

После benchmark фиксируется воспроизводимый production local model profile: OCR engine, VLM, LLM, runtime/server, quantization, context size, timeout, concurrency, fallback, image limits, load/unload policy, deployment topology и измеренные resource requirements.

---

## Блок E. Controlled pilot

| Порядок | Код | Каноническое имя | Статус | Контур | Зависит от |
|---:|---|---|---|---|---|
| 26 | CTA-PILOT-002 | Real Case Intake and Data Quality Gate | `BLOCKED_CLIENT` | CLIENT + HYBRID | CTA-DATA-002, CTA-CAL-003, CTA-MODEL-001 |
| 27 | CTA-PILOT-003 | Frozen Blind Diagnostic Run | `BLOCKED_CLIENT` | HYBRID | CTA-PILOT-002 |
| 28 | CTA-PILOT-004 | Independent Expert Review Execution | `BLOCKED_CLIENT` | CLIENT | CTA-PILOT-003, CTA-REVIEW-002 |
| 29 | CTA-PILOT-005 | Provenance-Bound Outcome Linkage | `BLOCKED_CLIENT` | HYBRID | CTA-PILOT-003 |
| 30 | CTA-PILOT-006 | Controlled Pilot Calibration Summary | `PLANNED` | GITHUB + HYBRID | CTA-PILOT-004, CTA-PILOT-005 |

Pilot boundary:

- 15–20 clean real cases;
- frozen diagnostic before outcomes are disclosed;
- two independent reviewers where possible;
- omissions as human-added findings;
- disagreements adjudicated or explicitly pending;
- provenance-bound outcome linkage;
- no causal interpretation or validated-accuracy claim.

---

## Блок F. Методология v2 и пороги

| Порядок | Код | Каноническое имя | Статус | Контур | Зависит от |
|---:|---|---|---|---|---|
| 31 | CTA-METH-001 | Agent Error Taxonomy | `PLANNED` | GITHUB + HYBRID | CTA-PILOT-006 |
| 32 | CTA-METH-002 | Diagnostic Methodology v2 | `PLANNED` | GITHUB + CLIENT | CTA-METH-001 |
| 33 | CTA-METH-003 | Decision Threshold Sign-Off | `BLOCKED_CLIENT` | CLIENT | CTA-METH-002 |

---

## Блок G. On-premise pilot release

| Порядок | Код | Каноническое имя | Статус | Контур | Зависит от |
|---:|---|---|---|---|---|
| 34 | CTA-DEPLOY-001 | Client On-Premise Installation | `BLOCKED_LOCAL` | LOCAL_IDE | CTA-MODEL-001, CTA-METH-002 |
| 35 | CTA-SEC-001 | Isolation, Audit and Recovery Acceptance | `BLOCKED_LOCAL` | LOCAL_IDE + CLIENT | CTA-DEPLOY-001, CTA-OPS-001 |
| 36 | CTA-RELEASE-001 | Controlled Pilot Release Candidate | `PLANNED` | HYBRID | CTA-SEC-001, CTA-METH-003 |

Release candidate должен включать release bundle, manifest, SBOM/dependencies, config templates, model profile, operator guide, rollback guide и acceptance report.

---

# Отложенные ветки

До CTA-RELEASE-001 не входят в ближайший канонический путь:

- video/storyboard analysis;
- automatic media-plan recommendations;
- advertising-cabinet integrations;
- predictive uplift model;
- automatic winning-creative selection;
- SaaS multi-tenant edition;
- SSO/MFA enterprise extension;
- масштабная brand memory/RAG;
- synthetic focus groups как отдельный продукт.

# Следующая задача

К реализации первой запускается:

`CTA-BENCH-002 — Target Hardware LLM/VLM/OCR Benchmark`.

Контур: `LOCAL_IDE`. Для выполнения требуется OpenCode на Mac mini M4 Pro 24 GB/целевом железе.
