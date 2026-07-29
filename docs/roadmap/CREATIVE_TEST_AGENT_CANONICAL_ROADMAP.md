# Creative Test Agent — каноническая дорожная карта

Версия: 1.3  
Дата фиксации: 2026-07-29  
Статус документа: canonical / single source of truth

## Назначение

Этот документ задаёт единственный канонический порядок развития Creative Test Agent.

Правила:

1. У каждой задачи есть неизменяемый уникальный код и уникальное каноническое имя.
2. Задачи выполняются в порядке поля `Порядок`, если отдельно не зафиксировано исключение.
3. Новые задачи добавляются только с новым кодом; существующие коды не переиспользуются.
4. Статус изменяется только после выполнения acceptance criteria.
5. Реальные клиентские материалы не коммитятся в репозиторий.
6. До завершения controlled pilot запрещены заявления о валидированной точности, причинном brand lift или прогнозе uplift.

## Обозначения

Статусы:

- `DONE` — выполнено и принято;
- `PARTIAL` — основа выполнена, но необходима следующая итерация;
- `PLANNED` — не начато;
- `BLOCKED_CLIENT` — зависит от материалов или решения клиента;
- `BLOCKED_LOCAL` — требует локальной среды, моделей, браузера, GPU или закрытых файлов.

Контур реализации:

- `GITHUB` — можно полностью выполнить из чата через GitHub: код, тесты, документация, PR, CI;
- `HYBRID` — код можно сделать через GitHub, но acceptance требует локальной проверки;
- `LOCAL_IDE` — требуется Codex/OpenCode или другая локальная IDE;
- `CLIENT` — требуется действие, материал или решение клиента.

---

# Канонический порядок реализации

## Блок A. Завершённый фундамент

### 01. CTA-CORE-001 — Local-First Application Foundation

- Статус: `DONE`
- Контур: `GITHUB`
- Результат: FastAPI, локальная БД, загрузка файлов, проекты, клиенты, аудит, роли, локальные модели, экспорт отчётов, Docker foundation.
- Acceptance: базовое приложение и CI работают в закрытом контуре.

### 02. CTA-DATA-001 — Deterministic Tabular Intake

- Статус: `DONE`
- Контур: `GITHUB`
- Зависит от: CTA-CORE-001
- Результат: безопасный импорт CSV/XLSX, inspection, устойчивое определение разделителей, регистрация исходных файлов.
- Acceptance: импорт воспроизводим, оригиналы не изменяются, регрессионные тесты проходят.

### 03. CTA-GOLD-001 — Synthetic Creative Golden Pack

- Статус: `DONE`
- Контур: `GITHUB`
- Зависит от: CTA-DATA-001
- Результат: детерминированный synthetic golden pack для регрессии визуального анализа.
- Acceptance: pack, manifest и integrity-check проходят CI.

### 04. CTA-VISION-001 — Local Vision Benchmark Harness

- Статус: `DONE`
- Контур: `GITHUB`
- Зависит от: CTA-GOLD-001
- Результат: benchmark harness для OCR/VLM/hybrid-кандидатов.
- Acceptance: harness измеряет качество, abstention, repeatability, latency и ресурсы без claims о production accuracy.

### 05. CTA-PILOT-INTAKE-001 — Controlled Pilot Intake Package

- Статус: `DONE`
- Контур: `GITHUB`
- Зависит от: CTA-DATA-001
- Результат: as-is intake, SHA-256, relationship hints, acceptance gates и pilot metrics.
- Acceptance: пакет создаётся и валидируется локально и в CI.

### 06. CTA-REPORT-001 — Provisional Evidence-Bound One-Page Report

- Статус: `DONE`
- Контур: `GITHUB`
- Зависит от: CTA-PILOT-INTAKE-001
- Результат: one-page PPTX/HTML/evidence JSON с provenance и ограничениями.
- Acceptance: отчёт воспроизводим, manifest валиден, запрещён composite prediction claim.

### 07. CTA-OPS-001 — Operator Recovery Rehearsal

- Статус: `DONE`
- Контур: `GITHUB`
- Зависит от: CTA-CORE-001
- Результат: backup, safe restore, recovery drill, operator checklist.
- Acceptance: автоматизированная репетиция восстановления проходит CI.

### 08. CTA-CAL-001 — Pilot Calibration Protocol

