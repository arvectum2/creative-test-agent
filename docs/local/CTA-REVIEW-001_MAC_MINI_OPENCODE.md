# ТЗ для OpenCode — локальная приёмка CTA-REVIEW-001 на Mac mini

## Цель

Проверить на целевой локальной среде полный browser/operator flow finding-level expert review. Не изменять evidence boundaries и не коммитить реальные клиентские материалы, локальную БД, generated reports, screenshots с клиентскими данными, `.env`, токены или модели.

## 1. Ветка и окружение

```bash
cd <LOCAL_REPO_PATH>
git fetch origin
git checkout feat/cta-review-001
git pull --ff-only origin feat/cta-review-001
git status --short
git rev-parse HEAD

python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev]'
```

Обязательные ограничения:

```bash
export CTA_ENV=local
export CTA_HOST=127.0.0.1
export CTA_LOCAL_ONLY_MODE=true
export CTA_ALLOW_CLOUD_LLM=false
export CTA_LLM_PROVIDER=stub
export CTA_VISION_PROVIDER=stub
export CTA_SECURITY_FAIL_CLOSED=true
```

Существующие `CTA_DATABASE_URL` и `CTA_STORAGE_ROOT` не менять без необходимости. Если локальная SQLite БД содержит нужные данные, сделать backup до миграции.

## 2. Миграции и автоматические проверки

```bash
source .venv/bin/activate
alembic upgrade head
python scripts/check_model_registry.py
python -m compileall -q src scripts
python -m pytest tests/test_finding_reviews.py tests/test_client_report_v2.py -q
python -m pytest tests/ -q
```

Acceptance:

- Alembic доходит до `h7i8j9k0l1m2`;
- runtime/Alembic model registries совпадают;
- targeted tests проходят;
- полный suite не получает новых regressions; ранее существующие failures отделяются с точными командами и traceback.

## 3. Запуск

```bash
uvicorn src.main:app --host 127.0.0.1 --port 8000
curl -fsS http://127.0.0.1:8000/health
curl -fsS http://127.0.0.1:8000/version
```

Использовать только `http://127.0.0.1:8000` или `http://localhost:8000`. Внешние LLM/VLM API запрещены.

## 4. Подготовка данных

Использовать существующий локальный Ozon showcase/project с completed diagnostics либо approved synthetic fixture. Не вводить UUID и JSON вручную. Начинать путь из UI:

```text
Projects → project → Campaign Evidence → campaign → asset → finding
```

## 5. Browser acceptance — system finding

1. Открыть campaign evidence detail.
2. Убедиться, что findings показаны отдельными карточками с `Review finding`.
3. Открыть finding кнопкой, без ручного UUID/JSON.
4. Проверить наличие criterion/text, campaign/asset/test-run context, immutable SHA-256, review status и всех обязательных полей.
5. Сохранить revision 1, например `supported`, значения 1–5, severity correctness, confidence 0–1, role и rationale.
6. Сохранить revision 2 с другим decision/rationale.
7. Проверить, что revision 1 не изменилась, revision 2 ссылается на предыдущую, а campaign detail показывает latest decision и revision number.
8. Проверить длинные finding/rationale, keyboard navigation и ширины 1440/1024 px без перекрытий.

Нельзя обновлять или удалять существующую строку `finding_review`. Stale-hash сценарий выполняется только через штатное изменение/rerun system finding; если это невозможно без ручного SQL, отметить browser-check `NOT_APPLICABLE`, оставив automated test источником acceptance.

## 6. Browser acceptance — missed_by_system

1. На campaign detail нажать `Add missed finding`.
2. При необходимости выбрать asset.
3. Заполнить criterion, title, text, proposed severity, role, relevance, actionability, traceability, confidence и rationale.
4. Сохранить и открыть `Review history`.
5. Проверить:
   - decision=`missed_by_system`;
   - source kind=`human`;
   - system snapshot отсутствует;
   - human snapshot присутствует;
   - `system_finding_fabricated=false`.

## 7. Export acceptance

```bash
curl -fsS \
  'http://127.0.0.1:8000/finding-reviews/projects/<PROJECT_ID>/evidence.json' \
  -o /tmp/cta-review-001-evidence.json

curl -fsS \
  'http://127.0.0.1:8000/finding-reviews/projects/<PROJECT_ID>/calibration-package.zip' \
  -o /tmp/cta-review-001-calibration.zip

unzip -l /tmp/cta-review-001-calibration.zip
unzip -p /tmp/cta-review-001-calibration.zip package_manifest.json | python -m json.tool
unzip -p /tmp/cta-review-001-calibration.zip expert_review.csv | head -n 5
```

Проверить:

- evidence JSON содержит все revisions и human finding;
- system review содержит snapshot SHA-256;
- human finding не содержит system snapshot;
- ZIP содержит `finding_reviews_evidence.json`, `expert_review.csv`, `package_manifest.json`;
- manifest hashes соответствуют файлам;
- human omission экспортирован как `finding_origin=human_added`;
- в package нет бинарных клиентских assets.

## 8. Client report v2

```bash
python scripts/client_report_v2.py generate --project-id <PROJECT_ID> --locale ru
```

В evidence JSON report bundle проверить:

- latest persisted system reviews подхвачены как expert assessments;
- findings без review остаются `not_reviewed`;
- human omissions находятся в отдельном `human_findings` block;
- human omissions не подменяют agent diagnostics;
- release status остаётся `manual_review_required`, когда есть human omission или неполный review.

## 9. Permissions и isolation

При включённой auth:

- admin/manager/analyst может записывать review;
- viewer получает 403 на POST;
- finding/review другого project не открывается с подставленным project ID;
- export одного project не содержит reviews другого.

При отключённой auth отметить role-matrix browser check как `NOT_APPLICABLE`; automated contracts должны пройти.

## 10. Data safety

Во время проверки приложение и model runtime работают через loopback. Запрещено коммитить client assets, SQLite DB, generated JSON/ZIP/report, screenshots с клиентским content, секреты и модели. Разрешены только code/tests и обезличенный Markdown acceptance record.

## 11. Итог OpenCode

Создать `docs/acceptance/CTA-REVIEW-001_LOCAL.md`:

```markdown
# CTA-REVIEW-001 local acceptance

- Date/time:
- Mac/model/OS:
- Commit SHA:
- Project evidence class: real local / approved synthetic
- Overall verdict: PASS / FAIL / BLOCKED

## Commands and automated checks
| Check | Result | Evidence |

## Browser scenarios
| Scenario | Result | Notes |

## Export and report integration
| Check | Result | Notes |

## Security/data safety
| Check | Result | Notes |

## Defects found and fixes

## Remaining blockers

## Sanitized conclusion
```

Если всё прошло: изменить status в `docs/acceptance/CTA-REVIEW-001.md` на `DONE`, обновить canonical roadmap/status view и закрыть issue #61 только после push обезличенного acceptance record и зелёного CI. При блокере не ставить `DONE`; указать точную команду/route, ожидаемое и фактическое поведение.
