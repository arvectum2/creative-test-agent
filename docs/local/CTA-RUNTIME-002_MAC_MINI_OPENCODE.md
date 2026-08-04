# OpenCode ТЗ — CTA-RUNTIME-002 Graceful Shutdown Completion

Каноническая задача: `CTA-RUNTIME-002`  
Issue: `#78`  
Контур: `LOCAL_IDE / Mac mini`  
Целевая машина: **Mac mini Apple M4 Pro, 24 GB unified memory**  
Зависимость: завершённый `CTA-MODEL-001` и frozen profile  
Execution mode: `HYBRID`; GitHub-код принимается отдельно, финальный lifecycle gate выполняется здесь.

## 0. Цель локальной части

Подтвердить на реальном MLX-контуре, что один вызов `stop` завершает normal asynchronous shutdown без преждевременного `FAIL`.

Обязательный итог:

- `SIGTERM` отправлен один раз каждой принадлежащей профилю process group;
- процесс опрашивается до exit в пределах `graceful_shutdown_seconds`;
- `SIGKILL` не применяется до окончания grace period;
- после shutdown свободны `127.0.0.1:8091` и `127.0.0.1:8093`;
- PID files удалены только после фактического exit;
- `residual_process_count=0`;
- normal MLX lifecycle и delayed-shutdown regression проходят одним `stop`;
- model IDs, revisions, runtime versions и dependency pins CTA-MODEL-001 не изменены.

Это не новый benchmark и не повторный выбор моделей.

## 1. Запреты и границы

Не коммитить и не публиковать:

- model weights, Hugging Face cache и absolute local model paths;
- содержимое `.local/cta-model-001/`, PID files и runtime logs;
- реальные клиентские creatives, prompts, outputs, screenshots, DB и generated reports;
- raw process lists с username/home path;
- токены, ключи, cookies и environment dumps.

Разрешено вернуть в GitHub/issue только sanitized aggregate evidence: commit SHA, PASS/FAIL, durations, boolean lifecycle fields, ports, residual count и перечень выполненных команд без локальных путей.

## 2. Подготовка репозитория

Работать только после merge GitHub implementation PR CTA-RUNTIME-002.

```bash
git fetch origin
git checkout main
git pull --ff-only origin main
git status --short
git rev-parse HEAD
```

Рабочее дерево должно быть чистым.

Активировать application environment:

```bash
source .venv/bin/activate
python -m pip install -e '.[dev]'
```

Зафиксировать commit SHA локально в заметках, но не добавлять machine paths.

## 3. Проверить frozen runtime contract без изменений

```bash
PROFILE='config/model_profiles/production/cta_model_001.mac_mini_m4pro_24gb.frozen.json'

python scripts/cta_model_001.py validate --mode frozen --profile "$PROFILE"

python -m pytest \
  tests/test_cta_model_001_profile.py \
  tests/test_cta_model_001_runtime_dependencies.py \
  tests/test_cta_runtime_002_shutdown.py \
  tests/test_model_profiles_openai_compatible_local.py -q
```

Проверить exact LLM pins:

```bash
cat config/model_profiles/runtime/cta_model_001.llm.requirements.txt
```

Ожидается:

```text
mlx-openai-server==1.3.12
mlx-lm==0.31.3
```

Проверить, что frozen profile по-прежнему содержит:

```text
VLM: mlx-community/Qwen3-VL-4B-Instruct-4bit, port 8091
LLM: mlx-community/Qwen3.5-4B-MLX-4bit, port 8093
```

При любом drift остановиться. Не пересчитывать integrity hash и не «чинить» frozen profile в этой задаче.

## 4. Проверить accepted Python environments

Использовать те же окружения, что приняты CTA-MODEL-001:

```bash
export CTA_VLM_PYTHON='<accepted VLM python>'
export CTA_LLM_PYTHON='<accepted LLM python>'

"$CTA_VLM_PYTHON" --version
"$CTA_LLM_PYTHON" --version

"$CTA_VLM_PYTHON" - <<'PY'
import importlib.metadata as m
for package in ('mlx', 'mlx-vlm'):
    print(package, m.version(package))
PY

"$CTA_LLM_PYTHON" - <<'PY'
import importlib.metadata as m
expected = {
    'mlx-openai-server': '1.3.12',
    'mlx-lm': '0.31.3',
}
for package, wanted in expected.items():
    actual = m.version(package)
    print(package, actual)
    if actual != wanted:
        raise SystemExit(f'{package}: expected {wanted}, got {actual}')
PY
```

