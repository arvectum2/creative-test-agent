# Creative Test Agent — читаемый статус дорожной карты

Дата среза: 2026-07-30  
Канонический источник: `docs/roadmap/CREATIVE_TEST_AGENT_CANONICAL_ROADMAP.md`, версия 1.8.

## 1. Правило идентификаторов

Начиная с `ROADMAP-001`, единственными постоянными идентификаторами являются доменные коды вида:

```text
CTA-<DOMAIN>-<NNN>
```

Примеры: `CTA-OZON-001`, `CTA-REPORT-002`, `CTA-REVIEW-001`.

Старые последовательные коды вида `CTA-001`, `CTA-017` использовались в рабочих чатах и ранних issue/PR до фиксации канонической дорожной карты. Они считаются **legacy aliases**, не переиспользуются и не определяют порядок реализации.

GitHub-номер `#59` — это номер issue/PR и не является task ID.

Для новых работ обязательно использовать канонический ID. В текстах старый ID можно указывать только как alias:

```text
CTA-VIS-002 (legacy CTA-017)
```

## 2. Сводка по этапам

| Этап | Блок | Диапазон задач | Выполнено | Статус | Что это означает |
|---|---|---:|---:|---|---|
| 1 | A. Фундамент | 01–11 | 11/11 | DONE | Базовое приложение, intake, DQ, workspace, отчёты, calibration foundation готовы. |
| 2 | B. Клиентская демонстрация v1 | 12–20 | 9/9 | DONE | Функциональный demo-MVP завершён и принят на реальном Ozon-кейсе. |
| 3 | C. Экспертная калибровка | 21–23 | 0/3 | NEXT | Нужно встроить экспертную проверку, adjudication и dashboard. |
| 4 | D. Локальные модели | 24–25 | 0/2 | BLOCKED_LOCAL | Нужен OpenCode/Codex на целевом железе для benchmark и production profile. |
| 5 | E. Controlled pilot | 26–30 | 0/5 | BLOCKED_CLIENT | Нужны 15–20 реальных кейсов и участие экспертов заказчика. |
| 6 | F. Методология v2 | 31–33 | 0/3 | PLANNED | Выполняется по результатам controlled pilot. |
| 7 | G. On-premise release | 34–36 | 0/3 | BLOCKED_LOCAL/CLIENT | Требуются установка у клиента, ИБ-приёмка и release bundle. |

## 3. Полный порядок реализации

### Этап 1 — фундамент

| № | Канонический ID | Задача | Статус | Контур |
|---:|---|---|---|---|
| 01 | CTA-CORE-001 | Local-First Application Foundation | DONE | GITHUB |
| 02 | CTA-DATA-001 | Deterministic Tabular Intake | DONE | GITHUB |
| 03 | CTA-GOLD-001 | Synthetic Creative Golden Pack | DONE | GITHUB |
| 04 | CTA-VISION-001 | Local Vision Benchmark Harness | DONE | GITHUB |
| 05 | CTA-PILOT-INTAKE-001 | Controlled Pilot Intake Package | DONE | GITHUB |
| 06 | CTA-REPORT-001 | Provisional Evidence-Bound One-Page Report | DONE | GITHUB |
| 07 | CTA-OPS-001 | Operator Recovery Rehearsal | DONE | GITHUB |
| 08 | CTA-CAL-001 | Pilot Calibration Protocol | DONE | GITHUB |
| 09 | CTA-DQ-001 | Strict Data Quality Lineage Binding | DONE | GITHUB |
| 10 | CTA-UI-001 | Unified Pilot Workspace | DONE | GITHUB |
| 11 | CTA-CAL-002 | Ozon Brand-Lift Diagnostic Calibration v1 | DONE | GITHUB |

### Этап 2 — клиентская демонстрация v1

| № | Канонический ID | Задача | Статус | Контур |
|---:|---|---|---|---|
| 12 | CTA-VIS-002 | Unified Creative Visual Context | DONE | GITHUB |
| 13 | CTA-VIS-003 | Full-Pipeline Visual Context Propagation | DONE | GITHUB |
| 14 | CTA-VIS-004 | Visual Evidence Traceability | DONE | GITHUB |
| 15 | CTA-VIS-005 | Visual Confidence and Abstention Policy | DONE | GITHUB |
| 16 | CTA-OZON-001 | Ozon Showcase Data Loader | DONE | HYBRID |
| 17 | CTA-OZON-002 | Ozon Campaign Evidence Workspace | DONE | HYBRID |
| 18 | CTA-REPORT-002 | Evidence-Bound Client Report v2 | DONE | HYBRID |
| 19 | CTA-DEMO-001 | Ozon End-to-End Client Demo | DONE | HYBRID |
| 20 | CTA-DATA-002 | Client Calibration Data Request Pack | DONE | GITHUB |

