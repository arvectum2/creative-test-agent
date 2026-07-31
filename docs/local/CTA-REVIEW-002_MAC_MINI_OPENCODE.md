# ТЗ для OpenCode — локальная приёмка CTA-REVIEW-002

## 1. Цель

Проверить на Mac mini ветку `feat/cta-review-002` как операторский workflow: два независимых эксперта оценивают один system finding, система автоматически выявляет disagreement, третий участник выполняет adjudication, а все исходные записи остаются неизменными.

Работать только на synthetic fixtures или обезличенной локальной копии. Реальные файлы Заказчика, screenshots с клиентскими данными, локальная БД, model weights и generated reports не коммитить.

## 2. Исходные данные

- repository: `arutyunoveth/creative-test-agent`;
- branch: `feat/cta-review-002`;
- issue: `#63`;
- локальная среда проекта и существующий `.env`;
- отдельная backup-копия текущей SQLite/PostgreSQL БД;
- synthetic workspace из repository.

## 3. Подготовка

1. Сохранить:
   - `git status`;
   - текущий branch/commit;
   - версию Python;
   - значения security posture без секретов;
   - SHA-256 исходной БД.
2. Переключиться на `feat/cta-review-002` и подтянуть актуальный commit.
3. Создать отдельную тестовую БД либо backup рабочей БД.
4. Убедиться, что:
   - `CTA_LOCAL_ONLY_MODE=true`;
   - host — `127.0.0.1`;
   - cloud LLM/VLM отключены;
   - telemetry и внешние API не используются.

## 4. Автоматизированная проверка

Выполнить последовательно:

```bash
python -m pip install -e ".[dev]"
python -m compileall -q src scripts
python scripts/check_model_registry.py
alembic current
alembic upgrade head
alembic current
python -m pytest tests/test_finding_reviews.py tests/test_client_report_v2.py -q
```

Затем выполнить полный regression suite, если он укладывается в локальное окно:

```bash
python -m pytest -q
```

Зафиксировать команды, exit codes, число passed/failed/skipped и полный текст только новых failures.

## 5. Проверка migration

Проверить на чистой БД и на копии БД после CTA-REVIEW-001:

- появились поля `reviewer_subject_id`, `reviewer_subject_kind`, `reviewer_revision_number`;
- legacy review получили backfill identity и revision;
- создана таблица `finding_adjudication` и индексы;
- `alembic downgrade h7i8j9k0l1m2` выполняется на тестовой БД;
- повторный `alembic upgrade head` успешен;
- исходные review не потеряны и не изменены по содержанию.

Сравнить counts и SHA-256 экспортов до/после там, где это применимо.

## 6. Browser acceptance

Запустить приложение штатной командой проекта на loopback. Через UI без ручного ввода UUID и без редактирования JSON выполнить сценарий.

### Сценарий A — независимые review

1. Открыть synthetic project → Campaign Evidence → system finding → `Finding review`.
2. Сохранить review от:
   - Expert ID `reviewer-a`, display name `Reviewer A`;
   - decision `supported`, высокие dimensions.
3. В отдельной browser session или после смены declared identity сохранить review от:
   - Expert ID `reviewer-b`, display name `Reviewer B`;
   - decision `unsupported`, correctness/traceability минимум на 2 пункта ниже, severity correctness отличающийся.
4. Проверить:
   - в history две записи;
   - у обеих expert revision = 1;
   - reviewer IDs различаются;
   - исходный system finding и snapshot SHA-256 одинаковы;
   - status автоматически стал `disagreement`;
   - причины включают decision mismatch и соответствующие score/severity mismatches.

### Сценарий B — независимая ревизия

1. Сохранить вторую revision для `reviewer-a`.
2. Проверить:
   - global revision увеличилась;
   - reviewer-a revision стала 2;
   - `supersedes_review_id` указывает только на предыдущую review reviewer-a;
   - review reviewer-b не superseded и не изменена.

### Сценарий C — adjudication

1. Открыть `Adjudication`.
2. Проверить отображение обеих latest review, immutable review IDs и basis fingerprint.
3. Сохранить решение третьим участником:
   - Adjudicator ID `adjudicator-1`;
   - role `Methodology owner`;
   - final decision, dimensions, confidence;
   - обязательный осмысленный rationale.
4. Проверить:
   - status = `adjudicated`;
   - adjudication round = 1;
   - basis review IDs соответствуют двум latest review;
   - исходные review и system finding не изменены;
   - analyst и basis reviewer не могут выполнить adjudication.

### Сценарий D — stale basis

1. Открыть adjudication page и сохранить basis fingerprint.
2. Не закрывая страницу, создать новую revision одного reviewer в другой session.
3. Попытаться сохранить adjudication со старой страницы.
4. Ожидается HTTP 409 / понятное сообщение `adjudication_basis_changed`.
5. После reload status должен быть `stale_adjudication`, прежняя adjudication остаётся в history.
6. Сохранить round 2 на актуальном basis и проверить `supersedes_adjudication_id`.

## 7. Export и Client Report v2

Для состояний `disagreement`, `adjudicated`, `stale_adjudication` проверить:

- `/finding-reviews/projects/{project_id}/evidence.json`;
- calibration ZIP;
- `expert_review.csv`;
- `adjudications.csv`;
- `package_manifest.json` и SHA-256;
- Client Report v2 evidence/HTML/PDF/PPTX, которые генерируются штатным workflow.

Ожидания:

- unresolved disagreement → `not_reviewed`, `pending_adjudication`, `manual_review_required`;
- current adjudication → итоговый adjudicated verdict с basis fingerprint;
- stale adjudication → снова pending adjudication;
- original review rationales и revisions доступны только как append-only evidence;
- human-added finding не превращается в system finding;
- claim boundaries запрещают validated accuracy, causal lift, asset-level attribution и automatic threshold tuning.

Два последовательных calibration ZIP без изменения данных должны быть byte-identical.

## 8. Security acceptance

Подтвердить:

- приложение слушает только loopback;
- запросы к внешним адресам отсутствуют;
- cloud LLM/VLM вызовы отсутствуют;
- клиентские данные не попали в git diff/logs/screenshots;
- project-scope isolation: review/adjudication одного project недоступны через другой project ID;
- audit log содержит `finding_review_created`, `human_finding_created`, `finding_adjudication_created`;
- update/delete immutable моделей отклоняются.

## 9. Evidence bundle

Создать локально каталог, не коммитить клиентские данные:

```text
artifacts/local-acceptance/CTA-REVIEW-002/<timestamp>/
```

Включить только безопасные материалы:

- `environment.txt` без секретов;
- `commands.log`;
- `pytest-summary.txt`;
- `migration-check.txt`;
- `browser-checklist.md`;
- synthetic screenshots;
- redacted evidence JSON;
- SHA-256 manifest.

В issue `#63` и PR добавить комментарий с итогом `PASS` или `FAIL`, commit SHA, кратким перечнем проверок и ссылкой только на безопасные committed artifacts либо текстовый summary. Реальные client artifacts не загружать.

## 10. Критерий PASS

PASS ставится только если одновременно:

- migration и targeted tests проходят;
- два reviewer streams независимы и append-only;
- disagreement вычисляется автоматически;
- third-party adjudication работает;
- stale basis защищён;
- Client Report v2 блокирует unresolved disagreement;
- export детерминирован;
- loopback/no-cloud подтверждены;
- клиентские материалы не закоммичены.

При failure не исправлять acceptance evidence задним числом: описать root cause, приложить безопасный лог, внести кодовый fix отдельным commit и повторить полный сценарий.
