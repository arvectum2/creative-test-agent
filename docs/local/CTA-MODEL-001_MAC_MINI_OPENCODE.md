# OpenCode ТЗ — CTA-MODEL-001 Production Local Model Profile

Каноническая задача: `CTA-MODEL-001`  
Issue: `#72`  
Рабочая ветка: `feat/cta-model-001`  
Контур: `LOCAL_IDE`  
Целевая машина: **Mac mini Apple M4 Pro, 24 GB unified memory**  
Основание: CTA-BENCH-002 revision `20260801-091536`.

## 0. Цель локальной части

Не проводить новый benchmark и не выбирать модели заново. Нужно превратить уже принятое решение CTA-BENCH-002 в воспроизводимый frozen production profile, доказать его через реальный application path и вернуть в GitHub только обезличенные конфиги, проверки и acceptance summary.

Основной результат:

```text
config/model_profiles/production/cta_model_001.mac_mini_m4pro_24gb.frozen.json
```

В Git разрешены только sanitized metadata, versions, revisions, sizes, limits, aggregate metrics и SHA-256. Запрещены model weights, cache files, реальные клиентские assets, raw client prompts/outputs, screenshots, DB, runtime logs и benchmark raw outputs.

## 1. Перед началом

1. Остановить все ранее запущенные `llama-server`, `mlx_vlm.server`, `mlx-openai-server`, Ollama/LM Studio model processes, если они используют те же порты/память.
2. Проверить чистоту процессов:

```bash
lsof -nP -iTCP:8091 -sTCP:LISTEN || true
lsof -nP -iTCP:8093 -sTCP:LISTEN || true
pgrep -af 'mlx_vlm|mlx-openai|app.cli|llama-server' || true
```

3. Обновить репозиторий и ветку:

```bash
git fetch origin
git checkout feat/cta-model-001
git pull --ff-only origin feat/cta-model-001
git status --short
```

Рабочее дерево до начала должно быть чистым. Не выполнять работу на старой benchmark branch.

4. Активировать основное окружение приложения и установить dev dependencies:

```bash
source .venv/bin/activate
python -m pip install -e '.[dev]'
```

5. Проверить GitHub preparation:

```bash
python scripts/cta_model_001.py validate \
  --mode draft \
  --profile config/model_profiles/production/cta_model_001.mac_mini_m4pro_24gb.draft.json

python -m pytest \
  tests/test_cta_model_001_profile.py \
  tests/test_model_profiles_openai_compatible_local.py -q
```

Ожидается PASS. При FAIL сначала исправить код/branch, не заполнять профиль поверх неисправной схемы.

## 2. Создать локальную рабочую копию

```bash
mkdir -p .local/cta-model-001
cp \
  config/model_profiles/production/cta_model_001.mac_mini_m4pro_24gb.draft.json \
  .local/cta-model-001/profile.filled.json
```

Редактировать `.local/cta-model-001/profile.filled.json`. Не менять draft так, чтобы скрыть ещё не измеренные поля.

## 3. Источник истины benchmark

Использовать локальную папку:

```text
artifacts/cta-bench-002/20260801-091536/
```

Проверить минимум:

```text
environment.json
integrity_manifest.json
SUMMARY.md
metric_integrity_audit.md
topology_results.json
process_cleanup_audit.csv
resource_samples.csv или эквивалентный resource artifact
candidates/VLM-MLX-4B/
candidates/LLM-MLX-4B/
```

Если файла нет, не угадывать значение. Зафиксировать gap в issue #72 и воспроизвести только недостающий measurement на том же frozen case pack без изменения cases/prompts/thresholds.

Рассчитать SHA-256 canonical integrity manifest:

```bash
shasum -a 256 artifacts/cta-bench-002/20260801-091536/integrity_manifest.json
```

Записать digest в `benchmark.artifact_manifest_sha256`.

## 4. Заполнить точную environment/runtime identity

### 4.1 Hardware / OS

```bash
sw_vers
uname -a
sysctl -n hw.model
sysctl -n machdep.cpu.brand_string
sysctl -n hw.memsize
```

Заполнить `target_hardware.os_version` и `target_hardware.os_build`. Не менять constants `Mac mini`, `Apple M4 Pro`, `24`.

### 4.2 Python и packages

Для VLM и LLM использовать ровно те Python environments, на которых выполнена acceptance. Не объединять окружения без отдельной проверки.