Контрольная точка этапа достигнута 2026-07-30: реальный browser path пройден на Mac mini с Qwen2.5-VL-7B через llama.cpp; отчёт v2 и evidence boundaries проверены; клиентские файлы не коммитились.

### Этап 3 — экспертная калибровка

| № | Канонический ID | Задача | Статус | Контур | Следующее действие |
|---:|---|---|---|---|---|
| 21 | CTA-REVIEW-001 | Finding-Level Expert Review | DONE | HYBRID | Локальная приёмка завершена на Mac mini; automated + browser acceptance пройдены. |
| 22 | CTA-REVIEW-002 | Independent Review Adjudication | PLANNED | HYBRID + CLIENT | Сохранить независимые review и согласовать с заказчиком процесс adjudication. |
| 23 | CTA-CAL-003 | Calibration Quality Dashboard | PLANNED | HYBRID | Рассчитать review-метрики и экспортировать XLSX/JSON. |

### Этап 4 — локальные модели

| № | Канонический ID | Задача | Статус | Контур | Следующее действие |
|---:|---|---|---|---|---|
| 24 | CTA-BENCH-002 | Target Hardware OCR/VLM Benchmark | DONE | LOCAL_IDE | Выбран VLM-MLX-4B + TOPOLOGY-U, revision 20260801-091536. |
| 25 | CTA-MODEL-001 | Production Local Model Profile | BLOCKED_LOCAL | HYBRID + LOCAL_IDE | Зафиксировать OCR/VLM/LLM, quantization, timeouts, fallback и ресурсы. |

### Этап 5 — controlled pilot

| № | Канонический ID | Задача | Статус | Контур | Что требуется |
|---:|---|---|---|---|---|
| 26 | CTA-PILOT-002 | Real Case Intake and Data Quality Gate | BLOCKED_CLIENT | CLIENT + HYBRID | 15–20 чистых кейсов с IDs, hashes, placements, CG/TG counts и методологией. |
| 27 | CTA-PILOT-003 | Frozen Blind Diagnostic Run | BLOCKED_CLIENT | HYBRID | Заморозить system output до раскрытия outcomes. |
| 28 | CTA-PILOT-004 | Independent Expert Review Execution | BLOCKED_CLIENT | CLIENT | Два reviewer, где возможно; фиксация omissions и disagreements. |
| 29 | CTA-PILOT-005 | Provenance-Bound Outcome Linkage | BLOCKED_CLIENT | HYBRID | Связать frozen output с outcomes без причинной интерпретации. |
| 30 | CTA-PILOT-006 | Controlled Pilot Calibration Summary | PLANNED | GITHUB + HYBRID | Итог continue / redesign / pause / stop. |

### Этап 6 — методология v2

| № | Канонический ID | Задача | Статус | Контур |
|---:|---|---|---|---|
| 31 | CTA-METH-001 | Agent Error Taxonomy | PLANNED | GITHUB + HYBRID |
| 32 | CTA-METH-002 | Diagnostic Methodology v2 | PLANNED | GITHUB + CLIENT |
| 33 | CTA-METH-003 | Decision Threshold Sign-Off | BLOCKED_CLIENT | CLIENT |

### Этап 7 — on-premise release

| № | Канонический ID | Задача | Статус | Контур |
|---:|---|---|---|---|
| 34 | CTA-DEPLOY-001 | Client On-Premise Installation | BLOCKED_LOCAL | LOCAL_IDE |
| 35 | CTA-SEC-001 | Isolation, Audit and Recovery Acceptance | BLOCKED_LOCAL | LOCAL_IDE + CLIENT |
| 36 | CTA-RELEASE-001 | Controlled Pilot Release Candidate | PLANNED | HYBRID |

## 4. Таблица соответствия старых и канонических ID

Сопоставление не всегда один-к-одному: ранняя дорожная карта дробила работу подробнее, а каноническая объединяет её в принимаемые deliverables.

