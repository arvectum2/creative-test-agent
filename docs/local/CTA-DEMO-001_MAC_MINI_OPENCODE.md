# CTA-DEMO-001 — ТЗ для локальной проверки на Mac mini через OpenCode

## Цель

Закрыть последнюю acceptance gate задачи `CTA-DEMO-001`: пройти реальный Ozon end-to-end demo в браузере, сформировать report v2, проверить все артефакты и зафиксировать обезличенный результат без коммита клиентских файлов.

## Жёсткие ограничения

- Не коммитить и не прикладывать в GitHub реальные ZIP/XLSX, изображения, отчёты или screenshots с клиентскими данными.
- Не включать cloud LLM, внешние VLM, телеметрию или внешние API.
- Не менять evidence boundaries ради прохождения smoke test.
- Не заполнять missing значения вручную.
- Не закрывать issue #52 и не переводить roadmap в `DONE`, пока все обязательные проверки не пройдены.

## Подготовка

1. Открыть локальный репозиторий `creative-test-agent`.
2. Получить актуальный `main` после merge PR по CTA-DEMO-001.
3. Создать локальную рабочую ветку только при необходимости исправления дефекта; результаты smoke test сами по себе не требуют коммита.
4. Активировать обычное окружение проекта.
5. Убедиться, что реальные Ozon ZIP/XLSX и креативы находятся только в локальном storage/input каталоге, исключённом из Git.

## Проверка конфигурации

Перед запуском вывести и проверить без публикации секретов:

```bash
python - <<'PY'
from src.shared.config.settings import get_settings
s = get_settings()
print({
    "local_only_mode": s.local_only_mode,
    "allow_cloud_llm": s.allow_cloud_llm,
    "llm_provider": s.llm_provider,
    "vision_provider": s.vision_provider,
    "storage_root": s.storage_root,
    "database_url": s.database_url.split("@")[-1] if "@" in s.database_url else s.database_url,
})
PY
```

Обязательный результат:

- `local_only_mode = True`;
- `allow_cloud_llm = False`;
- используемые OCR/VLM/LLM — локальные или осознанный local stub для конкретного missing-state кейса;
- storage и DB указывают на локальные пути.

## Автоматические проверки

```bash
python -m pip install -e ".[dev]"
python -m compileall -q src scripts
python -m pytest tests/test_cta_demo_001.py -q
rm -rf .local/cta-demo-001-synthetic
python scripts/cta_demo_001.py self-test --output .local/cta-demo-001-synthetic
python scripts/cta_demo_001.py validate --input .local/cta-demo-001-synthetic
python scripts/cta_demo_001.py check-determinism
```

Ожидается: все команды завершаются с кодом 0.

## Запуск приложения

Использовать штатную команду проекта. Если применяется Uvicorn напрямую:

```bash
uvicorn src.main:app --host 127.0.0.1 --port 8000
```

Не слушать `0.0.0.0` для этой проверки.

## Найти реальный showcase project ID

1. Открыть `http://127.0.0.1:8000/ui/projects`.
2. Найти проект, в который локально загружен реальный Ozon showcase package.
3. Открыть Campaign Evidence Workspace.
4. Скопировать только UUID/ID проекта; он не является клиентским бинарным материалом, но не публиковать его без необходимости.

Альтернатива через локальный API:

```bash
curl --fail --silent "http://127.0.0.1:8000/campaign-evidence/projects/<PROJECT_ID>" \
  | python -m json.tool > .local/cta-demo-001-workspace-sanitized.json
```

Перед сохранением убедиться, что JSON не содержит чувствительных текстов, которые нельзя оставлять в `.local`.

## Реальный browser smoke test

Открыть:

```text
http://127.0.0.1:8000/ui/projects/<PROJECT_ID>/campaign-evidence/demo
```

### Шаг 1 — showcase project

Проверить:

- название проекта корректно;
- закрытый контур и cloud blocked видны в верхнем banner;
- normalization run и source fingerprint присутствуют в evidence references;
- нет ручного ввода UUID/JSON для дальнейшего сценария.

### Шаг 2 — campaign selection

Проверить минимум:

- один полный contrast case;
- один multi-asset/uncertain case;
- один rejected-link или missing-data case, если он есть в реальном наборе.

Для выбранной кампании сверить case ID, brand/product, platform и period с Campaign Evidence Workspace.

### Шаг 3 — original creative

Для полного кейса:

- preview открывается;
- filename соответствует локальному исходнику;
- linkage status/confidence совпадают с workspace;
- accepted-in-set не становится `yes` для rejected asset.

