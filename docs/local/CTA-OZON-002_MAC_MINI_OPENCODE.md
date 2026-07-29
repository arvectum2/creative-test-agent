# ТЗ: локальная приёмка CTA-OZON-002 на Mac mini через OpenCode

## 1. Цель

Проверить на реальной локальной базе Ozon, что GitHub-реализация `CTA-OZON-002 — Ozon Campaign Evidence Workspace` корректно показывает в браузере цепочку:

```text
campaign → creative set → observed CG/TG outcomes → asset-level agent diagnostics
```

Локальная часть не должна переписывать workspace заново. OpenCode используется для обновления уже клонированного репозитория, запуска приложения, браузерной проверки на реальных локальных данных и фиксации обезличенного smoke-test evidence в GitHub issue #48.

## 2. Исходное состояние

Предполагается, что после локальной приёмки `CTA-OZON-001` на Mac mini уже существуют:

- clone репозитория `~/Projects/creative-test-agent`;
- Python virtual environment `.venv`;
- локальный `.env`;
- SQLite database вне Git-репозитория;
- local storage с immutable ZIP/XLSX и извлечёнными изображениями;
- загруженный проект `Ozon Brand-Lift Showcase v1`;
- 9 campaigns, 27 observed outcomes и 16 creative records для текущей версии исходных файлов.

Если папка проекта отсутствует, OpenCode должен выполнить обычный `git clone`, а не `git init`. Реальные клиентские файлы, БД, storage, скриншоты с чувствительными данными и отчёты должны оставаться вне Git history.

## 3. Ожидаемый результат

После выполнения локальной части:

1. Mac mini работает на актуальном `main`, содержащем PR по CTA-OZON-002.
2. Targeted и полные offline tests проходят.
3. Приложение запускается в closed-loop режиме.
4. На странице реального Ozon проекта есть карточка `Campaign Evidence`.
5. Workspace открывается без ручного ввода UUID.
6. Campaign list показывает все реальные campaigns, funnel outcomes, creative links, confidence и warnings.
7. Theraflex, Rennie, Bepanthen и Supradyn Energy находятся в начале как contrast cases.
8. Campaign detail показывает фактические CG/TG outcomes отдельно от agent diagnostics.
9. Relief остаётся campaign with outcomes but without accepted Ozon creative.
10. Triderm остаётся asset without outcomes.
11. Multi-asset campaigns не получают individual-asset attribution.
12. Изображения загружаются из локального storage через protected preview endpoint.
13. Отсутствующий diagnostic отображается как explicit missing state.
14. Хотя бы один completed local diagnostic отображается рядом с неизменёнными factual outcomes.
15. В issue #48 добавлен обезличенный smoke-test summary.

## 4. Запреты

OpenCode не должен:

- выполнять `git init` в существующем clone;
- создавать второй независимый проект;
- копировать реальные `Ozon.zip`, `Test.xlsx`, SQLite DB или storage внутрь репозитория;
- делать `git add -f` для клиентских файлов;
- коммитить `.env`;
- отправлять изображения, workbook, prompts или diagnostics во внешний облачный API;
- включать `CTA_ALLOW_CLOUD_LLM=true`;
- изменять `rejected`, `missing`, `probable`, `one_to_many` или `uncertain` на `exact` ради красивой демонстрации;
- приписывать observed CG/TG difference конкретному banner;
- называть descriptive difference причинным brand lift;
- создавать numeric uplift prediction;
- заполнять отсутствующие значения догадками;
- закрывать issue #48 до завершения всех local acceptance checks.

## 5. Стартовый промпт для OpenCode

Открыть `~/Projects/creative-test-agent` и передать OpenCode:

```text
Работаем в уже клонированном репозитории arutyunoveth/creative-test-agent.
Не выполняй git init и не создавай новый проект.
Задача — локальная приёмка CTA-OZON-002 по docs/local/CTA-OZON-002_MAC_MINI_OPENCODE.md.
Используй существующие локальные SQLite DB и storage после CTA-OZON-001.
Не копируй и не коммить Ozon.zip, Test.xlsx, изображения, DB, storage, .env, браузерные профили или полные screenshots.
Не включай облачные LLM/VLM/OCR API.
Сначала проверь git state, environment, targeted tests, complete CI-equivalent suite и API evidence counts.
Затем запусти приложение, пройди browser smoke test, проверь contrast cases и evidence boundaries.
При дефекте остановись, сохрани минимальный воспроизводимый факт и предложи отдельный patch branch/PR. Не меняй linkage или исходные outcomes ради прохождения проверки.
```

