# Creative Test Agent — полный клиентский демонстрационный контур

Версия: 1.0  
Дата: 2026-07-31  
Назначение: 35–45-минутная демонстрация максимально полного рабочего контура Заказчику.

## Что показываем

Не отдельный «AI-анализ картинки», а управляемый evidence-bound процесс:

`исходные данные → креатив → визуальные наблюдения → диагностика → фактические outcomes → экспертная проверка → независимое расхождение → adjudication → калибровочные метрики → отчёты и exports`.

Контур демонстрирует:

- local-first работу без внешних API;
- provenance и integrity каждого значимого слоя;
- distinction between fact, agent diagnostic, outcome and expert opinion;
- явную работу с missing/uncertain evidence;
- human-in-the-loop release boundary;
- воспроизводимые клиентские отчёты и калибровочные exports.

## Evidence boundary

Во время встречи нельзя называть dashboard «точностью модели» и нельзя утверждать причинный uplift отдельного креатива.

Допустимые формулировки:

- «наблюдаемая экспертная поддержка выводов на выбранном evidence set»;
- «доля выводов, прошедших независимую экспертную проверку»;
- «descriptive outcome coverage»;
- «фактические CG/TG outcomes кампании»;
- «diagnostic recommendation с confidence и release boundary».

Запрещённые формулировки:

- validated model accuracy;
- proven causal lift;
- predicted numeric uplift;
- automatic winning creative;
- regulatory/medical approval.

## Подготовленный маршрут

Подставить локальный `project_id` вместо `{project_id}`.

1. **Health и закрытый контур**
   - `/health`
   - `/health/db`
   - `/version`
   - показать `local_only_mode=true` и loopback listener.

2. **Проект и lineage**
   - `/ui/projects`
   - `/ui/projects/{project_id}`
   - показать project scope, исходные assets, mapping/DQ, audit и entry points.

3. **Campaign Evidence Workspace**
   - `/ui/projects/{project_id}/campaign-evidence`
   - открыть контрастный case с real preview, factual outcomes и completed diagnostic.
   - показать campaign/asset linkage confidence и missing-data warnings.

4. **Ozon client demo view**
   - `/ui/projects/{project_id}/campaign-evidence/demo`
   - показать выбранный contrast case, visual observations, evidence references, recommendation и ограничения.
   - при готовности сформировать Client Report v2 из этой страницы.

5. **Visual evidence и diagnostic layers**
   - OCR/visual summary;
   - brand/logo prominence;
   - packshot/CTA/promo badge;
   - hierarchy, readability, cognitive load;
   - message–visual binding;
   - confidence, provenance и missing semantics;
   - accepted/review-required/abstained findings;
   - proposed vs effective recommendation.

6. **Factual CG/TG outcomes**
   - показать outcomes рядом с diagnostics;
   - проговорить, что campaign-set outcomes не атрибутируются автоматически одному asset;
   - показать funnel stage отдельно: awareness, recall, consideration, purchase intent.

7. **Client Report v2**
   - показать слои: facts, agent diagnostics, outcomes, expert review, limitations/confidence;
   - показать HTML и downloadable formats, доступные в текущем локальном проекте;
   - показать evidence JSON/manifest и integrity hash;
   - продемонстрировать, что release блокируется при incomplete/unresolved review state.

8. **Finding-Level Expert Review**
   - перейти к review через finding в campaign evidence detail;
   - показать immutable system finding;
   - сохранить review первого reviewer;
   - показать шкалы correctness, relevance, actionability, traceability, severity correctness и confidence;
   - добавить human finding как omission, не перезаписывая system output.

9. **Independent Review**
   - открыть тот же finding от второго reviewer subject;
   - показать отдельный append-only stream;
   - создать agreement либо material disagreement;
   - material disagreement возникает при различном decision, severity correctness или dimension spread ≥ 2.