- Статус: `DONE`
- Контур: `GITHUB`
- Зависит от: CTA-PILOT-INTAKE-001, CTA-REPORT-001
- Результат: finding-level review, outcome linkage, questionnaire evidence, workflow metrics, calibration summary.
- Acceptance: пакет валидируется, real-human и synthetic evidence разделены, causal interpretation запрещена.

### 09. CTA-DQ-001 — Strict Data Quality Lineage Binding

- Статус: `DONE`
- Контур: `GITHUB`
- Зависит от: CTA-DATA-001
- Результат: Data Quality связан с актуальным mapping fingerprint и normalization run.
- Acceptance: stale normalization блокируется, повторный inspection не раздувает counts.

### 10. CTA-UI-001 — Unified Pilot Workspace

- Статус: `DONE`
- Контур: `GITHUB`
- Зависит от: CTA-DATA-001, CTA-DQ-001, CTA-REPORT-001
- Результат: единый browser workflow без ручного UUID/JSON.
- Acceptance: оператор проходит путь intake → mapping → normalization → DQ → clarification → readiness → reports только через UI.

### 11. CTA-CAL-002 — Ozon Brand-Lift Diagnostic Calibration v1

- Статус: `DONE`
- Контур: `GITHUB`
- Зависит от: CTA-CAL-001
- Результат: 27 CG/TG-наблюдений, статистический descriptive package, creative manifest, 12-критериальная funnel-aware rubric, обновлённые промпты.
- Acceptance: CI проходит; awareness, recall, consideration и purchase intent не смешиваются; numeric uplift prediction запрещён.

---

## Блок B. Клиентская демонстрация v1

### 12. CTA-VIS-002 — Unified Creative Visual Context

- Статус: `DONE`
- Контур: `GITHUB`
- Зависит от: CTA-VISION-001, CTA-CAL-002
- Результат: создана единая версионированная типизированная структура визуального контекста с evidence-bound observations, обязательными confidence/provenance, явной семантикой missing-versus-absent и совместимостью с legacy `VisionResult`.
- Scope:
  - OCR text;
  - visual summary;
  - brand/logo prominence;
  - packshot;
  - CTA;
  - promo badge;
  - hierarchy;
  - message–visual binding;
  - cognitive load;
  - readability;
  - extraction confidence;
  - visual risks.
- Acceptance:
  - структура валидируется schema/tests;
  - отсутствующие признаки остаются missing;
  - confidence и provenance обязательны;
  - backward compatibility сохранена.

### 13. CTA-VIS-003 — Full-Pipeline Visual Context Propagation

- Статус: `DONE`
- Контур: `GITHUB`
- Зависит от: CTA-VIS-002
- Результат: единый fingerprinted `VisualEvidenceEnvelope` строится один раз и без изменений передаётся в creative summary, audience simulation, rubric scoring, brand safety, brandbook compliance и final recommendation; canonical context, confidence, provenance, warnings и missing semantics сохраняются в test-run storage и API.
- Scope:
  - creative summary;
  - audience simulation;
  - rubric scoring;
  - brand safety;
  - brandbook compliance;
  - final recommendation.
- Acceptance:
  - каждая стадия получает одинаковую evidence-модель;
  - промпты не угадывают отсутствующие признаки;
  - regression tests подтверждают использование visual context;
  - confidence снижается при плохом extraction без автоматического снижения creative score.

### 14. CTA-VIS-004 — Visual Evidence Traceability

- Статус: `DONE`
- Контур: `GITHUB`
- Зависит от: CTA-VIS-003
- Результат: каждое populated visual observation получает детерминированный integrity-checked reference ID; визуальные findings связываются с конкретными observation snapshots, confidence и provenance; unknown, stale и criterion-unrelated references отклоняются; unsupported/unassessed visual conclusions fail closed без автоматического изменения legacy score.
- Scope:
  - reference registry в `VisualEvidenceEnvelope` v1.1;
  - creative summary;
  - audience simulation;
  - rubric findings;
  - brand-safety risks;
  - brandbook-compliance violations;
  - final recommendation;
  - persisted trace manifest и API.
- Acceptance:
  - unassessed `null` fields не получают references;
  - assessed absence остаётся citable observation;
  - каждый accepted visual finding имеет валидный relevant reference;
  - invalid references сохраняются отдельно для audit и не принимаются как evidence;
  - visual finding без валидного reference получает zero diagnostic confidence и явный unsupported/unassessed status;
  - score не снижается автоматически только из-за missing extraction;
  - trace manifest воспроизводим и сохраняется без DB migration;
  - regression tests и CI проходят.

### 15. CTA-OZON-001 — Ozon Showcase Data Loader