## 6. Обновление существующего clone

```bash
cd ~/Projects/creative-test-agent
git status --short
git branch --show-current
git fetch origin
git switch main
git pull --ff-only origin main
git log -5 --oneline
```

Acceptance:

- активна ветка `main`;
- рабочее дерево чистое;
- в истории присутствует merge/commit CTA-OZON-002;
- локальные клиентские файлы не отображаются в `git status`.

Если рабочее дерево не чистое, OpenCode не должен выполнять `reset --hard` без анализа. Сначала вывести список локальных изменений и отделить пользовательскую работу от generated/ignored files.

## 7. Python environment

```bash
cd ~/Projects/creative-test-agent
source .venv/bin/activate
python --version
python -m pip install -e ".[dev]"
```

Нужен Python `>=3.11`.

Проверить closed-loop variables без вывода secrets:

```bash
python - <<'PY'
from src.shared.config.settings import get_settings
s = get_settings()
print({
    "database_url": s.database_url.split("@")[-1] if "@" in s.database_url else s.database_url,
    "storage_root": s.storage_root,
    "local_only_mode": s.local_only_mode,
    "allow_cloud_llm": s.allow_cloud_llm,
    "llm_provider": s.llm_provider,
    "vision_provider": s.vision_provider,
})
PY
```

Required:

- `local_only_mode=true`;
- `allow_cloud_llm=false`;
- database and storage point to the existing local Mac mini paths;
- no cloud provider is configured.

## 8. Pre-flight tests

Targeted checks:

```bash
python -m pytest tests/test_campaign_evidence_workspace.py -v
python -m pytest tests/test_ozon_showcase_loader.py -v
```

Full CI-equivalent checks:

```bash
make ci-check
```

Если `make ci-check` в проекте запускает только read-only/offline checks, он обязателен. Live PostgreSQL, network, Ollama или browser automation не должны внезапно становиться обязательными для default unit suite.

Acceptance:

- targeted tests pass;
- full default suite passes;
- tests do not read real Ozon files;
- tests do not perform network calls;
- working tree remains clean.

## 9. Найти реальный Ozon project ID

Не вводить UUID вручную из старых логов, если его можно определить из БД.

```bash
python - <<'PY'
from src.modules.projects.service import list_projects
for project in list_projects():
    if project.name == "Ozon Brand-Lift Showcase v1":
        print(project.id, project.name)
PY
```

Сохранить ID только в shell variable, не в tracked file:

```bash
export OZON_PROJECT_ID="<ID из команды>"
test -n "$OZON_PROJECT_ID"
```

## 10. API smoke test до запуска браузера

Запустить приложение в отдельном Terminal:

```bash
cd ~/Projects/creative-test-agent
source .venv/bin/activate
uvicorn src.main:app --host 127.0.0.1 --port 8000
```

В другом Terminal:

```bash
curl -fsS "http://127.0.0.1:8000/health" | python -m json.tool
curl -fsS "http://127.0.0.1:8000/campaign-evidence/projects/$OZON_PROJECT_ID" \
  > "$HOME/CTA-local-data/reports/cta-ozon-002-workspace.json"
```

Проверить обезличенные counts и boundaries:

```bash
python - <<'PY'
import json
from pathlib import Path
p = Path.home() / "CTA-local-data/reports/cta-ozon-002-workspace.json"
data = json.loads(p.read_text())
print("summary:", data["summary"])
print("case_ids:", [c["case_id"] for c in data["campaigns"]])
print("boundaries:", data["evidence_boundaries"])
assert data["evidence_boundaries"]["causal_interpretation_allowed"] is False
assert data["evidence_boundaries"]["numeric_uplift_prediction_generated"] is False
assert data["evidence_boundaries"]["individual_asset_outcome_attribution_allowed"] is False
assert data["evidence_boundaries"]["missing_values_inferred"] is False
assert data["evidence_boundaries"]["diagnostics_are_model_outputs_not_factual_outcomes"] is True
PY
```