Absolute paths не копировать в issue или acceptance doc.

## 5. Предварительная очистка

Сначала попытаться штатный stop. Он должен быть идемпотентным для уже остановленного контура:

```bash
python scripts/cta_model_001.py stop --profile "$PROFILE" || true
```

Затем проверить:

```bash
lsof -nP -iTCP:8091 -sTCP:LISTEN || true
lsof -nP -iTCP:8093 -sTCP:LISTEN || true
pgrep -af 'mlx_vlm|mlx-openai|app.cli' || true
find .local/cta-model-001 -maxdepth 1 -name '*.pid.json' -print 2>/dev/null || true
```

До старта не должно быть listener на 8091/8093 и принадлежащих CTA process groups. Не удалять PID file вручную, если процесс ещё жив. При неизвестном listener выяснить владельца; runtime CLI не должен kill неизвестный процесс без PID ownership.

## 6. GitHub delayed-shutdown regression на Mac mini

Выполнить минимум 5 последовательных прогонов synthetic regression, который использует реальные process groups, loopback sockets, delayed SIGTERM handler и force-kill path:

```bash
for run in 1 2 3 4 5; do
  echo "CTA-RUNTIME-002 synthetic run $run"
  python -m pytest tests/test_cta_runtime_002_shutdown.py -q || exit 1
done
```

Обязательные проверки теста:

- delayed graceful process не вызывает premature failure;
- force-kill используется только после grace period;
- занятый порт без PID ownership завершается fail safe;
- stale PID record удаляется только после verified shutdown.

## 7. Реальный MLX lifecycle: три цикла

Для каждого цикла выполнить только один `stop`.

```bash
mkdir -p .local/cta-runtime-002

for run in 1 2 3; do
  echo "=== lifecycle $run ==="

  python scripts/cta_model_001.py start --profile "$PROFILE"
  python scripts/cta_model_001.py status --profile "$PROFILE"
  python scripts/cta_model_001.py preflight --require-runtime --profile "$PROFILE"

  python scripts/cta_model_001.py stop --profile "$PROFILE" \
    > ".local/cta-runtime-002/stop-$run.json"

  python - ".local/cta-runtime-002/stop-$run.json" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
if payload.get('status') != 'STOPPED':
    raise SystemExit(payload)
rows = payload.get('components') or []
if {row.get('component') for row in rows} != {'vision', 'llm'}:
    raise SystemExit(f'unexpected components: {rows}')
for row in rows:
    required = {
        'stopped': True,
        'residual': False,
        'residual_process_count': 0,
        'port_free': True,
        'pid_file_removed': True,
    }
    for key, wanted in required.items():
        if row.get(key) != wanted:
            raise SystemExit(f"{row.get('component')} {key}: {row.get(key)!r} != {wanted!r}")
print('verified', [(row['component'], row['elapsed_seconds'], row['force_kill_used']) for row in rows])
PY

  lsof -nP -iTCP:8091 -sTCP:LISTEN && exit 1 || true
  lsof -nP -iTCP:8093 -sTCP:LISTEN && exit 1 || true
  test ! -e .local/cta-model-001/vision.pid.json
  test ! -e .local/cta-model-001/llm.pid.json
  pgrep -af 'mlx_vlm|mlx-openai|app.cli' || true
done
```

Acceptance для каждого цикла:

- первый и единственный `stop` возвращает exit code 0;
- нет повторного `stop` для «дожидания»;
- обе строки имеют `stopped=true`;
- `residual_process_count=0`;
- `port_free=true` для 8091 и 8093;
- `pid_file_removed=true`;
- `force_kill_used=false` для normal path, если runtime штатно укладывается в 20 секунд.

Если normal MLX shutdown требует force-kill, это не автоматический FAIL при соблюдении grace period и нулевом residual, но результат отдельно зафиксировать как risk и не закрывать issue без анализа причины.

## 8. Delayed real-runtime scenario