- Статус: `PLANNED`
- Контур: `HYBRID`
- Зависит от: CTA-DATA-001, CTA-CAL-002
- Цель: идемпотентно собирать локальный showcase-проект из ZIP и XLSX.
- GitHub scope:
  - loader;
  - mapping schema;
  - validation;
  - synthetic fixtures;
  - tests;
  - документация.
- Local acceptance:
  - реальный ZIP и XLSX загружаются без коммита клиентских файлов;
  - повторный запуск не создаёт дубликаты;
  - uncertain linkage не превращается в exact.

### 16. CTA-OZON-002 — Ozon Campaign Evidence Workspace

- Статус: `PLANNED`
- Контур: `HYBRID`
- Зависит от: CTA-OZON-001, CTA-VIS-004
- Цель: показать в UI связку campaign → creative set → CG/TG outcomes → agent diagnostics.
- Scope:
  - campaign cards;
  - asset previews;
  - funnel metrics;
  - linkage confidence;
  - missing-data warnings;
  - factual outcomes рядом с diagnostic findings.
- Acceptance:
  - Theraflex, Rennie и Bepanthen/Supradyn Energy доступны как контрастные showcase cases;
  - Relief, Triderm и multi-asset cases имеют явные ограничения;
  - browser smoke test проходит локально.

### 17. CTA-REPORT-002 — Evidence-Bound Client Report v2

- Статус: `PLANNED`
- Контур: `HYBRID`
- Зависит от: CTA-VIS-004, CTA-OZON-002
- Цель: сформировать основной клиентский отчёт пилота.
- Обязательные слои:
  1. наблюдаемые факты;
  2. диагностика агента;
  3. фактические CG/TG outcomes;
  4. экспертная оценка;
  5. ограничения и confidence.
- Форматы:
  - HTML;
  - one-page PPTX;
  - full PPTX;
  - DOCX;
  - evidence JSON;
  - XLSX appendix.
- Acceptance:
  - каждый finding имеет evidence reference;
  - campaign-set и individual-asset conclusions различаются;
  - missing values не заполняются догадками;
  - визуальная проверка PPTX/DOCX выполнена локально.

### 18. CTA-DEMO-001 — Ozon End-to-End Client Demo

- Статус: `PLANNED`
- Контур: `HYBRID`
- Зависит от: CTA-OZON-002, CTA-REPORT-002
- Цель: зафиксировать воспроизводимый демонстрационный сценарий.
- Сценарий:
  - открыть showcase project;
  - выбрать кампанию;
  - показать исходный креатив;
  - показать visual extraction;
  - показать funnel diagnostics;
  - сопоставить с CG/TG;
  - скачать отчёт.
- Acceptance:
  - synthetic E2E проходит CI;
  - real-data smoke test проходит локально;
  - demo script и operator checklist готовы.

### 19. CTA-DATA-002 — Client Calibration Data Request Pack

- Статус: `PLANNED`
- Контур: `GITHUB`
- Зависит от: CTA-DEMO-001
- Цель: стандартизировать запрос следующей партии данных.
- Deliverables:
  - XLSX template;
  - CSV template;
  - JSON Schema;
  - validator;
  - пример корректного набора;
  - пример ошибочного набора;
  - инструкция клиенту.
- Acceptance:
  - обязательные поля формально проверяются;
  - абсолютные counts предпочтительнее округлённых rates;
  - asset/campaign/placement linkage обязателен или явно missing.

---

## Блок C. Экспертная калибровка

### 20. CTA-REVIEW-001 — Finding-Level Expert Review

- Статус: `PLANNED`
- Контур: `HYBRID`
- Зависит от: CTA-REPORT-002
- Цель: обеспечить поштучную проверку выводов агента.
- Оценки:
  - supported;
  - partially_supported;
  - unsupported;
  - missed_by_system;
  - harmful_false_positive;
  - needs_rewording.
- Дополнительные поля:
  - correctness;
  - relevance;
  - actionability;
  - traceability;
  - severity correctness;
  - reviewer confidence.
- Acceptance:
  - БД, API, UI, audit trail и exports реализованы;
  - исходный системный finding не перезаписывается;
  - usability проверена локально.

### 21. CTA-REVIEW-002 — Independent Review Adjudication

- Статус: `PLANNED`
- Контур: `HYBRID`
- Зависит от: CTA-REVIEW-001
- Цель: сохранять и разрешать расхождения между экспертами.
- Acceptance:
  - независимые review остаются неизменными;
  - disagreement вычисляется автоматически;
  - adjudication требует adjudicator и rationale;
  - клиент утверждает процесс adjudication.

