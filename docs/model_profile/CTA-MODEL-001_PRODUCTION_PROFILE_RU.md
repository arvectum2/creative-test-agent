# CTA-MODEL-001 — Production Local Model Profile

Статус: `DONE`; runtime reliability follow-up `CTA-RUNTIME-002` выполняется отдельно  
Каноническая задача: `CTA-MODEL-001`  
GitHub issue: `#72`  
Целевое железо: **Mac mini Apple M4 Pro, 24 GB unified memory**  
Основание: CTA-BENCH-002, revision `20260801-091536`.

## 1. Что фиксирует профиль

Production Local Model Profile — это не рекомендация «какую модель попробовать», а строгий договор между:

1. принятым benchmark;
2. локальными runtime и весами;
3. переменными `CTA_*` приложения;
4. операторским запуском и остановом;
5. измеренным пределом ресурсов.

Профиль существует в двух состояниях:

- `draft` — версия в GitHub с известными решениями benchmark и явными `null` там, где точные значения доступны только на Mac mini;
- `frozen` — локально заполненный и SHA-256-связанный профиль без пропусков и placeholder-значений.

Файл схемы:

```text
config/model_profiles/production/cta_model_001.schema.json
```

Исходный draft:

```text
config/model_profiles/production/cta_model_001.mac_mini_m4pro_24gb.draft.json
```

## 2. Зафиксированный выбор benchmark

| Роль | Основной компонент | Runtime | Назначение |
|---|---|---|---|
| Visual extraction | `VLM-MLX-4B` / `mlx-community/Qwen3-VL-4B-Instruct-4bit` | `mlx_vlm.server` | Извлечение текста и наблюдаемых визуальных признаков |
| Analytical stages | `LLM-MLX-4B` / `mlx-community/Qwen3.5-4B-MLX-4bit` | `mlx-openai-server` | Structured analytical output и fail-closed pipeline |
| OCR fallback | Tesseract 5, `rus+eng` | in-process | Только ручной fallback, не основной hybrid path |
| VLM reference fallback | Qwen2.5-VL-7B GGUF + mmproj | `llama.cpp` | Ручная regression/reference проверка |

Принятый benchmark label — `TOPOLOGY-U`. При этом полный application-path acceptance использовал два loopback server process: `mlx_vlm.server` и `mlx-openai-server`. Поэтому frozen profile обязан явно зафиксировать operational mode и объяснить связь с benchmark label. Скрытая трактовка запрещена.

## 3. Запрещённые подмены

Без новой benchmark revision нельзя:

- менять model ID, quantization или runtime;
- включать OCR→VLM hybrid как основной путь;
- включать автоматический cloud fallback;
- заменять missing evidence предположением;
- публиковать invalid structured output вместо fail-closed fallback;
- повышать concurrency выше 2;
- называть профиль доказательством validated model accuracy, causal lift или numeric uplift prediction.

## 4. CLI

### Проверка draft

```bash
python scripts/cta_model_001.py validate \
  --mode draft \
  --profile config/model_profiles/production/cta_model_001.mac_mini_m4pro_24gb.draft.json
```

### Генерация `.env` приложения

```bash
python scripts/cta_model_001.py render-env \
  --profile <PROFILE_JSON> \
  --output .local/cta-model-001/application.env
```

### Проверка отсутствия drift

```bash
python scripts/cta_model_001.py check-env \
  --profile <FROZEN_PROFILE_JSON> \
  --env-file .local/cta-model-001/application.env
```

### Заморозка заполненного профиля

```bash
python scripts/cta_model_001.py seal \
  --profile .local/cta-model-001/profile.filled.json \
  --output .local/cta-model-001/profile.frozen.json

python scripts/cta_model_001.py validate \
  --mode frozen \
  --profile .local/cta-model-001/profile.frozen.json
```

`seal` нормализует JSON, фиксирует UTC timestamp и рассчитывает `integrity.profile_sha256`. Любое изменение frozen profile делает digest недействительным.

## 5. Runtime control

