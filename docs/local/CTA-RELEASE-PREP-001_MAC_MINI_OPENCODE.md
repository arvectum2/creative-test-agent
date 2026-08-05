# OpenCode ТЗ — CTA-RELEASE-PREP-001 Local Acceptance

Каноническая задача: `CTA-RELEASE-PREP-001`  
Issue: `#83`  
Ветка: `feat/cta-release-prep-001`  
Целевая машина: Mac mini Apple M4 Pro, 24 GB unified memory  
Режим: `LOCAL_IDE` / synthetic only

## Цель

Принять on-premise release skeleton на чистой локальной среде: доказать воспроизводимость ZIP, безопасный состав, чистую установку, запуск закрытого контура, frozen model-profile lifecycle и исполнимый rollback.

## Жёсткие ограничения

- не использовать клиентские файлы и идентификаторы;
- не коммитить model weights, базы, логи, screenshots, env-файлы, локальные пути и acceptance artifacts;
- не менять frozen model identity, revisions или integrity hashes;
- не разрешать cloud fallback;
- не закрывать issue и не ставить `DONE`, пока GitHub CI и все локальные gates не PASS;
- не маскировать провалы повторным запуском без анализа причины.

## 1. Подготовка чистого worktree

```bash
git fetch origin
git worktree add ../cta-release-prep-001-clean origin/feat/cta-release-prep-001
cd ../cta-release-prep-001-clean
git status --short
git rev-parse HEAD
```

Рабочее дерево должно быть чистым. Зафиксировать SHA в sanitized evidence.

## 2. Базовая среда

```bash
python3.11 -m venv .venv-release
source .venv-release/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

Не использовать существующую project venv.

## 3. GitHub-equivalent checks

```bash
python -m compileall -q scripts/cta_release_prep_001.py scripts/cta_release_prep_001_clean_install.py
python scripts/check_code_health.py
python -m pytest tests/test_cta_release_prep_001.py -q -s
```

Ожидание: все проверки PASS, module/function budgets не нарушены.

## 4. Детерминированная сборка

```bash
REVISION="$(git rev-parse HEAD)"
rm -rf .local/cta-release-prep-001-a .local/cta-release-prep-001-b

python scripts/cta_release_prep_001.py --project-root . build \
  --output-dir .local/cta-release-prep-001-a \
  --source-revision "$REVISION"

python scripts/cta_release_prep_001.py --project-root . build \
  --output-dir .local/cta-release-prep-001-b \
  --source-revision "$REVISION"

shasum -a 256 .local/cta-release-prep-001-a/*.zip
shasum -a 256 .local/cta-release-prep-001-b/*.zip
cmp .local/cta-release-prep-001-a/*.zip .local/cta-release-prep-001-b/*.zip
```

Ожидание: ZIP byte-identical, SHA-256 одинаковый.

## 5. Статическая проверка пакета

```bash
BUNDLE=".local/cta-release-prep-001-a/creative-test-agent-onprem-0.1.0-rc1.zip"
python scripts/cta_release_prep_001.py --project-root . validate --bundle "$BUNDLE"
zipinfo -1 "$BUNDLE" > .local/cta-release-prep-001-file-list.txt
```

Проверить вручную:

- ровно один root directory;
- есть release manifest, SBOM, dependency export и SHA256SUMS;
- нет `.env`, `.env.server`, DB, logs, caches, artifacts, private keys и model weights;
- нет абсолютных путей пользователя;
- frozen profile включён как JSON reference, веса отсутствуют;
- `.env.onprem.example` сохраняет loopback, auth enabled и fail-closed flags.

## 6. Clean-machine synthetic install

```bash
mkdir -p artifacts/local-acceptance/CTA-RELEASE-PREP-001
python scripts/cta_release_prep_001_clean_install.py \
  --bundle "$BUNDLE" \
  --evidence artifacts/local-acceptance/CTA-RELEASE-PREP-001/clean-install.json
```

Ожидание в evidence:

- `status=PASS`;
- clean environment true;
- install-project PASS;
- manifest/SBOM/checksums validation PASS;
- compile, model registry, migrations, closed-loop, server readiness PASS;
- HTTP health smoke PASS;
- rollback backup/mutate/restore/verify PASS.

Проверить, что evidence не содержит секретов и абсолютных local paths.

## 7. Frozen production model gate

Использовать существующие отдельные runtime environments из frozen profile. Не устанавливать model runtime в application venv.

```bash
python scripts/cta_model_001.py validate --mode frozen
python scripts/cta_model_001.py start
python scripts/cta_model_001.py preflight --require-runtime
python scripts/cta_model_001.py status
```

Ожидание:

- VLM `mlx-community/Qwen3-VL-4B-Instruct-4bit` на `127.0.0.1:8091`;
- LLM `mlx-community/Qwen3.5-4B-MLX-4bit` на `127.0.0.1:8093`;
- exact model identity и source revision совпадают;
- profile internal SHA-256 `7796913472bb9de1f789c7a7ebaa0a0fab096c48f46e32580c107aab473c9698`;
- cloud fallback false.

## 8. Release-bundle runtime smoke с frozen models

Распаковать ZIP в новый временный каталог, создать новый application venv, скопировать `.env.onprem.example` в `.env.server`, заменить placeholder-секреты локальными случайными значениями и запустить приложение только на loopback.

Обязательный сценарий synthetic only:

1. открыть login;
2. войти bootstrap admin;
3. открыть UI;
4. создать/загрузить синтетический creative fixture;
5. выполнить один test run на frozen local models;
6. открыть result/report/history;
7. перезапустить приложение без потери результата;
8. проверить degraded path при остановленном model endpoint — запрос должен fail closed, без cloud fallback;
9. восстановить model runtime и повторить health.

Не сохранять screenshot с локальными путями или credential fields.

## 9. Shutdown gate

```bash
python scripts/cta_model_001.py stop
lsof -nP -iTCP:8091 -sTCP:LISTEN || true
lsof -nP -iTCP:8093 -sTCP:LISTEN || true
```

Ожидание:

- один stop call завершает оба owned process groups;
- force kill не применяется на нормальном пути;
- порты 8091/8093 свободны;
- PID files удалены;
- residual CTA model processes = 0.

Остановить application server и подтвердить освобождение его порта.

## 10. Sanitized evidence

Обновить `docs/acceptance/CTA-RELEASE-PREP-001.md` только агрегированными данными:

- worktree SHA;
- OS/architecture/Python versions без username/path;
- bundle SHA-256;
- число payload files и SBOM components;
- результаты GitHub-equivalent, deterministic build, clean install, rollback, frozen runtime, E2E/restart/degraded path, shutdown;
- отсутствие client data/secrets/model weights;
- GO/NO-GO.

Локальные raw artifacts оставить только в ignored `artifacts/local-acceptance/**`.

## 11. Завершение

Если есть дефекты:

1. исправить в той же ветке;
2. добавить regression test;
3. повторить все затронутые gates;
4. push;
5. дождаться зелёных targeted workflow и baseline CI.

После полного PASS:

- обновить PR body финальными доказательствами;
- добавить sanitized comment в issue #83;
- merge squash;
- отдельным status-only PR обновить canonical roadmap и закрыть issue #83.