### 22. CTA-CAL-003 — Calibration Quality Dashboard

- Статус: `PLANNED`
- Контур: `HYBRID`
- Зависит от: CTA-REVIEW-002
- Метрики:
  - expert-supported finding rate;
  - actionability rate;
  - traceability rate;
  - human-added findings;
  - harmful false positives;
  - reviewer disagreement;
  - operator touch time;
  - manual action count;
  - outcome coverage.
- Acceptance:
  - dashboard не называет эти метрики validated model accuracy;
  - real и synthetic evidence отображаются раздельно;
  - XLSX/JSON export доступен.

---

## Блок D. Локальные модели и целевая инфраструктура

### 23. CTA-BENCH-002 — Target Hardware OCR/VLM Benchmark

- Статус: `BLOCKED_LOCAL`
- Контур: `LOCAL_IDE`
- Зависит от: CTA-VIS-003, CTA-VISION-001
- Цель: выбрать OCR/VLM/hybrid конфигурацию на фактическом оборудовании.
- Требуется Codex/OpenCode для:
  - установки моделей;
  - запуска benchmark;
  - GPU/CPU/RAM/VRAM измерений;
  - проверки русского OCR;
  - browser/manual audit.
- Acceptance:
  - сравнены минимум три режима;
  - зафиксированы extraction quality, hallucination, abstention, repeatability, latency и ресурсы;
  - выбран кандидат или зафиксировано отсутствие приемлемого кандидата.

### 24. CTA-MODEL-001 — Production Local Model Profile

- Статус: `BLOCKED_LOCAL`
- Контур: `HYBRID`
- Зависит от: CTA-BENCH-002
- Цель: зафиксировать рабочий model profile.
- Параметры:
  - OCR engine;
  - VLM;
  - LLM;
  - quantization;
  - context size;
  - timeout;
  - fallback;
  - image limits;
  - RAM/VRAM requirements.
- Acceptance:
  - profile воспроизводимо загружается;
  - health-check проходит;
  - конфигурация документирована;
  - measured values не заменены предположениями.

---

## Блок E. Controlled pilot

### 25. CTA-PILOT-002 — Real Case Intake and Data Quality Gate

- Статус: `BLOCKED_CLIENT`
- Контур: `CLIENT + HYBRID`
- Зависит от: CTA-DATA-002, CTA-CAL-003, CTA-MODEL-001
- Цель: зарегистрировать 15–20 чистых реальных кейсов.
- Acceptance:
  - каждый case имеет creative ID, campaign ID и asset hash;
  - mapping и DQ завершены;
  - excluded/deferred cases имеют причину;
  - исходные материалы остаются локальными.

### 26. CTA-PILOT-003 — Frozen Blind Diagnostic Run

- Статус: `BLOCKED_CLIENT`
- Контур: `HYBRID`
- Зависит от: CTA-PILOT-002
- Цель: сформировать и заморозить выводы агента до раскрытия outcomes экспертам/разработчикам.
- Acceptance:
  - output hash и prompt/model versions сохранены;
  - повторный запуск не заменяет frozen output;
  - outcome leakage исключён процедурно.

### 27. CTA-PILOT-004 — Independent Expert Review Execution

- Статус: `BLOCKED_CLIENT`
- Контур: `CLIENT`
- Зависит от: CTA-PILOT-003, CTA-REVIEW-002
- Цель: провести независимую проверку findings двумя экспертами, где возможно.
- Acceptance:
  - каждый included case имеет finding-level review;
  - omissions фиксируются как human-added;
  - disagreements adjudicated или явно pending.

### 28. CTA-PILOT-005 — Provenance-Bound Outcome Linkage

- Статус: `BLOCKED_CLIENT`
- Контур: `HYBRID`
- Зависит от: CTA-PILOT-003
- Цель: связать frozen diagnostics с историческими/посткампанийными outcomes.
- Acceptance:
  - provenance hash обязателен;
  - context comparability указана;
  - causal_interpretation_allowed=false;
  - missing outcomes остаются missing.

### 29. CTA-PILOT-006 — Controlled Pilot Calibration Summary

- Статус: `PLANNED`
- Контур: `GITHUB + HYBRID`
- Зависит от: CTA-PILOT-004, CTA-PILOT-005
- Цель: сформировать итог controlled pilot.
- Acceptance:
  - workflow, review, disagreement и outcome coverage описаны;
  - не заявляется validated accuracy;
  - сформировано решение: continue / redesign / pause / stop.