```bash
export CTA_VLM_PYTHON='<absolute path to accepted VLM python>'
export CTA_LLM_PYTHON='<absolute path to accepted LLM python>'

"$CTA_VLM_PYTHON" --version
"$CTA_LLM_PYTHON" --version

"$CTA_VLM_PYTHON" - <<'PY'
import importlib.metadata as m
for package in ('mlx', 'mlx-vlm'):
    print(package, m.version(package))
PY

"$CTA_LLM_PYTHON" - <<'PY'
import importlib.metadata as m
for package in ('mlx', 'mlx-lm', 'mlx-openai-server'):
    print(package, m.version(package))
PY
```

Заполнить `vision.runtime.version`, `vision.runtime.python_version`, `llm.runtime.version`, `llm.runtime.python_version`. В `runtime.version` записать server package + version в однозначном виде.

#### 4.2.1 LLM compatibility pin

Зафиксированный runtime-контракт LLM находится в:

```text
config/model_profiles/runtime/cta_model_001.llm.requirements.txt
```

Содержимое:

```text
mlx-openai-server==1.3.12
mlx-lm==0.31.3
```

Причина pin:

```text
mlx-lm==0.28.3 cannot load model_type=qwen3_5 and fails with:
ValueError: Model type qwen3_5 not supported
```

`mlx-openai-server==1.3.12` тянет `mlx-lm` транзитивно; без явного pin bootstrap может молча установить несовместимый `mlx-lm==0.28.3`. Поэтому LLM environment создаётся через exact requirements-файл, а не установкой `mlx-openai-server` отдельно.

Восстановление LLM environment:

```bash
"$CTA_LLM_PYTHON" -m pip install \
  -r config/model_profiles/runtime/cta_model_001.llm.requirements.txt
```

Verify установки:

```bash
"$CTA_LLM_PYTHON" - <<'PY'
import importlib.metadata as m

expected = {
    "mlx-openai-server": "1.3.12",
    "mlx-lm": "0.31.3",
}

errors = []
for package, version in expected.items():
    actual = m.version(package)
    print(package, actual)
    if actual != version:
        errors.append(f"{package}: expected {version}, got {actual}")

if errors:
    raise SystemExit("; ".join(errors))
PY
```

### 4.3 Model source revision и local hash

Для каждой Hugging Face model определить exact resolved commit SHA из cache metadata/snapshot path. Не использовать `main`, `latest` или дату вместо revision.

Заполнить:

```text
vision.model.source_revision
llm.model.source_revision
```

Рассчитать hash локальной model directory детерминированно, без symlink target ambiguity:

```bash
python - <<'PY'
from pathlib import Path
import hashlib
import os

for env_name in ('CTA_VLM_MODEL_DIR', 'CTA_LLM_MODEL_DIR'):
    root = Path(os.environ[env_name]).resolve()
    digest = hashlib.sha256()
    total = 0
    for path in sorted(p for p in root.rglob('*') if p.is_file()):
        relative = path.relative_to(root).as_posix().encode()
        digest.update(len(relative).to_bytes(8, 'big'))
        digest.update(relative)
        size = path.stat().st_size
        total += size
        digest.update(size.to_bytes(8, 'big'))
        with path.open('rb') as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                digest.update(chunk)
    print(env_name, root, digest.hexdigest(), total)
PY
```

Заполнить:

```text
vision.model.local_sha256
vision.model.disk_bytes
llm.model.local_sha256
llm.model.disk_bytes
```

Не коммитить absolute model paths; runtime command остаётся через explicit model ID и Python env var.

### 4.4 Tesseract

```bash
tesseract --version
tesseract --list-langs
```

Должны присутствовать `rus` и `eng`. Найти `rus.traineddata` и `eng.traineddata`, затем рассчитать один aggregate digest в фиксированном порядке имён и содержимого. Заполнить `ocr.version` и `ocr.language_data_sha256`.

## 5. Зафиксировать limits и topology без догадок

### 5.1 Context и image limits

Из accepted launch config/server capabilities и application constraints заполнить:

```text
vision.limits.context_tokens
vision.limits.max_image_bytes
vision.limits.max_image_pixels
llm.limits.context_tokens
```

Правила:

- `max_images_per_request=1` оставить;
- VLM `max_output_tokens=2048`, `temperature=0`, `seed=42` оставить, если именно это прошло accepted application path;
- LLM `max_output_tokens=4096`, `temperature=0.2` оставить, если это фактический app adapter acceptance;
- limit должен быть проверен реальным request, а не только заявлен server documentation;
- profile должен описывать product limit, который приложение реально соблюдает.

Если приложение сейчас не ограничивает bytes/pixels до request, добавить code guard + tests в эту ветку либо выбрать консервативный accepted product limit и явно проверить его.