Expected for the accepted real source version:

- `campaign_count=9`;
- `outcome_count=27`;
- `creative_count=16`;
- `unlabelled_asset_count=1` for Triderm;
- case IDs `OZON-001` through `OZON-009` are present;
- first contrast cases are `OZON-007`, `OZON-003`, `OZON-001`, `OZON-006`.

If counts differ, do not modify code immediately. Compare source fingerprint, mapping version and local loader acceptance report from CTA-OZON-001.

## 11. Browser smoke test

Open in a local browser:

```text
http://127.0.0.1:8000/ui/projects/<OZON_PROJECT_ID>
```

### 11.1 Project page

Verify:

- `Campaign Evidence` card is visible;
- click opens `/ui/projects/<project_id>/campaign-evidence`;
- no raw UUID needs to be typed after the project page is open.

### 11.2 Workspace list

Verify:

- top boundary notice separates facts from diagnostics;
- summary counts match the API;
- first cards are Theraflex, Rennie, Bepanthen, Supradyn Energy;
- each campaign card shows period/platform;
- CG/TG metrics retain their own funnel names;
- descriptive delta is marked as `Δ pp`, not forecast;
- creative records show filename, linkage status and confidence;
- diagnostic status is explicit;
- warnings are visible without opening raw JSON;
- Triderm appears in `Assets without campaign outcomes`.

### 11.3 Theraflex

Open Theraflex detail and verify:

- two accepted Ozon assets are visible;
- both remain `one_to_many`;
- `campaign_multi_asset` is visible;
- observed outcomes are campaign-level;
- `individual_asset_outcome_attribution_allowed=false` remains visible;
- no outcome is duplicated under an individual asset.

### 11.4 Rennie

Verify:

- accepted Ozon variants and rejected VK variants are distinguishable;
- mixed funnel outcomes remain separate, including purchase intent;
- rejected VK assets do not count as accepted campaign creatives;
- multi-asset warning remains visible.

### 11.5 Bepanthen

Verify:

- both formats remain visible;
- both retain `one_to_many`;
- no single banner is labelled the cause of the campaign result.

### 11.6 Supradyn Energy

Verify:

- one exact Ozon creative is visible;
- exact linkage does not change the general campaign-level outcome boundary;
- image preview opens locally;
- completed diagnostic is shown when one exists;
- factual rates do not change when diagnostics are present.

### 11.7 Relief

Verify:

- factual outcome rows are present;
- supplied VK creative is `rejected`;
- accepted creative count for the campaign is zero;
- `campaign_without_accepted_asset` and `rejected_asset_link` are visible;
- UI does not silently substitute another asset.

### 11.8 Triderm

Verify:

- appears only in the unlabelled-assets section;
- linkage status is `missing`;
- no fabricated campaign/outcome card is created;
- note explains that no outcome row exists.

## 12. Проверка image previews

For at least one exact asset and one multi-asset campaign:

1. Open the preview in a new tab.
2. Confirm HTTP `200` and correct image.
3. Confirm URL uses `/creative-assets/{asset_id}/image`.
4. Confirm the browser does not request an external image host.
5. Confirm the server log contains no upload or outbound API action.

Optional command-line check after copying one preview URL from page source:

```bash
curl -I "http://127.0.0.1:8000/creative-assets/<ASSET_ID>/image"
```

Expected content type: local `image/jpeg`, `image/png` or equivalent.

## 13. Проверка diagnostics

### 13.1 Existing completed diagnostics

If completed test runs already exist for Ozon assets, verify:

- each diagnostic is attached only to its own asset;
- overall score, findings, scorecard, risks and recommendation are model-output fields;
- visual traceability and decision states are visible;
- a diagnostic for one asset does not appear under another asset;
- campaign outcomes remain unchanged.

### 13.2 No completed diagnostics

A missing diagnostic is a valid source state, but the browser path must be exercised with at least one completed local diagnostic before final acceptance.

Use only local providers. Recommended minimum:

- one exact case: Supradyn Energy;
- one multi-asset case: one Theraflex asset, while confirming that the second asset remains separate.