| Legacy ID | Канонический ID | Комментарий |
|---|---|---|
| CTA-001 | CTA-CORE-001 | Базовое приложение. |
| CTA-002–CTA-004 | CTA-CORE-001 / CTA-UI-001 | Security, asset intake и project workspace были включены в более крупные deliverables. |
| CTA-005–CTA-006 | CTA-DATA-001 / CTA-DQ-001 | Intake, mapping, normalization и lineage разделены по ответственности. |
| CTA-007 | CTA-DQ-001 | Data Quality gate. |
| CTA-008–CTA-009 | CTA-UI-001 | Clarifications и unified workspace. |
| CTA-010 | CTA-REPORT-001 | Основа экспорта. |
| CTA-011 | CTA-CAL-001 / CTA-CORE-001 | Prompt/evaluation registry вошёл в фундамент и calibration protocol. |
| CTA-012 | CTA-GOLD-001 | Synthetic golden pack. |
| CTA-013 | CTA-VISION-001 | Benchmark harness. |
| CTA-014 | CTA-OPS-001 | Backup/recovery. |
| CTA-015 | CTA-CAL-001 | Pilot calibration protocol. |
| CTA-016 | CTA-CAL-002 | Ozon calibration v1. |
| CTA-017 | CTA-VIS-002 | Canonical visual context. |
| CTA-018 | CTA-VIS-003 | Visual context propagation. |
| CTA-019 | CTA-VIS-004 | Evidence traceability. |
| CTA-020 | CTA-VIS-005 | Confidence and abstention. |
| CTA-021–CTA-022 | CTA-OZON-001 | Data package и loader объединены. |
| CTA-023–CTA-024 | CTA-OZON-002 | Linkage UI и campaign detail объединены. |
| CTA-025–CTA-026, CTA-031 | CTA-DEMO-001 | Contrast scenarios, E2E и readiness gate объединены. |
| CTA-027–CTA-030 | CTA-REPORT-002 | Finding model, funnel model и export pack объединены в Report v2. |
| CTA-032 | CTA-REVIEW-001 | Finding-level review. |
| CTA-033 | CTA-REVIEW-002 | Adjudication. |
| CTA-034 | CTA-CAL-003 | Calibration dashboard. |
| CTA-035 | CTA-BENCH-002 | Target hardware benchmark. |
| CTA-036–CTA-038 | CTA-BENCH-002 / CTA-MODEL-001 | Benchmark, profiles и replay сведены в выбор и фиксацию production profile. |
| CTA-039–CTA-041 | CTA-DATA-002 | Specification, templates и validator объединены. |
| CTA-043–CTA-044 | CTA-PILOT-002 | Dataset intake и case registration. |
| CTA-045 | CTA-PILOT-003 | Blind output freeze. |
| CTA-046–CTA-047 | CTA-PILOT-004 / CTA-REVIEW-002 | Review execution и adjudication разделены на платформу и проведение. |
| CTA-048 | CTA-PILOT-005 | Outcome linkage. |
| CTA-049–CTA-050 | CTA-PILOT-006 | Summary и управленческое решение. |
| CTA-051 | CTA-METH-001 | Error taxonomy. |
| CTA-052–CTA-054 | CTA-METH-002 | Rubric, prompts и category overlays объединены. |
| CTA-055 | CTA-METH-003 | Threshold sign-off. |
| CTA-056–CTA-058, CTA-060 | CTA-DEPLOY-001 | Infrastructure profile, package, installation и load acceptance. |
| CTA-059, CTA-061 | CTA-SEC-001 | Isolation и recovery acceptance. |
| CTA-062 | CTA-RELEASE-001 | Pilot release acceptance. |
| CTA-063–CTA-067 | Deferred branches | Канонические IDs будут назначены только после открытия этих веток. |

## 5. Насколько проект близок к MVP

### Functional/demo MVP — 100%

Выполнены блоки A и B: загрузка материалов, локальная VLM, анализ, visual evidence, confidence/abstention, Ozon A/B outcomes, browser workspace и клиентские отчёты.

### MVP для установки у заказчика — ориентировочно 65–75%

Кодовая и демонстрационная часть готова. Для управляемого развёртывания ещё нужны:

1. экспертная калибровка в продукте — CTA-REVIEW-001/002, CTA-CAL-003;
2. benchmark и production model profile — CTA-MODEL-001 (CTA-BENCH-002 — DONE);
3. on-premise installation и security acceptance — CTA-DEPLOY-001, CTA-SEC-001;
4. release bundle — CTA-RELEASE-001.

### Валидированный продукт — не завершён

Controlled pilot и methodology v2 ещё не проведены. Поэтому нельзя заявлять validated accuracy, причинный brand lift или прогноз uplift.

## 6. Ближайший канонический порядок

```text
CTA-REVIEW-001
→ CTA-REVIEW-002
→ CTA-CAL-003
→ CTA-BENCH-002 — DONE
→ CTA-MODEL-001
→ CTA-PILOT-002
→ CTA-PILOT-003
→ CTA-PILOT-004
→ CTA-PILOT-005
→ CTA-PILOT-006
```

Параллельно после согласования инфраструктуры можно готовить CTA-DEPLOY-001, но закрыть его до production model profile нельзя.
