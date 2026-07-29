# ТЗ: локальная приёмка CTA-OZON-001 на Mac mini через OpenCode

## 1. Цель

Развернуть **существующий GitHub-репозиторий** Creative Test Agent на Mac mini с нуля, не создавая отдельный новый проект, выполнить loader на реальных локальных `Ozon.zip` и `Test.xlsx`, подтвердить идемпотентность и зафиксировать smoke-test evidence в GitHub issue #45.

GitHub-часть задачи уже содержит loader, mapping, synthetic fixtures, tests и документацию. Локальная часть не должна переписывать решение заново: OpenCode используется для установки, запуска, диагностики и, только при выявленном дефекте, минимального исправления через отдельный PR.

## 2. Исходное состояние

На Mac mini:

- папка проекта ещё не создана;
- код локально отсутствует;
- единственный канонический источник кода — GitHub-репозиторий `arutyunoveth/creative-test-agent`;
- реальные ZIP/XLSX находятся или будут скопированы в локальную папку вне репозитория;
- реальные клиентские файлы запрещено добавлять в Git, PR, GitHub Actions artifacts или публичные логи.

## 3. Ожидаемый результат

После выполнения:

1. Репозиторий клонирован на Mac mini.
2. Создано Python-окружение и установлены зависимости.
3. Настроены отдельная локальная SQLite БД и storage вне Git-репозитория.
4. Реальные ZIP/XLSX проходят `--dry-run`.
5. Первый обычный запуск создаёт Ozon showcase project.
6. Второй идентичный запуск возвращает тот же `normalization_run_id` и `idempotent_reuse=true`.
7. В отчёте явно видны:
   - Relief platform mismatch;
   - Triderm without outcomes;
   - multi-asset campaign limitations;
   - отсутствие автоматического повышения uncertain/probable linkage до exact.
8. Полные synthetic tests проходят локально.
9. В issue #45 добавлен обезличенный smoke-test отчёт без клиентских бинарников.
10. Задача может быть переведена из `BLOCKED_LOCAL` в `DONE` только после проверки всех критериев.

## 4. Запреты

OpenCode не должен:

- выполнять `git init`;
- создавать второй независимый проект вместо clone;
- копировать код вручную из GitHub в новую папку;
- помещать реальные `Ozon.zip`, `Test.xlsx`, распакованные изображения, БД или storage внутрь репозитория;
- делать `git add -f` для игнорируемых файлов;
- коммитить `.env`;
- отправлять клиентские файлы в облачную модель или внешний API;
- менять linkage на `exact` ради прохождения приёмки;
- интерпретировать CG/TG difference как причинный uplift или прогноз;
- закрывать issue #45 до записи smoke-test evidence.

## 5. Подготовка Mac mini

### 5.1. Проверить инструменты

В Terminal:

```bash
xcode-select -p || xcode-select --install
git --version
python3 --version
```