После трёх normal cycles выполнить один controlled stop на прогретых моделях:

1. Запустить runtime.
2. Выполнить по одному synthetic smoke request к VLM и LLM, используя уже существующие CTA-MODEL-001 smoke-команды/fixtures. Не использовать клиентские данные.
3. Сразу после завершения smoke выполнить один `stop`.
4. Проверить тот же JSON contract, порты, PID files и residual count.

Команды start/stop:

```bash
python scripts/cta_model_001.py start --profile "$PROFILE"
# выполнить существующие synthetic VLM/LLM smoke из CTA-MODEL-001 runbook
python scripts/cta_model_001.py stop --profile "$PROFILE" \
  > .local/cta-runtime-002/stop-warm.json
```

Не добавлять artificial sleep между первым `stop` и проверкой. Цель — проверить, что сам CLI дожидается асинхронного завершения.

## 9. Полная локальная проверка

```bash
python -m compileall -q src scripts tests
python -m pytest tests/test_cta_runtime_002_shutdown.py -q
python -m pytest \
  tests/test_cta_model_001_profile.py \
  tests/test_cta_model_001_runtime_dependencies.py \
  tests/test_model_profiles_openai_compatible_local.py \
  tests/test_openai_compatible_local_provider.py \
  tests/test_vlm_analyzer_normalization.py \
  tests/test_pipeline_structured_recovery.py -q
make ci-check
```

Зафиксировать pass counts и список pre-existing failures, если full suite не полностью green. Новых failures от CTA-RUNTIME-002 быть не должно.

## 10. Проверка отсутствия утечек

```bash
git status --short
git diff --check
git ls-files .local || true
git diff --cached --name-only
```

Убедиться, что не staged:

```text
.local/**
*.pid.json
*.log
model weights/cache
client data
raw smoke outputs
absolute paths
```

Локальные JSON-файлы stop можно удалить после составления sanitized summary.

## 11. Формат sanitized evidence в issue #78

Добавить один комментарий:

```markdown
## CTA-RUNTIME-002 local Mac mini acceptance

- main commit: `<SHA>`
- machine: Mac mini Apple M4 Pro, 24 GB; macOS 26.6
- frozen profile validation: PASS
- exact runtime pins: PASS
- synthetic delayed-shutdown regression: 5/5 PASS
- real MLX normal lifecycle: 3/3 PASS with one stop per cycle
- warm/delayed lifecycle: PASS with one stop
- premature FAIL: 0
- ports after each stop: 8091 free, 8093 free
- PID files after each stop: removed
- residual process count after each stop: 0
- force-kill on normal path: `<0/3 or explain>`
- targeted tests: `<count>` PASS
- full CI/local suite: `<result>`
- client data/model weights/local paths/runtime logs committed: no

Claim boundary: lifecycle reliability only; no validated accuracy, causal lift or numeric-uplift claim.
```

Не вставлять raw `ps`, `lsof`, environment dumps или local paths.

## 12. Close-out после PASS

Только после успешного комментария:

1. Создать branch `docs/cta-runtime-002-closeout` от принятого `main`.
2. Обновить `docs/acceptance/CTA-RUNTIME-002.md`: status `DONE`, main SHA, sanitized local evidence.
3. В новой версии канонической roadmap заменить `CTA-RUNTIME-002` на `DONE`; исторический v2.2 не переписывать, если проект использует versioned roadmap policy.
4. Обновить `docs/roadmap/CURRENT.md`, top-level `ROADMAP.md` и Waiting-for-Data summary.
5. Создать status-only PR с `Closes #78`.
6. Дождаться CI и merge через squash.

До local PASS issue #78 остаётся open, а задача — `BLOCKED_LOCAL`, даже если GitHub implementation уже merged.

## 13. Stop conditions

Остановить close-out и оставить issue open, если выполнено хотя бы одно:

- первый `stop` возвращает `FAIL`, а повторный проходит;
- `SIGKILL` отправлен раньше завершения grace period;
- listener 8091 или 8093 остаётся;
- PID file удалён при живом PID/process group;
- residual process count больше 0;
- PID ownership mismatch;
- изменены frozen model identity, revisions или dependency pins;
- в Git попали local/client/runtime artifacts;
- появились новые regression failures.
