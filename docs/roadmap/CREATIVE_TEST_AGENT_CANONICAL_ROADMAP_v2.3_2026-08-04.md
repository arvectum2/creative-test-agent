# Creative Test Agent — каноническая дорожная карта

Версия: 2.3  
Дата фиксации: 2026-08-04  
Статус: `canonical / single source of truth`

Эта редакция заменяет v2.2 как источник текущих статусов и порядка. v2.2 остаётся исторической записью. Изменение v2.3 закрывает `CTA-PILOT-PREP-001 — Controlled Pilot Intake Orchestration` после merge PR #88 и переводит Waiting-for-Data Lane к `CTA-PILOT-PREP-002 — Frozen Blind Run Infrastructure`.

## 1. Правила

1. Постоянный идентификатор имеет вид `CTA-<DOMAIN>-<NNN>` и не переиспользуется.
2. Номер GitHub issue или PR не является task ID.
3. `DONE` ставится только после всех обязательных GitHub, local и client gates.
4. Клиентские файлы, локальная БД, модели, screenshots и generated reports не коммитятся.
5. Missing evidence остаётся missing.
6. `probable` и `uncertain` linkage не повышаются до `exact` без прямого evidence.
7. Counts не восстанавливаются из rounded rates.
8. До controlled pilot запрещены заявления о validated model accuracy, causal brand lift и numeric uplift prediction.
9. Waiting-for-Data Lane не заменяет реальный controlled pilot и не считается его завершением.

Статусы: `DONE`, `PLANNED`, `IN_PROGRESS`, `BLOCKED_CLIENT`, `BLOCKED_LOCAL`.  
Контуры: `GITHUB`, `HYBRID`, `LOCAL_IDE`, `CLIENT`.

## 2. Сводка состояния

| Этап | Диапазон | Выполнено | Статус | Результат |
|---|---:|---:|---|---|
| A. Фундамент | 01–11 | 11/11 | `DONE` | Приложение, intake, DQ, workspace, отчётность и calibration foundation готовы. |
| B. Клиентская демонстрация v1 | 12–20 | 9/9 | `DONE` | Полный локальный Ozon demo-contour и Client Report v2 приняты. |
| C. Экспертная калибровка | 21–23 | 3/3 | `DONE` | Finding review, independent adjudication и calibration dashboard готовы. |
| D. Локальные модели | 24–25 | 2/2 | `DONE` | Benchmark и frozen production profile приняты на Mac mini M4 Pro / 24 GB. |
| E. Controlled pilot | 26–30 | 0/5 | `BLOCKED_CLIENT` | Нужны 15–20 реальных кейсов, outcomes и эксперты заказчика. |
| F. Методология v2 | 31–33 | 0/3 | `PLANNED` | Выполняется только на evidence controlled pilot. |
| G. On-premise release | 34–36 | 0/3 | `BLOCKED_LOCAL/CLIENT` | Нужны инфраструктура клиента, ИБ-приёмка и release candidate. |
| W. Параллельная подготовка | W01–W07 | 3/7 | `ACTIVE` | Structural debt, runtime shutdown и pilot-intake orchestration завершены. |

Функциональный demo-MVP: `100%`.  
Техническая готовность к controlled pilot: высокая; входной gate заблокирован клиентским dataset.  
Валидированный продукт: не завершён до этапов E–F.

## 3. Основной канонический путь

### Блок A — фундамент

| № | Код | Каноническое имя | Статус | Контур |
|---:|---|---|---|---|
| 01 | CTA-CORE-001 | Local-First Application Foundation | `DONE` | GITHUB |
| 02 | CTA-DATA-001 | Deterministic Tabular Intake | `DONE` | GITHUB |
| 03 | CTA-GOLD-001 | Synthetic Creative Golden Pack | `DONE` | GITHUB |
| 04 | CTA-VISION-001 | Local Vision Benchmark Harness | `DONE` | GITHUB |
| 05 | CTA-PILOT-INTAKE-001 | Controlled Pilot Intake Package | `DONE` | GITHUB |
| 06 | CTA-REPORT-001 | Provisional Evidence-Bound One-Page Report | `DONE` | GITHUB |
| 07 | CTA-OPS-001 | Operator Recovery Rehearsal | `DONE` | GITHUB |
| 08 | CTA-CAL-001 | Pilot Calibration Protocol | `DONE` | GITHUB |
| 09 | CTA-DQ-001 | Strict Data Quality Lineage Binding | `DONE` | GITHUB |
| 10 | CTA-UI-001 | Unified Pilot Workspace | `DONE` | GITHUB |
| 11 | CTA-CAL-002 | Ozon Brand-Lift Diagnostic Calibration v1 | `DONE` | GITHUB |

