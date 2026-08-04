# OpenCode ТЗ — CTA-PILOT-PREP-003 Synthetic Controlled Pilot Rehearsal

Каноническая задача: `CTA-PILOT-PREP-003`  
Issue: `#82`  
Рабочая ветка: `feat/cta-pilot-prep-003`  
Контур: `LOCAL_IDE`  
Целевая машина: Mac mini Apple M4 Pro, 24 GB unified memory

## 0. Цель

Провести полную локальную репетицию controlled pilot на шести frozen synthetic cases через реальный browser workflow и принятый production local model profile. Подтвердить, что intake/DQ, blind freeze, независимый review/adjudication, dashboard, exports и runtime lifecycle работают вместе без утечки outcomes и без запрещённых claims.

Это не реальный `CTA-PILOT-003`: клиентские данные отсутствуют, поэтому реальный controlled-pilot path остаётся `BLOCKED_CLIENT`.

## 1. Безопасное начало

Не использовать текущую директорию, если в ней есть WIP. Не делать stash и не трогать существующие локальные изменения.

```bash
git fetch origin
git worktree add ../creative-test-agent-pilot-prep-003 \
  feat/cta-pilot-prep-003
cd ../creative-test-agent-pilot-prep-003
git status --short
git rev-parse HEAD
```

Ожидается чистое дерево и head ветки из PR задачи. До начала сохранить SHA в acceptance log.

```bash
source .venv/bin/activate
python -m pip install -e '.[dev]'
```

Проверить отсутствие посторонних model processes и занятых портов:

```bash
lsof -nP -iTCP:8091 -sTCP:LISTEN || true
lsof -nP -iTCP:8093 -sTCP:LISTEN || true
pgrep -af 'mlx_vlm|mlx-openai|llama-server|app.cli' || true
```

## 2. Stub gate до моделей

```bash
export CTA_DATABASE_URL='sqlite:///./.local/cta-pilot-prep-003.db'
export CTA_LOCAL_ONLY_MODE=true
export CTA_ALLOW_CLOUD_LLM=false
export CTA_ENABLE_AUTH=false
export CTA_LLM_PROVIDER=stub
export CTA_VISION_PROVIDER=stub

rm -f .local/cta-pilot-prep-003.db
mkdir -p artifacts/local-acceptance/CTA-PILOT-PREP-003/stub
python scripts/run_migrations.py
python scripts/check_migrations.py
python scripts/check_model_registry.py
python scripts/cta_pilot_prep_003.py validate \
  --fixture tests/fixtures/pilot_rehearsal/cases.json
python scripts/cta_pilot_prep_003_runtime.py \
  --fixture tests/fixtures/pilot_rehearsal/cases.json \
  --output-dir artifacts/local-acceptance/CTA-PILOT-PREP-003/stub
python -m pytest tests/test_cta_pilot_prep_003.py -q -s
```

Все команды должны завершиться PASS. Не переходить к model/browser gate при ошибке.

## 3. Запуск frozen production models

Использовать неизменённый профиль:

```text
config/model_profiles/production/cta_model_001.mac_mini_m4pro_24gb.frozen.json
```

```bash
python scripts/cta_model_001.py validate \
  --mode frozen \
  --profile config/model_profiles/production/cta_model_001.mac_mini_m4pro_24gb.frozen.json

python scripts/cta_model_001.py start \
  --profile config/model_profiles/production/cta_model_001.mac_mini_m4pro_24gb.frozen.json \
  --component all \
  --repository-root . \
  --wait-seconds 240

python scripts/cta_model_001.py preflight \
  --profile config/model_profiles/production/cta_model_001.mac_mini_m4pro_24gb.frozen.json \
  --require-runtime

python scripts/cta_model_001.py status \
  --profile config/model_profiles/production/cta_model_001.mac_mini_m4pro_24gb.frozen.json \
  --component all \
  --repository-root .
```

Ожидаются только loopback endpoints `127.0.0.1:8091` и `127.0.0.1:8093`, exact VLM/LLM identity и отсутствие cloud fallback.

## 4. Запуск приложения

Создать отдельную БД для browser rehearsal:

```bash
export CTA_DATABASE_URL='sqlite:///./.local/cta-pilot-prep-003-browser.db'
rm -f .local/cta-pilot-prep-003-browser.db
python scripts/run_migrations.py
```

Загрузить application settings строго из frozen profile существующим `render-env`/`check-env` процессом проекта. Запустить приложение на `127.0.0.1`, не на `0.0.0.0`. Записать точную команду запуска и PID в локальный acceptance log.

Перед первым кейсом открыть browser devtools Network и убедиться, что запросы идут только к loopback application/model endpoints. Внешняя телеметрия и cloud API запрещены.

## 5. Шесть сценариев через UI

Использовать значения из `tests/fixtures/pilot_rehearsal/cases.json`. Исходный fixture не редактировать.

### 5.1 Intake и Data Quality

Через project-scoped intake UI зарегистрировать все шесть кейсов и подтвердить:

- состояния соответствуют fixture;
- `SYN-MISSING-001` сохраняет linkage и metrics как missing;
- `SYN-RATE-ONLY-002` сохраняет counts как `null`;
- `SYN-MULTI-ASSET-002` остаётся `probable`, имеет два assets и не становится `exact`;
- DQ summary содержит шесть кейсов;
- repeated JSON export byte-identical и SHA-256 совпадает.

### 5.2 Frozen blind diagnostics

Для четырёх included cases:

1. Под ролью manager/admin создать sealed synthetic outcome envelope.
2. До freeze попытаться раскрыть outcome: ожидается блокировка.
3. Под ролью analyst выполнить реальный model diagnostic run с frozen prompt/model/code provenance.
4. Зафиксировать revision number и SHA-256 диагностического output, input provenance, prompt manifest, model profile, execution metadata и revision manifest.
5. Убедиться, что response/export не содержит outcome plaintext.
6. После freeze под manager/admin раскрыть outcome и подтвердить соответствие envelope.
7. Повторный запуск одного кейса должен создать revision `N+1`, а не изменить revision 1.

Не подменять model output fixture-ответом. Ошибка модели, timeout, invalid structured output или abstention должны остаться видимыми и не исправляться вручную задним числом.

### 5.3 Два независимых reviewer streams

Использовать две разные identities:

```text
Pilot Rehearsal Reviewer A
Pilot Rehearsal Reviewer B
```

Для каждого из четырёх findings ввести reviews независимо, не показывая второму reviewer ответ первого до сохранения его версии. Проверить append-only history и distinct reviewer subjects.

Обязательные результаты:

- normal: agreement;
- multi-asset: agreement с решением `needs_rewording`;
- conflicting: material disagreement;
- harmful-false-positive: material disagreement.

### 5.4 Adjudication

Третья identity с ролью manager/admin, не входящая в basis reviewers:

```text
Pilot Rehearsal Adjudicator
```

Разрешить два disagreements:

- conflicting → `partially_supported`;
- harmful-false-positive → `harmful_false_positive`.

Проверить basis review IDs/fingerprint, append-only adjudication и release boundary. Дополнительно создать новую review revision после одного adjudication: прежнее решение должно стать stale; затем вернуть кейс в актуальное состояние новой adjudication round. Этот negative test не должен менять frozen expected summary.

### 5.5 Human-added omission

На conflicting case создать отдельный `missed_by_system` human finding. Подтвердить:

- system finding snapshot отсутствует;
- omission не сливается с output агента;
- dashboard считает ровно один human-added finding.

### 5.6 Dashboard, timing и exports

Внести explicit operator measurements по fixture. Не вычислять touch time из audit timestamps.

Ожидаемые totals:

```text
wall_clock_seconds = 2940
operator_touch_seconds = 1260
manual_action_count = 34
```

Проверить dashboard с фильтром `synthetic`:

- harmful false positive count = 1;
- human-added finding count = 1;
- real/synthetic не смешаны;
- каждый metric показывает numerator, denominator, coverage и limitations;
- нигде нет утверждения о validated model accuracy;
- JSON и XLSX exports повторно генерируются byte-identically.

## 6. Browser usability и isolation

Проверить без ручного редактирования UUID/JSON:

- переходы project → pilot intake → blind revisions → finding review → adjudication → calibration dashboard;
- читаемость статусов missing/deferred/disagreement/stale;
- доступность export actions;
- отсутствие outcome plaintext в diagnostic pages до разрешённого reveal;
- URL другого synthetic project не раскрывает case/revision/review.

Скриншоты не коммитить. В GitHub acceptance разрешён только текстовый sanitized результат.

## 7. Evidence bundle и shutdown

Сохранить локальные evidence в ignored directory:

```text
artifacts/local-acceptance/CTA-PILOT-PREP-003/<timestamp>/
```

Минимальный состав:

```text
environment.txt
commands.log
stub-summary.json
browser-scenario-results.txt
model-identities.txt
workflow-metrics.json
export-hashes.txt
security-network-check.txt
shutdown-check.txt
sanitized-acceptance.md
```

Не включать raw prompts/outputs, model logs, screenshots, local DB, absolute model paths или client data.

Остановить runtime одним вызовом:

```bash
python scripts/cta_model_001.py stop \
  --profile config/model_profiles/production/cta_model_001.mac_mini_m4pro_24gb.frozen.json \
  --component all \
  --repository-root .
```

```bash
lsof -nP -iTCP:8091 -sTCP:LISTEN || true
lsof -nP -iTCP:8093 -sTCP:LISTEN || true
pgrep -af 'mlx_vlm|mlx-openai|llama-server' || true
```

Ожидается: оба порта свободны, PID files удалены, residual process count 0, normal-path force kill не использован.

## 8. Что вернуть в GitHub

После PASS:

1. Обновить `docs/acceptance/CTA-PILOT-PREP-003.md` только sanitized фактами.
2. Добавить комментарий в issue #82 с commit SHA, OS/Python, model profile identity/hash, browser scenario PASS/FAIL, totals, export hashes и shutdown result.
3. Не коммитить local evidence bundle.
4. Не закрывать реальный `CTA-PILOT-003` и не менять `CTA-PILOT-002` с `BLOCKED_CLIENT`.
5. Issue #82 и roadmap можно перевести в DONE только после зелёного GitHub CI и этого local gate.

## 9. Критерий PASS

PASS возможен только одновременно при выполнении всех условий:

- шесть synthetic scenarios пройдены;
- four included cases frozen до outcome reveal;
- no outcome leakage before freeze;
- missing values remain missing;
- no count reconstruction and no non-exact→exact promotion;
- two independent reviewers and independent adjudicator verified;
- two disagreements resolved, one harmful false positive and one separate omission captured;
- dashboard/report exports deterministic and claims bounded;
- loopback-only operation and no external calls confirmed;
- graceful shutdown leaves zero residual processes;
- no client data or local artifacts committed.