---

## Блок F. Методология v2 и пороги

### 30. CTA-METH-001 — Agent Error Taxonomy

- Статус: `PLANNED`
- Контур: `GITHUB + HYBRID`
- Зависит от: CTA-PILOT-006
- Цель: классифицировать систематические ошибки.
- Классы:
  - missed evidence;
  - unsupported inference;
  - severity inflation;
  - weak recommendation;
  - category mismatch;
  - visual extraction failure;
  - reviewer disagreement.
- Acceptance: все существенные ошибки пилота отнесены к воспроизводимой taxonomy.

### 31. CTA-METH-002 — Diagnostic Methodology v2

- Статус: `PLANNED`
- Контур: `GITHUB + CLIENT`
- Зависит от: CTA-METH-001
- Цель: обновить рубрики, промпты, confidence policy и category overlays.
- Acceptance:
  - изменения основаны на pilot evidence;
  - regression pack обновлён;
  - методология подписана владельцем методологии и техническим владельцем.

### 32. CTA-METH-003 — Decision Threshold Sign-Off

- Статус: `BLOCKED_CLIENT`
- Контур: `CLIENT`
- Зависит от: CTA-METH-002
- Цель: утвердить пороги внутренних решений.
- Возможные статусы:
  - acceptable;
  - revise;
  - block;
  - insufficient evidence.
- Acceptance:
  - пороги утверждены клиентом;
  - правила confidence documented;
  - пороги не интерпретируются как прогноз market lift.

---

## Блок G. On-premise pilot release

### 33. CTA-DEPLOY-001 — Client On-Premise Installation

- Статус: `BLOCKED_LOCAL`
- Контур: `LOCAL_IDE`
- Зависит от: CTA-MODEL-001, CTA-METH-002
- Цель: развернуть приложение и модели в контуре клиента.
- Требуется Codex/OpenCode для:
  - Docker/host installation;
  - model download/import;
  - storage configuration;
  - GPU setup;
  - environment secrets;
  - local smoke tests.
- Acceptance: приложение запускается без внешних API и обслуживает согласованное число пользователей.

### 34. CTA-SEC-001 — Isolation, Audit and Recovery Acceptance

- Статус: `BLOCKED_LOCAL`
- Контур: `LOCAL_IDE + CLIENT`
- Зависит от: CTA-DEPLOY-001, CTA-OPS-001
- Цель: проверить закрытый контур, журналирование и восстановление.
- Acceptance:
  - внешняя телеметрия отсутствует;
  - роли доступа проверены;
  - backup/restore rehearsal выполнена на целевой машине;
  - клиент принял security checklist.

### 35. CTA-RELEASE-001 — Controlled Pilot Release Candidate

- Статус: `PLANNED`
- Контур: `HYBRID`
- Зависит от: CTA-SEC-001, CTA-METH-003
- Цель: собрать версионированный пилотный релиз.
- Deliverables:
  - release bundle;
  - manifest;
  - SBOM/зависимости;
  - config templates;
  - model profile;
  - operator guide;
  - rollback guide;
  - acceptance report.
- Acceptance: release воспроизводимо устанавливается и проходит controlled pilot checklist.

---

# Отложенные ветки

Следующие задачи не входят в ближайший канонический путь и могут быть открыты только после CTA-RELEASE-001:

- video and storyboard analysis;
- automatic media-plan recommendations;
- рекламные кабинетные интеграции;
- полноценная predictive uplift model;
- автоматический выбор winning creative;
- SaaS multi-tenant edition;
- SSO/MFA enterprise extension;
- масштабная brand memory / RAG по всей истории клиента;
- synthetic focus groups как самостоятельный исследовательский продукт.

# Ближайшая контрольная точка

Первая ближайшая контрольная точка достигается после задач CTA-VIS-002 → CTA-VIS-003 → CTA-VIS-004 → CTA-OZON-001 → CTA-OZON-002 → CTA-REPORT-002 → CTA-DEMO-001.

Критерий контрольной точки:

> На локальной машине открыт Ozon showcase project; для выбранной кампании видны исходный креатив, извлечённые визуальные признаки, traceable funnel-aware диагностика, фактические CG/TG outcomes, качество linkage, ограничения и скачиваемый evidence-bound отчёт.

# Следующая задача

К реализации первой запускается:

`CTA-OZON-001 — Ozon Showcase Data Loader`.