Runtime CLI не использует shell и не скачивает модели. Он запускает только command arrays из frozen profile, разрешая только whole-token ссылки `${CTA_VLM_PYTHON}` и `${CTA_LLM_PYTHON}`.

```bash
export CTA_VLM_PYTHON="$HOME/.venvs/cta-vlm/bin/python"
export CTA_LLM_PYTHON="$HOME/.venvs/cta-llm/bin/python"

python scripts/cta_model_001.py start --profile <FROZEN_PROFILE_JSON>
python scripts/cta_model_001.py status --profile <FROZEN_PROFILE_JSON>
python scripts/cta_model_001.py stop --profile <FROZEN_PROFILE_JSON>
```

Гарантии запуска:

- отдельная process group для каждого server;
- PID/log root только в `.local/cta-model-001/`;
- PID record привязан к component, process group и `integrity.profile_sha256`;
- model identity проверяется через `/v1/models` до допуска workload.

Гарантии остановки после `CTA-RUNTIME-002`:

1. Один вызов `stop` отправляет `SIGTERM` каждой принадлежащей профилю process group.
2. CLI опрашивает одновременно PID, process group и loopback-порт в течение всего `graceful_shutdown_seconds` либо до подтверждённого завершения.
3. `SIGKILL` используется только если после grace period остаётся PID, process group или занятый порт.
4. После force-kill CLI повторно ждёт `force_kill_seconds` и выполняет финальную проверку.
5. PID file удаляется только после подтверждённого exit, освобождения порта и нулевого residual process count.
6. Если PID record отсутствует, но профильный порт занят, CLI не пытается убить неизвестный процесс и завершает операцию с fail-safe ошибкой.

Успешный JSON-ответ для каждого component содержит минимум:

```text
stopped=true
residual=false
residual_process_count=0
port_free=true
pid_file_removed=true
graceful_signal_sent=true|false
force_kill_used=true|false
```

Повторный `stop` для уже остановленного component идемпотентен, если PID record отсутствует и порт свободен. При ownership mismatch PID record сохраняется, неизвестный процесс не сигнализируется.

Для `dual_server_sequential` команда `start --component all` запрещена: оператор должен явно запускать `vision` или `llm`.

Локальная приёмка lifecycle: `docs/local/CTA-RUNTIME-002_MAC_MINI_OPENCODE.md`.

## 6. Привязка к приложению

Frozen profile детерминированно задаёт:

```text
CTA_LOCAL_ONLY_MODE=true
CTA_ALLOW_CLOUD_LLM=false
CTA_VISION_PROVIDER=local_vlm
CTA_VISION_API_STYLE=openai_compatible
CTA_VISION_MODEL=mlx-community/Qwen3-VL-4B-Instruct-4bit
CTA_VISION_BASE_URL=http://127.0.0.1:8091
CTA_LLM_PROVIDER=openai_compatible_local
CTA_LLM_MODEL=mlx-community/Qwen3.5-4B-MLX-4bit
CTA_LLM_BASE_URL=http://127.0.0.1:8093/v1
CTA_LLM_TIMEOUT_SECONDS=240
CTA_VISION_TIMEOUT_SECONDS=240
```

Приложение использует root URL для VLM и `/v1` base URL для `openai_compatible_local` LLM adapter. Эти значения нельзя выравнивать «для красоты»: adapters формируют request paths по-разному.

## 7. Model profile registry

DB registry поддерживает `openai_compatible_local`:

- разрешены только loopback URL;
- требуется explicit model ID;
- health check вызывает `{base_url}/models`;
- reachability не считается PASS без совпадения served model ID;
- config loading выполняет idempotent upsert;
- ошибки загрузки возвращаются в API, а не скрываются.

Шаблон:

```text
config/model_profiles/cta-model-001-llm.example.json
```

## 8. Локальные артефакты и границы данных

Локально остаются:

- model weights и cache;
- absolute paths к Python environments и model directories;
- runtime PID/log files;
- raw benchmark и lifecycle logs;
- клиентские assets, prompts, outputs, screenshots, DB и generated reports.

В Git допустимы только sanitized versions, model identities, hashes, aggregate metrics, код, synthetic fixtures и обезличенная acceptance summary.