10. **Adjudication**
    - войти как `manager`/`admin`, отличный от basis reviewers;
    - показать immutable basis IDs и SHA-256 fingerprint;
    - сохранить final decision, confidence и mandatory rationale;
    - объяснить stale-basis protection после новой review revision;
    - показать, что история disagreement не исчезает.

11. **Calibration Quality Dashboard**
    - `/ui/projects/{project_id}/calibration`
    - показать девять metric cards;
    - переключить `all`, `real_client`, `synthetic`, `unclassified`;
    - показать included/excluded/deferred cases;
    - показать numerator, denominator, coverage, definition и limitations;
    - отдельно показать unresolved/stale/insufficient-review coverage gaps.

12. **Workflow measurements**
    - добавить operator touch time и manual action count;
    - показать validation `operator_touch_seconds <= wall_clock_seconds`;
    - подчеркнуть, что время не угадывается по audit timestamps;
    - показать append-only history.

13. **Deterministic exports**
    - `/calibration-dashboard/projects/{project_id}/export.json`
    - `/calibration-dashboard/projects/{project_id}/export.xlsx`
    - `/calibration-dashboard/projects/{project_id}/manifest.json`
    - показать SHA-256 header и manifest;
    - показать XLSX sheets `Summary`, `Metrics`, `Cases`, `Claim Boundary`;
    - показать `null`/empty для missing values вместо выдуманных нулей.

14. **Audit и безопасность**
    - показать audit trail для classification, review, adjudication, report generation и workflow measurement;
    - подтвердить loopback-only operation;
    - показать отсутствие внешней telemetry и cloud LLM calls;
    - проговорить backup/restore readiness.

## Рекомендуемые showcase cases

Для контраста использовать локальные cases, уже принятые CTA-OZON-002/CTA-DEMO-001:

- Theraflex;
- Rennie;
- Bepanthen / Supradyn Energy;
- OZON-007 как полный contrast case, если он присутствует в локальной БД.

Отдельно показать ограничения на Relief, Triderm и multi-asset cases, где linkage или individual attribution неполны.

## Talk track

### Вступление

«Система не пытается заменить эксперта одной цифрой. Она собирает проверяемую цепочку от исходного креатива и фактических данных до диагностики, независимой экспертной оценки и калибровочного контроля».

### На visual evidence

«Каждый принятый визуальный вывод должен иметь конкретную observation reference, confidence и provenance. При недостатке evidence система abstains или требует review, а не додумывает».

### На outcomes

«Outcomes показаны рядом с диагностикой, но не превращаются автоматически в доказательство причинного эффекта отдельного asset».

### На review/adjudication

«Мнения экспертов не переписываются. Расхождение считается автоматически и разрешается отдельным решением третьей роли с immutable basis».

### На dashboard

«Это dashboard качества калибровочного процесса и evidence coverage, а не заявка на валидированную точность модели».

### Финал

«Следующий шаг — прогнать тот же замороженный массив, который используется в параллельном решении Заказчика, сохранить независимые outputs и калибровать систему на расхождениях, omissions и outcome coverage».

## Варианты демонстрации

### Полный real-local режим

Использовать локальный Ozon project и локальный VLM runtime. Реальные материалы не экспортировать за пределы закрытого контура.

### Safe synthetic fallback

При проблеме с моделью или real DB использовать synthetic fixture. Явно показать evidence class `synthetic`; не выдавать его за клиентский результат.

### Report-only fallback

При проблеме live inference открыть уже сформированный локальный Client Report v2, evidence JSON и Calibration Dashboard. Объяснить, что inference не является обязательным для проверки provenance/review/adjudication/export chain.

## Критерий успешной встречи

Заказчик видит один непрерывный рабочий путь и может ответить «да» на вопросы:

- видны ли исходные evidence и ограничения;
- можно ли проследить каждый finding;
- может ли эксперт исправить/дополнить систему без уничтожения исходного output;
- сохраняются ли независимые мнения;
- блокируется ли release при незавершённой проверке;
- разделены ли real и synthetic evidence;
- можно ли выгрузить воспроизводимый пакет;
- может ли контур работать локально без внешних API.