### Шаг 4 — visual extraction

Обязательно проверить:

- provider;
- extraction confidence;
- evidence confidence;
- completeness;
- fingerprint;
- минимум одно populated observation;
- у каждого populated observation показаны confidence, provenance и reference ID;
- unassessed/missing поля не отображаются как `absent`;
- low/limited evidence не превращается в уверенный вывод.

Если у всех реальных assets visual extraction отсутствует, acceptance не пройдена: сначала выполнить локальный visual pipeline либо зафиксировать реальный blocker.

### Шаг 5 — funnel diagnostics

Проверить:

- completed test run;
- overall score;
- effective recommendation;
- visual traceability status;
- visual decision status;
- scorecard/findings/risks не смешаны с factual outcomes;
- manual review/abstention показаны без смягчения формулировки.

### Шаг 6 — CG/TG

Проверить:

- значения CG, TG, descriptive delta и N совпадают с workspace/source;
- missing TG/CG остаётся `—`;
- рядом видны `causal_interpretation_allowed=false` и `individual_asset_outcome_attribution_allowed=false`;
- multi-asset case не получает asset-level outcome attribution.

### Шаг 7 — report v2

Нажать `Generate evidence-bound report v2`.

Проверить:

- после redirect показаны report ID, version, release status и manifest SHA-256;
- доступны HTML, one-page PPTX, full PPTX, DOCX, evidence JSON, XLSX и manifest;
- каждый download проходит без 404/409;
- повторное скачивание того же report не меняет SHA-256.

Открыть локально:

- HTML — Safari/Chrome;
- one-page и full PPTX — PowerPoint или LibreOffice;
- DOCX — Word или LibreOffice при масштабе 100%;
- XLSX — Excel/LibreOffice, проверить filters/wrap/evidence refs;
- evidence JSON и manifest — проверить `null` для missing и evidence references;
- manifest — сверить SHA-256 хотя бы одного артефакта командой `shasum -a 256 <file>`.

## Проверка отсутствия внешнего трафика

Минимум:

1. Во время demo убедиться, что конфигурация блокирует cloud providers.
2. Просмотреть application log: не должно быть вызовов OpenAI, Anthropic, Google, внешних OCR/VLM endpoints.
3. При наличии Little Snitch/LuLu выполнить повторный проход с запретом исходящих соединений для процесса Python и убедиться, что demo и report generation продолжают работать.

## Обязательный sanitized результат

Создать локально файл `.local/CTA-DEMO-001_REAL_SMOKE.md`:

```markdown
# CTA-DEMO-001 real-data smoke

Date/time:
Commit SHA:
Mac model / RAM:
Project: real Ozon showcase (ID redacted or shortened)
Local-only posture: PASS/FAIL

## Complete case
Case ID:
Preview: PASS/FAIL
Visual extraction: PASS/FAIL
Completed diagnostic: PASS/FAIL
CG/TG rows: PASS/FAIL

## Limitation cases
Multi-asset/uncertain: PASS/FAIL/NOT PRESENT
Rejected link: PASS/FAIL/NOT PRESENT
Missing value remains missing: PASS/FAIL/NOT PRESENT

## Report v2
Generation: PASS/FAIL
HTML: PASS/FAIL
One-page PPTX: PASS/FAIL
Full PPTX: PASS/FAIL
DOCX: PASS/FAIL
Evidence JSON: PASS/FAIL
XLSX: PASS/FAIL
Manifest/SHA-256: PASS/FAIL

External API traffic: NONE / FOUND
Defects found:
Final verdict: PASS / FAIL / BLOCKED
```

Не коммитить этот файл.

## Комментарий в issue #52

Добавить только обезличенный итог:

```text
CTA-DEMO-001 real-data smoke: PASS
Commit: <sha>
Environment: Mac mini, <RAM>, local-only
Complete contrast case: PASS
Visual extraction + refs: PASS
Diagnostics vs CG/TG separation: PASS
Limitation cases: PASS
Report downloads and visual inspection: PASS
External API traffic: none observed
Client files committed/uploaded: no
```

При `FAIL` или `BLOCKED` перечислить только технические симптомы, route/status code и sanitized identifiers. Не закрывать issue.

## Definition of done

После PASS:

1. issue #52 получает sanitized smoke comment;
2. roadmap меняется с `BLOCKED_LOCAL` на `DONE` отдельным небольшим PR;
3. acceptance document отмечает local checks;
4. issue #52 закрывается только после merge этого status PR.