### Блок B — клиентская демонстрация v1

| № | Код | Каноническое имя | Статус | Контур |
|---:|---|---|---|---|
| 12 | CTA-VIS-002 | Unified Creative Visual Context | `DONE` | GITHUB |
| 13 | CTA-VIS-003 | Full-Pipeline Visual Context Propagation | `DONE` | GITHUB |
| 14 | CTA-VIS-004 | Visual Evidence Traceability | `DONE` | GITHUB |
| 15 | CTA-VIS-005 | Visual Confidence and Abstention Policy | `DONE` | GITHUB |
| 16 | CTA-OZON-001 | Ozon Showcase Data Loader | `DONE` | HYBRID |
| 17 | CTA-OZON-002 | Ozon Campaign Evidence Workspace | `DONE` | HYBRID |
| 18 | CTA-REPORT-002 | Evidence-Bound Client Report v2 | `DONE` | HYBRID |
| 19 | CTA-DEMO-001 | Ozon End-to-End Client Demo | `DONE` | HYBRID |
| 20 | CTA-DATA-002 | Client Calibration Data Request Pack | `DONE` | GITHUB |

### Блок C — экспертная калибровка

| № | Код | Каноническое имя | Статус | Контур |
|---:|---|---|---|---|
| 21 | CTA-REVIEW-001 | Finding-Level Expert Review | `DONE` | HYBRID |
| 22 | CTA-REVIEW-002 | Independent Review Adjudication | `DONE` | HYBRID + CLIENT |
| 23 | CTA-CAL-003 | Calibration Quality Dashboard | `DONE` | HYBRID |

### Блок D — локальные модели

| № | Код | Каноническое имя | Статус | Контур |
|---:|---|---|---|---|
| 24 | CTA-BENCH-002 | Target Hardware LLM/VLM/OCR Benchmark | `DONE` | LOCAL_IDE |
| 25 | CTA-MODEL-001 | Production Local Model Profile | `DONE` | HYBRID + LOCAL_IDE |

Актуальный runtime-контракт:

- VLM: `mlx-community/Qwen3-VL-4B-Instruct-4bit`, loopback `127.0.0.1:8091`;
- LLM: `mlx-community/Qwen3.5-4B-MLX-4bit`, loopback `127.0.0.1:8093`;
- exact dependency pins: `mlx-openai-server==1.3.12`, `mlx-lm==0.31.3`;
- Tesseract 5.5.3 `rus+eng` как manual fallback;
- cloud fallback disabled;
- timeout 240 s, max concurrency 2;
- exact model identity gate и fail-closed structured-output policy.

### Блок E — controlled pilot

| № | Код | Каноническое имя | Статус | Контур | Зависит от |
|---:|---|---|---|---|---|
| 26 | CTA-PILOT-002 | Real Case Intake and Data Quality Gate | `BLOCKED_CLIENT` | CLIENT + HYBRID | CTA-DATA-002, CTA-CAL-003, CTA-MODEL-001 |
| 27 | CTA-PILOT-003 | Frozen Blind Diagnostic Run | `BLOCKED_CLIENT` | HYBRID | CTA-PILOT-002 |
| 28 | CTA-PILOT-004 | Independent Expert Review Execution | `BLOCKED_CLIENT` | CLIENT | CTA-PILOT-003, CTA-REVIEW-002 |
| 29 | CTA-PILOT-005 | Provenance-Bound Outcome Linkage | `BLOCKED_CLIENT` | HYBRID | CTA-PILOT-003 |
| 30 | CTA-PILOT-006 | Controlled Pilot Calibration Summary | `PLANNED` | GITHUB + HYBRID | CTA-PILOT-004, CTA-PILOT-005 |