### 5.2 Reconciliation `TOPOLOGY-U`

Benchmark summary называет выбранной `TOPOLOGY-U`, но full application-path E2E использовал два процесса: VLM 4B + LLM 4B.

Проверить implementation и artifacts, затем выбрать одно operational mode:

```text
single_multimodal_server
dual_server_resident
dual_server_sequential
```

Для текущего accepted E2E ожидаемый кандидат — `dual_server_resident`, но это не нужно ставить автоматически без проверки process/resource evidence.

Заполнить `topology.operational_mode`, `topology.reconciliation`, `topology.load_unload_policy`.

В reconciliation явно написать:

- что именно означает `TOPOLOGY-U` в benchmark harness;
- какой server выполняет visual extraction;
- какой server выполняет analytical stages;
- находятся ли оба resident одновременно;
- почему это не противоречит selected label;
- при каких условиях требуется sequential/manual fallback.

## 6. Заполнить measured resource envelope

Не переносить цифры из памяти или issue, если они не подтверждены artifact.

Заполнить:

```text
measured_envelope.cold_start_seconds
measured_envelope.warm_p50_seconds
measured_envelope.warm_p90_seconds
measured_envelope.warm_max_seconds
measured_envelope.peak_rss_bytes
measured_envelope.peak_memory_pressure
measured_envelope.swap_used_bytes
measured_envelope.disk_footprint_bytes
measured_envelope.concurrency_1_pass
measured_envelope.concurrency_2_pass
measured_envelope.shutdown_residual_processes
```

Уже зафиксированные benchmark constants не менять:

```text
visual_text_f1=0.731
visual_p95_seconds=5.2
structured_schema_valid_rate=0.941
end_to_end_wall_seconds=101.5
resident_headroom_fraction=0.564
```

Если raw artifact показывает другую единицу/агрегацию, остановиться и исправить schema/draft через отдельный commit с объяснением в PR. Не «подгонять» artifact к profile.

## 7. Заморозить профиль

Сначала проверить, что все `null` из обязательного local freeze списка заменены:

```bash
python scripts/cta_model_001.py seal \
  --profile .local/cta-model-001/profile.filled.json \
  --output .local/cta-model-001/profile.frozen.json

python scripts/cta_model_001.py validate \
  --mode frozen \
  --profile .local/cta-model-001/profile.frozen.json
```

Оба шага должны PASS.

Скопировать frozen profile в Git:

```bash
cp \
  .local/cta-model-001/profile.frozen.json \
  config/model_profiles/production/cta_model_001.mac_mini_m4pro_24gb.frozen.json
```

Проверить, что файл не содержит username/home path, tokens/API keys, client names/IDs/content, raw prompts/outputs, cache path или external endpoint.

## 8. Запустить production profile через CLI

### 8.1 Render application env

```bash
python scripts/cta_model_001.py render-env \
  --profile config/model_profiles/production/cta_model_001.mac_mini_m4pro_24gb.frozen.json \
  --output .local/cta-model-001/application.env

python scripts/cta_model_001.py check-env \
  --profile config/model_profiles/production/cta_model_001.mac_mini_m4pro_24gb.frozen.json \
  --env-file .local/cta-model-001/application.env
```

### 8.2 Start and identity gate

```bash
python scripts/cta_model_001.py start \
  --profile config/model_profiles/production/cta_model_001.mac_mini_m4pro_24gb.frozen.json

python scripts/cta_model_001.py status \
  --profile config/model_profiles/production/cta_model_001.mac_mini_m4pro_24gb.frozen.json

python scripts/cta_model_001.py preflight \
  --require-runtime \
  --profile config/model_profiles/production/cta_model_001.mac_mini_m4pro_24gb.frozen.json
```

Обязательное условие: `/v1/models` возвращает exact IDs из frozen profile. Alias, другой quantization или autodetect — FAIL.

## 9. Application-path acceptance

Загрузить `.local/cta-model-001/application.env` и запустить приложение только на loopback:

```bash
set -a
source .local/cta-model-001/application.env
set +a
uvicorn src.main:app --host 127.0.0.1 --port 8000
```

Проверить:

```bash
curl -fsS http://127.0.0.1:8000/health
curl -fsS http://127.0.0.1:8000/llm/health
curl -fsS http://127.0.0.1:8000/vision/health
```

Затем пройти три synthetic application-path cases из финальной CTA-BENCH-002 acceptance:

1. normal evidence;
2. missing/unreadable evidence;
3. conflicting/unsupported evidence.

Для каждого проверить:

- canonical `VisionResult` / evidence envelope;
- exact model metadata;
- schema valid или explicit fail-closed fallback;
- valid evidence refs;
- missing остаётся missing;
- unsupported CTA/logo/packshot не изобретаются;
- abstention/review_required сохраняются;
- Client Report v2 создаётся без validation errors;
- deterministic export создаётся и проходит integrity check.

Не использовать реальные клиентские assets для GitHub evidence. Реальный local smoke можно выполнить отдельно, но в issue дать только aggregate/sanitized результат.

## 10. Concurrency и resource replay

На frozen profile выполнить минимум:

- один cold start;
- warm-up, не включённый в scored cases;
- representative single request;
- `concurrency=2` с двумя независимыми representative requests;
- полный E2E normal case;
- shutdown.

Во время replay записать локально:

```bash
memory_pressure -Q
sysctl -n vm.swapusage
ps -o pid,ppid,rss,%cpu,command -p <PID>
```

Acceptance:

- `concurrency=1` PASS;
- `concurrency=2` PASS без cross-request contamination;
- нет critical memory pressure;
- swap не выходит за frozen envelope;
- model IDs не меняются;
- latency не выходит за frozen no-go threshold;
- no OOM/timeout/invalid output publication.

Если фактическая эксплуатация требует меньше concurrency, frozen profile должен быть изменён на `max_concurrency=1`, а причина записана. Нельзя оставить 2 только потому, что это максимум schema.

## 11. Stop / cleanup acceptance

```bash
python scripts/cta_model_001.py stop \
  --profile config/model_profiles/production/cta_model_001.mac_mini_m4pro_24gb.frozen.json

pgrep -af 'mlx_vlm|mlx-openai|app.cli' || true
lsof -nP -iTCP:8091 -sTCP:LISTEN || true
lsof -nP -iTCP:8093 -sTCP:LISTEN || true
```

Ожидается:

- CLI `STOPPED`;
- PID files удалены;
- 0 residual process groups;
- порты свободны;
- memory pressure вернулся к baseline.

Любой residual process — FAIL, даже если его можно удалить вручную.

## 12. Regression / CI

```bash
python -m compileall -q src scripts
python scripts/check_model_registry.py
python scripts/cta_model_001.py validate \
  --mode frozen \
  --profile config/model_profiles/production/cta_model_001.mac_mini_m4pro_24gb.frozen.json
python -m pytest \
  tests/test_cta_model_001_profile.py \
  tests/test_model_profiles_openai_compatible_local.py \
  tests/test_openai_compatible_local_provider.py \
  tests/test_vlm_analyzer_normalization.py \
  tests/test_pipeline_structured_recovery.py -q
make ci-check
```

Если full suite имеет pre-existing failures, повторить на чистом `origin/main` с тем же окружением и приложить controlled comparison. Новые failures запрещены.

## 13. Acceptance record

Создать:

```text
docs/acceptance/CTA-MODEL-001.md
```

Обязательные поля:

- verdict PASS/FAIL;
- main/base SHA и branch SHA;
- benchmark revision + artifact manifest SHA-256;
- frozen profile SHA-256;
- exact model IDs/source revisions/local hashes/quantization;
- exact runtime/Python/macOS versions;
- endpoints и ports;
- operational topology + reconciliation;
- limits/generation/timeouts/concurrency;
- cold/warm/resource/disk envelope;
- three-case application E2E result;
- report/export result;
- process cleanup result;
- targeted/full-suite result;
- no-client-data confirmation;
- claim boundary confirmation.

Не включать raw client content, home paths и logs.

## 14. GitHub завершение

1. Закоммитить только frozen profile, acceptance record, исправления кода/тестов и уточнённую документацию.
2. Push в `feat/cta-model-001`.
3. Обновить draft PR: exact results, commands, CI, local acceptance.
4. Добавить sanitized comment в issue #72.
5. Перевести PR из draft в ready только после PASS.
6. После green CI — merge.
7. Отдельным status close-out PR перевести CTA-MODEL-001 в `DONE`; controlled pilot остаётся blocked on client data.
8. Закрыть issue #72 только после merge implementation и status close-out.

## 15. Stop conditions

Остановиться и не замораживать профиль, если:

- exact model revision/hash недоступны;
- served model ID не совпадает;
- runtime слушает не loopback;
- operational topology нельзя однозначно объяснить;
- `concurrency=2` нестабилен при profile max_concurrency=2;
- memory/swap envelope не подтверждён;
- invalid output выходит из fail-closed boundary;
- после stop остаются процессы;
- для PASS нужно менять frozen benchmark cases или скрывать failures.