Create and run tests through the existing UI or API. Do not create a synthetic campaign-level diagnostic. Do not run cloud providers. If local model execution is intentionally deferred, record the task as still `BLOCKED_LOCAL` and do not mark acceptance complete.

The purpose here is UI/evidence wiring, not production model selection or accuracy validation.

## 14. Responsive and visual QA

Check at desktop width and approximately 820 px width:

- no horizontal page overflow beyond metric tables;
- tables remain readable or scroll within their panel;
- previews preserve aspect ratio and are not cropped destructively;
- filenames wrap instead of breaking layout;
- fact and diagnostic panels stack on narrow screens;
- warning text remains readable;
- color is not the only indication of linkage state because status text is always shown.

Do not redesign unrelated global UI during this task.

## 15. Security and privacy verification

While the application is running:

```bash
lsof -i -n -P | grep -E 'python|uvicorn' || true
```

Expected:

- app listens only on `127.0.0.1:8000`;
- no unexpected outbound connection is initiated by the smoke test;
- `CTA_ALLOW_CLOUD_LLM=false`;
- real client binaries remain outside repo;
- browser developer tools show local preview requests only.

Check Git state:

```bash
cd ~/Projects/creative-test-agent
git status --short
git ls-files | grep -Ei 'Ozon\.zip|Test\.xlsx|cta-ozon-002-workspace\.json|creative_test_agent\.db' && exit 1 || true
```

## 16. Acceptance evidence for issue #48

Add only a sanitized text summary. Do not attach real creatives, workbook contents, DB, full API payload, source paths containing personal information, browser HAR, or screenshots that expose client data.

Template:

```markdown
## CTA-OZON-002 local acceptance — Mac mini

Date: YYYY-MM-DD
Commit: <main SHA>
Environment: macOS / Python <version> / SQLite / local-only

### Automated checks
- targeted campaign-evidence tests: PASS
- Ozon loader regression tests: PASS
- make ci-check: PASS

### Real workspace
- campaign_count: 9
- outcome_count: 27
- creative_count: 16
- unlabelled_asset_count: 1
- project page → workspace navigation: PASS
- local image previews: PASS
- factual CG/TG vs diagnostics separation: PASS

### Required cases
- Theraflex multi-asset limitation: PASS
- Rennie mixed/rejected variants visible: PASS
- Bepanthen multi-format limitation: PASS
- Supradyn Energy exact asset visible: PASS
- Relief rejected platform mismatch: PASS
- Triderm without outcomes: PASS
- explicit missing diagnostic state: PASS
- at least one completed local diagnostic rendered: PASS

### Evidence boundaries
- causal interpretation generated: NO
- numeric uplift prediction generated: NO
- missing values inferred: NO
- non-exact linkage promoted: NO
- real client binaries committed/transmitted: NO

Result: PASS / BLOCKED
Defects or follow-up: <none or issue/PR links>
```

## 17. Действия при дефекте

If a defect is found:

1. Stop the acceptance sequence.
2. Record the route, campaign ID/case ID, expected and actual state.
3. Determine whether the problem is source data, local environment, loader persistence, aggregation service or template/CSS.
4. Do not edit real DB records manually to hide the problem.
5. Create a minimal branch from current `main`:

```bash
git switch -c fix/cta-ozon-002-local-acceptance
```

6. Add only the minimal code/test/documentation patch.
7. Run targeted tests and `make ci-check`.
8. Open a separate PR linked to issue #48.
9. Repeat the affected browser smoke steps after merge.

## 18. Definition of Done

`CTA-OZON-002` may be moved from `BLOCKED_LOCAL` to `DONE` only when:

- GitHub PR is merged;
- CI is green;
- real project workspace opens from the project page;
- all expected real counts are verified or a source-version difference is documented;
- contrast cases render correctly;
- Relief and Triderm limitations remain explicit;
- multi-asset attribution remains blocked;
- local previews work;
- at least one completed local diagnostic is rendered beside unchanged factual outcomes;
- missing diagnostics remain explicit;
- closed-loop/security checks pass;
- sanitized acceptance evidence is posted to issue #48;
- no real client file or generated local artifact has entered Git history.