Pilot boundary:

- 15–20 clean real cases;
- system output замораживается до раскрытия outcomes;
- два независимых reviewer, где возможно;
- omissions фиксируются как human-added findings;
- disagreements adjudicated или explicitly pending;
- outcome linkage provenance-bound;
- causal interpretation и accuracy claims запрещены.

### Блок F — методология v2

| № | Код | Каноническое имя | Статус | Контур |
|---:|---|---|---|---|
| 31 | CTA-METH-001 | Agent Error Taxonomy | `PLANNED` | GITHUB + HYBRID |
| 32 | CTA-METH-002 | Diagnostic Methodology v2 | `PLANNED` | GITHUB + CLIENT |
| 33 | CTA-METH-003 | Decision Threshold Sign-Off | `BLOCKED_CLIENT` | CLIENT |

### Блок G — on-premise pilot release

| № | Код | Каноническое имя | Статус | Контур |
|---:|---|---|---|---|
| 34 | CTA-DEPLOY-001 | Client On-Premise Installation | `BLOCKED_LOCAL` | LOCAL_IDE |
| 35 | CTA-SEC-001 | Isolation, Audit and Recovery Acceptance | `BLOCKED_LOCAL` | LOCAL_IDE + CLIENT |
| 36 | CTA-RELEASE-001 | Controlled Pilot Release Candidate | `PLANNED` | HYBRID |

## 4. Waiting-for-Data Lane

Эта очередь выполняется, пока `CTA-PILOT-002` заблокирована клиентскими данными. После поступления dataset основной controlled-pilot path получает приоритет.

| Приоритет | Код | Каноническое имя | Статус | Контур | Что даёт |
|---:|---|---|---|---|---|
| W01 | CTA-ARCH-001 | Structural Technical Debt Elimination | `DONE` | GITHUB | Декомпозиция монолитов, app factory/lifespan, нулевой exception budget и structural CI gate. |
| W02 | CTA-RUNTIME-002 | Graceful Shutdown Completion | `DONE` | HYBRID | Один `stop` ждёт полный grace period и корректно завершает MLX runtime. |
| W03 | CTA-PILOT-PREP-001 | Controlled Pilot Intake Orchestration | `DONE` | GITHUB | Case register, immutable provenance, append-only decisions, DQ summary/export и project-scoped UI/API. |
| W04 | CTA-PILOT-PREP-002 | Frozen Blind Run Infrastructure | `PLANNED` | GITHUB | Immutable output hash, prompt/model versions, outcome-access separation и replay protection. |
| W05 | CTA-PILOT-PREP-003 | Synthetic Controlled Pilot Rehearsal | `PLANNED` | HYBRID | Полная репетиция intake → blind run → two-reviewer adjudication → dashboard → summary. |
| W06 | CTA-RELEASE-PREP-001 | On-Premise Release Skeleton | `PLANNED` | GITHUB + HYBRID | Release manifest, SBOM, env/config templates, rollback и install verification. |
| W07 | CTA-CLIENT-001 | Controlled Pilot Launch Pack | `PLANNED` | GITHUB | Kickoff agenda, RACI, handoff checklist, reviewer guide, sign-off forms и escalation matrix. |

### W01 — CTA-ARCH-001 acceptance

Завершено PR #79 / main commit `27e479110a1b8dcb03e44d2781ed2292b5d0f638`:

- known structural debt budget устранён;
- max Python module 700 lines, max function 300 lines;
- tracked module/function exceptions пусты;
- FastAPI app factory и lifespan startup;
- structural code-health gate включён в CI;
- full regression: 1055 passed, 6 skipped, no pytest warnings.

### W02 — CTA-RUNTIME-002 acceptance

Завершено PR #86 и close-out PR #87 / main `51048c4e02051d29c240954cd1165fd20113980f`:

- normal asynchronous shutdown завершается одним `stop`;
- полный grace period соблюдается;
- force-kill применяется только после timeout;
- ports 8091/8093 свободны;
- PID files удаляются после exit;
- residual process count = 0;
- synthetic delayed-shutdown regression 5/5 PASS;
- real MLX lifecycle 3/3 PASS; warm/delayed lifecycle PASS.

### W03 — CTA-PILOT-PREP-001 acceptance

Завершено PR #88 / main commit `d6128280bfab45b83ba414a069baf4811e7e355e`:

- project-scoped controlled-pilot case register;
- статусы `included`, `excluded`, `deferred`, `needs_clarification`;
- immutable source/import provenance и canonical package SHA-256;
- append-only decision history и запрет direct state mutation;
- orchestration over completed import sessions, mapping coverage и Data Quality runs;
- deterministic project DQ summary и JSON export с SHA-256 header;
- project-scoped API и browser UI;
- synthetic valid, invalid, rate-only, missing-linkage и multi-asset fixtures;
- non-exact linkage не повышается до `exact`;
- impressions/clicks не восстанавливаются из rounded rates; missing counts остаются `null`;
- cross-project isolation и non-disclosing not-found behavior;
- targeted workflow run #3 PASS, full CI run #420 PASS;
- client data и local models не использовались;
- `CTA-PILOT-002` остаётся `BLOCKED_CLIENT`.

### W04 — CTA-PILOT-PREP-002 acceptance

Для перевода в `DONE` требуется:

- immutable frozen diagnostic revision с SHA-256;
- model profile, prompt hashes, code revision и input provenance;
- outcome fields недоступны diagnostic execution role до freeze;
- rerun создаёт новую append-only revision, а не заменяет frozen output;
- synthetic leakage и replay tests проходят CI;
- audit и deterministic export сохраняют все versions/hashes.

### W05 — CTA-PILOT-PREP-003 acceptance

- минимум 6 synthetic cases: normal, missing, conflicting, multi-asset, rate-only, harmful false positive;
- два независимых reviewer stream;
- material disagreement и adjudication;
- calibration dashboard и Pilot Calibration Summary;
- полный runbook, timing и manual-action measurements;
- ни один показатель не называется validated accuracy.

### W06 — CTA-RELEASE-PREP-001 acceptance

- versioned release manifest и SBOM/dependency export;
- frozen model profile reference и integrity hashes без model weights;
- fail-closed env/config templates;
- clean-machine synthetic install verification;
- rollback, backup/restore и upgrade instructions;
- actual client installation остаётся `CTA-DEPLOY-001`.

### W07 — CTA-CLIENT-001 acceptance

- kickoff agenda и RACI;
- data handoff checklist, inclusion/exclusion rules;
- reviewer/adjudicator guide;
- blind-run boundary, sign-off forms и escalation matrix;
- client-facing forbidden-claims section;
- deterministic client-facing package без embedded client data.

## 5. Что нужно от заказчика

Для запуска `CTA-PILOT-002`:

- 15–20 реальных кейсов;
- `campaign_id`, `creative_id` / `asset_id`;
- оригинальные creative files;
- platform, placement, format и observation window;
- audience segment и campaign goal;
- questionnaire/version и exact metric definitions;
- CG/TG sample counts и positive counts, где применимо;
- observed outcomes и units;
- linkage notes, weights, quotas и post-stratification;
- назначенные reviewers, adjudicator, data owner и methodology owner.

Основной формат передачи: пакет `CTA-DATA-002`.

## 6. Порядок реализации

Пока ждём данные:

```text
CTA-PILOT-PREP-002
→ CTA-PILOT-PREP-003
→ CTA-RELEASE-PREP-001
→ CTA-CLIENT-001
```

После поступления dataset:

```text
CTA-PILOT-002
→ CTA-PILOT-003
→ CTA-PILOT-004 + CTA-PILOT-005
→ CTA-PILOT-006
→ CTA-METH-001
→ CTA-METH-002
→ CTA-METH-003
→ CTA-DEPLOY-001
→ CTA-SEC-001
→ CTA-RELEASE-001
```

## 7. Следующая задача

`CTA-PILOT-PREP-002 — Frozen Blind Run Infrastructure` — issue #81, контур `GITHUB`.
