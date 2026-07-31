# OpenCode ТЗ — CTA-CAL-003 local acceptance on Mac mini

## Цель

Проверить Calibration Quality Dashboard в локальном закрытом контуре после GitHub implementation. Не изменять методологические определения и не добавлять реальные клиентские файлы в Git.

## 1. Подготовка

1. Checkout branch `feat/cta-cal-003` после синхронизации с актуальным dependency branch CTA-REVIEW-002.
2. Создать backup локальной SQLite DB и storage/export roots.
3. Зафиксировать commit SHA, Python version, OS, DB path и `CTA_LOCAL_ONLY_MODE`.
4. Убедиться, что приложение и local model endpoints слушают только loopback.

## 2. Automated checks

```bash
python -m compileall src tests scripts
python scripts/check_model_registry.py
alembic upgrade head
pytest tests/test_calibration_dashboard.py tests/test_finding_reviews.py -q
```

Затем выполнить полный regression suite и отдельно записать pre-existing unrelated failures, если они есть.

## 3. Migration replay

На копии DB:

1. `alembic upgrade j9k0l1m2n3o4`;
2. проверить таблицы `calibration_case_evidence`, `calibration_workflow_measurement` и indexes;
3. `alembic downgrade i8j9k0l1m2n3`;
4. повторно `alembic upgrade head`;
5. подтвердить сохранность остальных таблиц и finding review/adjudication evidence.

Нельзя выполнять destructive replay на единственной рабочей DB.

## 4. Browser acceptance

Открыть project page и перейти в `Calibration Quality Dashboard`.

Проверить:

- dashboard открывается без ручного UUID/JSON редактирования;
- девять metric cards читаемы без горизонтального переполнения основной страницы;
- каждый card показывает value или `—`, numerator/denominator, coverage и details;
- visible warning говорит, что это не validated accuracy;
- `all`, `real_client`, `synthetic`, `unclassified` дают разные case sets;
- case можно классифицировать и исключить/defer;
- excluded/deferred case исчезает из aggregate, но остаётся в DB/audit history;
- workflow form запрещает touch time больше wall-clock;
- valid measurement сохраняется один раз и видна в history;
- прямое UPDATE/DELETE append-only measurement отклоняется;
- finding with single review остаётся unresolved;
- active/stale disagreement виден как coverage gap;
- current adjudication даёт resolved assessment, но disagreement history не исчезает.

## 5. Export acceptance

Для неизменного evidence state дважды скачать JSON, XLSX и manifest.

Проверить:

- bytes JSON pair совпадают;
- bytes XLSX pair совпадают;
- SHA-256 header совпадает с локально рассчитанным hash;
- manifest sizes/hashes совпадают;
- XLSX открывается в Excel/LibreOffice/Numbers;
- sheets `Summary`, `Metrics`, `Cases`, `Claim Boundary` читаемы;
- real/synthetic filter отражён в Summary и rows;
- missing values остаются пустыми/`null`, а не нулями;
- claim boundary содержит false для accuracy, causal lift, prediction, threshold tuning и model selection.

## 6. Security and data boundary

1. Во время acceptance контролировать outbound network traffic.
2. Допустимы только loopback calls.
3. Проверить response headers `Cache-Control: no-store`, `X-Content-Type-Options: nosniff`.
4. Не коммитить DB, `-wal`, `-shm`, screenshots с client material, exports, local notes или model files.
5. `git status --short` после теста не должен показывать client evidence.

## 7. Sanitized acceptance record

Добавить в issue #65 только:

- commit SHA;
- PASS/FAIL;
- число targeted/full tests;
- migration replay result;
- browser checks result;
- deterministic export result;
- loopback/no-external-traffic result;
- перечень исправленных defects без client content;
- явное подтверждение `no client data committed`.

При defect: исправить в branch, повторить targeted acceptance и отметить предыдущий результат superseded.