Нужен Python 3.11 или новее. Если системный Python старее, установить актуальный Python через Homebrew:

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
brew install python@3.12
python3.12 --version
```

### 5.2. Создать рабочие каталоги

Рекомендуемая структура:

```text
~/Projects/creative-test-agent/        # только Git-репозиторий
~/CTA-local-data/ozon-input/           # реальные входные файлы
~/CTA-local-data/storage/              # immutable originals + extracted assets
~/CTA-local-data/reports/              # smoke-test JSON
~/CTA-local-data/creative_test_agent.db
```

Команды:

```bash
mkdir -p ~/Projects
mkdir -p ~/CTA-local-data/ozon-input
mkdir -p ~/CTA-local-data/storage
mkdir -p ~/CTA-local-data/reports
cd ~/Projects
```

## 6. Клонирование существующего проекта

Клонировать, а не создавать папку вручную:

```bash
git clone https://github.com/arutyunoveth/creative-test-agent.git
cd creative-test-agent
git status
git branch --show-current
```

Ожидается чистая ветка `main`.

Если private repository запрашивает авторизацию, использовать GitHub CLI или SSH, уже привязанные к аккаунту:

```bash
brew install gh
gh auth login
gh repo clone arutyunoveth/creative-test-agent ~/Projects/creative-test-agent
```

После clone:

```bash
cd ~/Projects/creative-test-agent
git pull --ff-only origin main
```

## 7. Открытие в OpenCode

Открыть **именно** `~/Projects/creative-test-agent` как workspace.

Стартовый промпт для OpenCode:

```text
Работаем в уже клонированном репозитории arutyunoveth/creative-test-agent.
Не выполняй git init и не создавай новый проект.
Задача — локальная приёмка CTA-OZON-001 по docs/local/CTA-OZON-001_MAC_MINI_OPENCODE.md.
Реальные Ozon.zip и Test.xlsx лежат вне репозитория в ~/CTA-local-data/ozon-input.
Не копируй их в репозиторий, не коммить бинарники, БД, storage, reports или .env.
Сначала только проверь окружение, установи зависимости, выполни dry-run, два обычных запуска, synthetic tests и собери обезличенный smoke-test summary.
При дефекте остановись, покажи причину и предложи минимальный patch в отдельной ветке; не меняй mapping uncertainty на exact.
```

## 8. Python-окружение

В корне репозитория:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e ".[dev]"
python --version
```

Ожидается Python `>=3.11`.

## 9. Локальная конфигурация

Создать `.env` из примера:

```bash
cp .env.example .env
```

Записать абсолютные пути текущего пользователя. Самый безопасный способ:

```bash
cat >> .env <<ENVVARS
CTA_DATABASE_URL=sqlite:///$HOME/CTA-local-data/creative_test_agent.db
CTA_STORAGE_ROOT=$HOME/CTA-local-data/storage
CTA_LOCAL_ONLY_MODE=true
CTA_ALLOW_CLOUD_LLM=false
CTA_LLM_PROVIDER=stub
CTA_VISION_PROVIDER=stub
ENVVARS
```

Проверить, что `.env` игнорируется:

```bash
git status --short
```

`.env` не должен появляться как tracked/untracked file.

> Для SQLite абсолютный URL на macOS имеет вид `sqlite:////Users/<user>/...`. Подстановка `$HOME` в приведённой команде даст правильный путь.

## 10. Размещение реальных файлов

Скопировать реальные файлы вне репозитория:

```text
~/CTA-local-data/ozon-input/Ozon.zip
~/CTA-local-data/ozon-input/Test.xlsx
```

Проверка:

```bash
ls -lh ~/CTA-local-data/ozon-input/Ozon.zip
ls -lh ~/CTA-local-data/ozon-input/Test.xlsx
```

Не распаковывать ZIP в репозиторий.

## 11. Pre-flight checks

```bash
source .venv/bin/activate
python -m pytest tests/test_ozon_showcase_loader.py -v
python scripts/load_ozon_showcase.py --help
```

Затем проверить рабочее дерево:

```bash
git status --short
```

Ожидается чистое дерево. Допустимы только локальные ignored-файлы, которые `git status` не показывает.

## 12. Dry-run на реальных данных

```bash
python scripts/load_ozon_showcase.py \
  --assets "$HOME/CTA-local-data/ozon-input/Ozon.zip" \
  --outcomes "$HOME/CTA-local-data/ozon-input/Test.xlsx" \
  --report "$HOME/CTA-local-data/reports/cta-ozon-001-dry-run.json" \
  --dry-run | tee "$HOME/CTA-local-data/reports/cta-ozon-001-dry-run-console.json"
```

Acceptance dry-run:

- exit code `0`;
- `status=ok`;
- `campaign_count=9`;
- `outcome_count=27` либо объяснимое число, если реальный workbook отличается от текущей calibration copy;
- `creative_asset_count=16` либо объяснимое число при другой версии архива;
- report JSON создан;
- нет записи в БД;
- source SHA-256 присутствуют;
- evidence boundaries фиксированы и false/true в соответствии с schema.

При отличии counts OpenCode не должен «подгонять» parser. Сначала вывести выбранный sheet/header/layout и доказать, какая версия файла загружена.

## 13. Первый load

```bash
python scripts/load_ozon_showcase.py \
  --assets "$HOME/CTA-local-data/ozon-input/Ozon.zip" \
  --outcomes "$HOME/CTA-local-data/ozon-input/Test.xlsx" \
  --report "$HOME/CTA-local-data/reports/cta-ozon-001-first.json" \
  | tee "$HOME/CTA-local-data/reports/cta-ozon-001-first-console.json"
```

Сохранить из stdout:

- `source_fingerprint`;
- `client_id`;
- `project_id`;
- `import_session_id`;
- `normalization_run_id`;
- counts;
- linkage counts;
- report path.

Ожидается `idempotent_reuse=false`.

## 14. Второй идентичный load

Повторить без изменений:

```bash
python scripts/load_ozon_showcase.py \
  --assets "$HOME/CTA-local-data/ozon-input/Ozon.zip" \
  --outcomes "$HOME/CTA-local-data/ozon-input/Test.xlsx" \
  --report "$HOME/CTA-local-data/reports/cta-ozon-001-second.json" \
  | tee "$HOME/CTA-local-data/reports/cta-ozon-001-second-console.json"
```

Acceptance idempotency:

- `idempotent_reuse=true`;
- `source_fingerprint` совпадает с первым запуском;
- `project_id`, `import_session_id`, `normalization_run_id` совпадают;
- counts не увеличились;
- source files не получили новые provenance records;
- локальные content-addressed blobs могут физически переиспользоваться.

Автоматическая проверка основных ID:

```bash
python - <<'PY'
import json
from pathlib import Path
root = Path.home() / "CTA-local-data/reports"
first = json.loads((root / "cta-ozon-001-first-console.json").read_text())
second = json.loads((root / "cta-ozon-001-second-console.json").read_text())
for key in ("source_fingerprint", "project_id", "import_session_id", "normalization_run_id"):
    assert first[key] == second[key], (key, first[key], second[key])
assert first["idempotent_reuse"] is False
assert second["idempotent_reuse"] is True
print("IDEMPOTENCY_OK")
PY
```

## 15. Проверка обязательных ограничений

```bash
python - <<'PY'
import json
from pathlib import Path
report = json.loads((Path.home() / "CTA-local-data/reports/cta-ozon-001-second.json").read_text())
codes = {item["code"] for item in report["limitations"]}
required = {
    "rejected_asset_link",
    "asset_without_outcomes",
    "campaign_multi_asset",
    "campaign_without_accepted_asset",
}
missing = required - codes
assert not missing, missing
assert report["evidence_boundaries"]["causal_interpretation_allowed"] is False
assert report["evidence_boundaries"]["numeric_uplift_prediction_generated"] is False
assert report["evidence_boundaries"]["uncertain_linkage_auto_promoted"] is False
print("LIMITATIONS_OK", sorted(codes))
PY
```

Ручная проверка report:

- Relief/VK отмечен `rejected`;
- у кампании Relief есть `campaign_without_accepted_asset`;
- Triderm отмечен `asset_without_outcomes`;
- Bepanthen, Rennie, Theraflex имеют `campaign_multi_asset`;
- Aerius не должен автоматически стать `exact` при неполной/противоречивой связке;
- `causal_interpretation_allowed=false`;
- `numeric_uplift_prediction_generated=false`.

## 16. Полная локальная регрессия

```bash
python -m pytest tests/ -v
make ci-check
```

Если полный `make ci-check` содержит платформенно-зависимый шаг, OpenCode должен:

1. зафиксировать точную failing command;
2. отдельно подтвердить `tests/test_ozon_showcase_loader.py`;
3. не объявлять полную приёмку зелёной;
4. открыть минимальный локальный fix PR только если это дефект кода, а не отсутствие внешнего инструмента.

## 17. Проверка отсутствия утечки в Git

```bash
git status --short
git ls-files | grep -Ei 'Ozon\.zip|Test\.xlsx|creative_test_agent\.db|CTA-local-data' && exit 1 || true
git check-ignore -v .env data/generated/ozon_showcase 2>/dev/null || true
```

Acceptance:

- реальные файлы не tracked;
- `.env` не tracked;
- БД, storage и reports находятся вне repo;
- рабочее дерево чистое, если patch не потребовался.

## 18. Обезличенный smoke-test summary

OpenCode должен подготовить Markdown без абсолютных пользовательских путей и без содержимого клиентских файлов:

```markdown
## CTA-OZON-001 local acceptance — Mac mini

- Repository commit: `<git rev-parse HEAD>`
- macOS / architecture: `<sw_vers -productVersion>` / `<uname -m>`
- Python: `<python --version>`
- ZIP SHA-256: `<hash>`
- XLSX SHA-256: `<hash>`
- Mapping SHA-256: `<hash>`
- Source fingerprint: `<fingerprint>`
- First run: `idempotent_reuse=false`
- Second run: `idempotent_reuse=true`
- Stable IDs: project/import-session/normalization-run — PASS
- Campaigns / outcomes / assets: `<counts>`
- Linkage counts: `<counts>`
- Relief mismatch visible: PASS
- Triderm missing outcomes visible: PASS
- Multi-asset limitations visible: PASS
- Uncertain/probable not promoted to exact: PASS
- Synthetic CTA-OZON-001 tests: PASS
- Full CI-equivalent local check: PASS / BLOCKED with exact reason
- Real binaries committed: NO
- Local report SHA-256: `<hash>`
```

Не вставлять:

- полные локальные пути пользователя;
- изображения;
- workbook rows;
- ФИО/контакты;
- contents ZIP/XLSX;
- `.env`.

## 19. Запись результата в GitHub

После успешной проверки добавить smoke-test summary комментарием в issue #45.

Если OpenCode имеет GitHub CLI:

```bash
gh issue comment 45 \
  --repo arutyunoveth/creative-test-agent \
  --body-file "$HOME/CTA-local-data/reports/cta-ozon-001-smoke-summary.md"
```

Issue закрывать только после подтверждения, что GitHub CI для implementation PR зелёный и локальные acceptance criteria выполнены.

## 20. Действия при дефекте

Если реальный package не загружается:

1. Не изменять реальные файлы.
2. Сохранить failing command и sanitized traceback.
3. Выполнить `--dry-run` с явным `--report`.
4. Проверить selected sheet/header/layout и source hashes.
5. Создать ветку от актуального `main`:

```bash
git switch main
git pull --ff-only origin main
git switch -c fix/cta-ozon-001-local-acceptance
```

6. Сделать минимальный parser/mapping/test patch.
7. Добавить synthetic regression, воспроизводящий дефект без клиентских данных.
8. Запустить полный test/CI набор.
9. Открыть PR, сославшись на issue #45, но не закрывая его до повторной local acceptance.

## 21. Финальные критерии DONE

CTA-OZON-001 переводится в `DONE`, когда одновременно выполнено:

- GitHub implementation PR merged;
- GitHub CI green;
- real ZIP/XLSX accepted locally;
- all source hashes/provenance present;
- second run creates no duplicates;
- Relief, Triderm, multi-asset and non-exact limitations remain explicit;
- JSON Data Quality/load report exists and is hashed;
- local synthetic/full checks recorded;
- issue #45 contains sanitized smoke evidence;
- no real client binary or secret is present in Git history.
