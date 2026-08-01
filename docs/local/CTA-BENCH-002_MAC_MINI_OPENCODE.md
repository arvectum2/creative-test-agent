# OpenCode ТЗ — CTA-BENCH-002 Target Hardware LLM/VLM/OCR Benchmark

Каноническая задача: `CTA-BENCH-002`  
Issue: `#68`  
Контур: `LOCAL_IDE`  
Целевая машина первой приёмки: **Mac mini Apple M4 Pro, 24 GB unified memory**  
Следующая зависимая задача: `CTA-MODEL-001 — Production Local Model Profile`

## 0. Исходное состояние, которое нельзя потерять

В репозитории уже есть рабочий локальный контур, поэтому задача не начинается «с чистого листа».

Подтверждённый baseline:

- реальный VLM-прогон `OZON-007` выполнен на `Qwen2.5-VL-7B-Instruct` через `llama.cpp`;
- используется OpenAI-compatible `/v1/chat/completions` adapter с base64 image transport;
- endpoint и приложение работают loopback-only;
- visual extraction проходит через canonical `VisualEvidenceEnvelope`, evidence references, traceability и abstention policy;
- доступны режимы `local_ocr`, `local_vlm`, `hybrid`;
- текущий OCR baseline — Tesseract/pytesseract;
- текущий LLM contour поддерживает `stub`, `ollama`, `lmstudio`; generic local OpenAI-compatible LLM profile может потребовать отдельного минимального adapter change;
- Gemma, установленная при предыдущей приёмке, была text-only и правильно отклонена multimodal gate.

**Обязательный baseline candidate:** существующий `Qwen2.5-VL-7B + llama.cpp` нельзя заменять до сравнения. Его результаты входят в итоговую таблицу наравне с MLX-кандидатами.

## 1. Цель

На одном frozen benchmark pack выбрать воспроизводимую конфигурацию для всего модельного контура агента:

1. OCR extraction;
2. VLM visual extraction;
3. LLM analytical stages и structured output;
4. OCR + VLM hybrid;
5. end-to-end deployment topology на 24 GB unified memory.

Итогом должен быть один из вариантов:

- выбранный production-candidate profile;
- разные кандидаты для `single-user demo` и `controlled pilot`;
- `no acceptable candidate` с измеренными причинами.

Результат нельзя называть validated production accuracy. Это hardware/runtime selection benchmark перед controlled pilot.

## 2. Почему MLX добавляется как обязательная ветка

Apple Silicon является целевой платформой первой установки. MLX должен быть проверен как нативный challenger, но **не объявляется победителем заранее**.

Из рекомендаций по MLX в protocol переносятся следующие правила:

- сравнивать server runtime отдельно от model quality;
- основная latency/throughput метрика — wall-clock, а не заявленный `tokens/sec`;
- TTFT учитывать только по первому непустому content token/chunk;
- минимум один raw SSE trace проверять вручную для каждого server candidate;
- model ID и quantization задавать явно; autodetect запрещён;
- после каждого прогона проверять и завершать дочерние/zombie model processes;
- дожидаться возврата memory pressure к baseline до запуска следующего candidate;
- single-request и `concurrency=2` измерять раздельно;
- большие модели, которые почти заполняют RAM только весами, не включать в основной 24 GB acceptance.

## 3. Жёсткие ограничения

- приложение и model endpoints слушают только `127.0.0.1`, `::1` или `localhost`;
- cloud fallback, external telemetry и внешние inference API отключены;
- реальные клиентские assets остаются локальными;
- не коммитить DB, weights, screenshots, previews, raw client outputs, server logs с client content или benchmark artifacts с client content;
- synthetic и real-local результаты хранить и агрегировать раздельно;
- failures/timeouts/OOM/invalid JSON включать в denominator;
- не менять frozen case set после начала comparison;
- не подбирать thresholds на финальном comparison set;
- не менять canonical `VisualEvidenceEnvelope`, traceability или abstention policy ради улучшения score;
- не запускать два Metal model runtimes одновременно без отдельного topology test;
- никакой кандидат не принимается только по скорости без quality, hallucination и schema compliance.

## 4. Обязательная матрица кандидатов

Названия ниже — стартовая матрица. OpenCode обязан зафиксировать exact versions, hashes и фактически доступные model IDs.

### 4.1 VLM candidates

| ID | Model/runtime | Роль |
|---|---|---|
| `VLM-BASE-LLAMA` | существующий `Qwen2.5-VL-7B-Instruct`, GGUF + mmproj, `llama.cpp` | обязательный proven baseline |
| `VLM-MLX-8B` | `mlx-community/Qwen3-VL-8B-Instruct-4bit`, `mlx-vlm.server` | основной MLX challenger |
| `VLM-MLX-4B` | `mlx-community/Qwen3-VL-4B-Instruct-4bit`, `mlx-vlm.server` | memory/latency fallback |

Допускается добавить 5/6/8-bit variant только отдельным candidate ID. Нельзя молча менять quantization между runs.

### 4.2 LLM candidates

| ID | Model/runtime | Роль |
|---|---|---|
| `LLM-CURRENT` | текущий фактически настроенный local LLM profile агента | обязательный application baseline |
| `LLM-MLX-9B` | `mlx-community/Qwen3.5-9B-MLX-4bit` | основной text-analysis challenger для 24 GB |
| `LLM-MLX-4B` | `mlx-community/Qwen3.5-4B-MLX-4bit` | low-memory/low-latency fallback |

Для `LLM-MLX-9B` основной server challenger — `mlx-openai-server`, поскольку необходимо отдельно проверить реальный batching и OpenAI-compatible behavior. `mlx_lm.server` допускается как official-reference control на той же модели, но не должен автоматически считаться production server.

Модели класса 30–35B не входят в основной acceptance на 24 GB. Они могут быть записаны только как `not feasible / research-only`, без скачивания и OOM-экспериментов, если по published size уже отсутствует безопасный memory headroom.

### 4.3 OCR candidates

| ID | Engine | Роль |
|---|---|---|
| `OCR-TESSERACT` | текущий Tesseract 5 + `rus+eng` | обязательный baseline |
| `OCR-CHALLENGER` | PaddleOCR/PP-OCRv5 mobile или другой локальный engine, реально устанавливаемый на этой машине | quality challenger |

Если challenger не устанавливается воспроизводимо на актуальном macOS/Python, это фиксируется как measured compatibility failure; Tesseract не получает победу автоматически.

### 4.4 Required execution modes

Минимум должны быть сравнены:

1. OCR-only baseline;
2. OCR-only challenger;
3. VLM baseline through llama.cpp;
4. VLM MLX 8B;
5. VLM MLX 4B;
6. OCR + VLM hybrid для минимум двух VLM candidates;
7. current LLM profile;
8. MLX LLM 9B;
9. MLX LLM 4B;
10. минимум две end-to-end topology.

## 5. Deployment topology, которую нужно выбрать

На 24 GB недостаточно выбрать модели по отдельности. Нужно измерить полный способ их эксплуатации.

### `TOPOLOGY-U — unified model`

Один VLM выполняет visual extraction и text analytical stages. Проверить качество text-only stages, structured JSON и общую latency без model switching.

### `TOPOLOGY-S — sequential dual model`

VLM выполняет extraction, затем освобождается; LLM загружается для analytical stages. Измерить unload/load time, полный wall-clock и отсутствие residual memory.

### `TOPOLOGY-R — resident dual model`

VLM и LLM остаются загруженными одновременно. Допускается только если:

- нет swap thrashing;
- memory pressure не становится критическим;
- оба runtime стабильны;
- latency не деградирует неприемлемо;
- процессы корректно останавливаются;
- есть минимум 20% фактического memory headroom на representative run либо иной явно обоснованный безопасный предел.

Основной результат должен сказать, какая topology подходит для:

- одиночной клиентской демонстрации;
- 1–2 одновременных пользователей controlled pilot;
- batch processing.

## 6. Phase 0 — inventory и compatibility gap

До скачивания новых моделей:

1. Checkout актуального `main` после merge документационного PR.
2. Создать рабочую ветку `feat/cta-bench-002` только если потребуется code/harness change.
3. Зафиксировать:
   - commit SHA;
   - macOS version/build;
   - Mac model;
   - M4 Pro CPU/GPU core count;
   - 24 GB unified memory;
   - текущий `iogpu.wired_limit_mb`, если доступен;
   - свободное место;
   - Python/uv versions;
   - Tesseract/OCR versions;
   - llama.cpp version/build;
   - MLX, mlx-lm, mlx-vlm и MLX server versions;
   - Ollama/LM Studio versions, если используются baseline;
   - model IDs, source revisions, local file hashes, quantization, context и image limits.
4. Сделать backup локальной DB и benchmark output root.
5. Проверить `.gitignore` для benchmark artifacts и model caches.
6. Найти CTA-VISION-001 harness, synthetic golden pack, manifests и accepted output schemas. Переиспользовать их.
7. Проверить, может ли текущий LLM `lmstudio` adapter безопасно работать с generic OpenAI-compatible local endpoint без ложной provider semantics.
8. Если нет — добавить минимальный provider `openai_compatible_local`:
   - loopback-only validation;
   - `/v1/models` health check;
   - `/v1/chat/completions`;
   - no API key requirement by default;
   - no cloud host;
   - explicit model ID;
   - tests and docs.
9. Не менять application adapter до direct server smoke. Сначала доказать, что server/model combination стабильно отвечает.

## 7. Frozen benchmark sets

### 7.1 Visual synthetic set

Создать immutable manifest с SHA-256. Включить:

- clean text-heavy creative;
- low-resolution/blur;
- mixed Russian/English;
- Cyrillic-heavy;
- no-text;
- dense layout;
- small disclaimer text;
- explicit CTA;
- assessed absence CTA/packshot/promo badge;
- logo prominence variants;
- message–visual mismatch;
- case, где корректное действие — abstain;
- multi-image or multi-page case в пределах поддерживаемого current product scope.

### 7.2 LLM synthetic set

Использовать реальные prompt contracts текущего pipeline, но с synthetic evidence. Включить:

- creative summary;
- audience simulation;
- rubric scoring;
- brand safety;
- brandbook compliance;
- final recommendation;
- unsupported visual evidence;
- missing data;
- conflicting evidence;
- Russian and mixed-language inputs;
- short, representative и maximum accepted request envelopes.

Для каждого case сохранить expected schema, forbidden claims, required evidence refs и allowed abstention state. Не создавать «gold prose», где допустимы несколько корректных формулировок.

### 7.3 Real-local set

При наличии согласованных Ozon/client assets:

- clean contrast case;
- dense layout;
- low-confidence visual case;
- Cyrillic-heavy case;
- multi-asset campaign case;
- case с factual campaign outcomes, которые нельзя атрибутировать individual asset.

Manifest может содержать только sanitized local IDs и SHA-256. Client names, image bytes и raw outputs в Git не публиковать.

После первого scored run set не менять. Изменение создаёт новую `benchmark_revision`.

## 8. Runtime launch protocol

Для каждого server candidate:

1. использовать отдельное environment/lockfile;
2. bind только на loopback;
3. задать exact model ID, без autodetect;
4. записать launch command в sanitized form;
5. проверить `/health` и `/v1/models`;
6. выполнить один tiny smoke без client data;
7. проверить model ID в server log;
8. выполнить benchmark;
9. отправить graceful shutdown;
10. после timeout завершить весь process group;
11. проверить отсутствие child/zombie process;
12. дождаться возврата memory pressure к baseline;
13. только затем запускать следующий candidate.

Если runtime не освобождает память, это отдельный acceptance defect, а не ручная мелочь.

## 9. Cold/warm и concurrency protocol

Для каждого candidate:

1. cold start после полного останова runtime;
2. model load time;
3. warm-up case, не входящий в scored set;
4. минимум три scored repetitions на synthetic set;
5. минимум два repetitions на real-local set;
6. fixed order или seeded permutation;
7. одинаковые timeout и output-token limits внутри comparison group;
8. single-request run как основной quality comparison;
9. отдельный `concurrency=2` run;
10. отдельный end-to-end topology run.

Для LLM context tiers измерять не абстрактные 50k prompts, а фактические serialized request envelopes current pipeline:

- `short`;
- representative median;
- representative p95;
- maximum accepted application request;
- optional 16k/32k stress только если это соответствует planned product profile.

## 10. Метрики и защита от ложных цифр

Записывать:

- request wall time;
- time to first **non-empty content**;
- total output tokens, если tokenizer/usage достоверны;
- wall tokens/sec;
- server-reported generation tokens/sec только как secondary metric;
- success/error/timeout/OOM/invalid-schema;
- request start offset и overlap ratio для concurrency;
- model load/unload time;
- peak RSS;
- system memory pressure и swap;
- CPU utilization;
- GPU utilization/allocated memory, где доступно;
- disk footprint;
- thermal/throttling observation.

Обязательные проверки metric integrity:

- минимум один raw SSE trace на candidate;
- пустой role chunk не считается первым token;
- non-streaming server не получает искусственно хороший TTFT/gen_tps;
- failures не удаляются из p50/p90 dataset — отдельно показываются success-only latency и all-attempt success rate;
- model name в response/log совпадает с candidate manifest;
- sample interval и measurement tools записаны.

## 11. OCR quality

Для каждого asset/engine:

- exact normalized text match;
- CER;
- WER, где meaningful;
- Cyrillic/Latin confusion;
- numbers, percent signs, prices, dosage/product strings;
- line/block order;
- small-print recall;
- invented text;
- confidence behavior;
- latency;
- preprocessing profile: resize, grayscale, threshold, orientation, deskew.

Original image и preprocessed image hashes должны быть связаны provenance. Нельзя вручную править OCR output перед scoring.

## 12. VLM quality

Для каждого asset/field:

- visual-summary factual support;
- OCR/detected text support;
- brand/logo prominence;
- packshot presence;
- CTA presence/text;
- promo badge;
- hierarchy;
- readability;
- cognitive load;
- message–visual binding;
- visual risks;
- field confidence;
- provenance/reference completeness;
- missing-versus-absent semantics;
- unsupported inference;
- invented logo/packshot/CTA/promo;
- correct abstention/review-required behavior;
- schema validation.

Не сводить всё к одному composite score без исходных dimensions.

## 13. LLM quality

На каждом pipeline stage считать:

- JSON/schema validity;
- repair/fallback count;
- evidence-reference validity;
- unsupported claim count;
- forbidden causal/numeric uplift claims;
- preservation of `missing`;
- correct use of abstention/review-required;
- rubric direction correctness;
- consistency between summary, scorecard and recommendation;
- Russian language quality;
- repeatability;
- truncation;
- stage latency;
- end-to-end report compatibility.

Structured output acceptance является hard gate. Быстрый model, который систематически требует repair или теряет evidence refs, не выбирается.

## 14. Hybrid OCR + VLM

OCR output передаётся в VLM как отдельный provenance-bound input. Raw image остаётся доступным VLM.

Проверить:

- улучшает ли OCR small text и Cyrillic extraction;
- переносит ли OCR errors в VLM findings;
- умеет ли VLM конфликтовать с OCR и abstain;
- сохраняются ли отдельные provenance для OCR и image observation;
- насколько hybrid увеличивает latency и memory;
- есть ли cases, где VLM-only лучше hybrid.

Manual correction между OCR и VLM запрещена.

## 15. Repeatability

Для каждого candidate сравнить repeated outputs:

- exact structured-output equality;
- normalized field stability;
- reference/fingerprint stability;
- confidence variance;
- recommendation/release-state variance;
- OCR text variance;
- timeout/error variance;
- response length variance.

Nondeterministic differences сохранять, а не усреднять молча. Temperature, seed, top-p и generation config фиксируются.

## 16. Integration acceptance

Для finalist candidates проверить через actual application path:

- output валидируется canonical schemas;
- `VisualEvidenceEnvelope` и source fingerprint создаются;
- populated observations получают references;
- unassessed `null` не получает false reference;
- assessed absence остаётся citable;
- unsupported finding abstains/requires review;
- missing extraction не снижает legacy creative score автоматически;
- LLM stages сохраняют evidence refs и forbidden-claim boundary;
- test-run storage/API сохраняют provenance;
- Campaign Evidence UI и Client Demo открывают result;
- Client Report v2 и deterministic exports формируются;
- current accepted `OZON-007` baseline не ломается;
- loopback-only и no-cloud checks проходят.

## 17. Автоматические проверки

До и после benchmark выполнить команды из актуального CI. Минимум:

```bash
python -m compileall -q src scripts tests
python scripts/check_model_registry.py
alembic upgrade head
```

Затем выполнить targeted tests для:

- LLM adapters/model profiles;
- local vision adapters;
- canonical visual context;
- full-pipeline propagation;
- traceability;
- abstention;
- campaign evidence;
- client demo;
- report v2;
- deterministic exports.

Если harness/adapters изменены — добавить regression tests, deterministic synthetic self-test и отдельный security test на rejection non-loopback URL.

## 18. Artifacts

Локальный ignored root:

`artifacts/cta-bench-002/<benchmark_revision>/`

Обязательные файлы:

- `environment.json`;
- `case_manifest_visual.json`;
- `case_manifest_llm.json`;
- `candidate_manifest.json`;
- `topology_manifest.json`;
- `runs.jsonl`;
- `ocr_field_metrics.csv`;
- `vlm_field_metrics.csv`;
- `llm_stage_metrics.csv`;
- `case_metrics.csv`;
- `resource_samples.csv`;
- `process_cleanup_audit.csv`;
- `metric_integrity_audit.md`;
- `summary.xlsx`;
- `SUMMARY.md`;
- `integrity_manifest.json`.

Real-local rows используют sanitized IDs/hashes. Raw client outputs, prompts with client content и logs не входят в publishable summary.

## 19. Decision gates

Кандидат или topology не может быть выбран, если:

- нарушает loopback-only;
- имеет cloud fallback/telemetry;
- фактически загружает не заявленную модель;
- ломает schema/provenance;
- систематически придумывает evidence;
- не abstains на unreadable/missing input;
- требует silent manual repair;
- нестабилен между repeated runs;
- оставляет zombie process или не освобождает память;
- вызывает persistent swap thrashing/critical memory pressure;
- не помещается в 24 GB с representative context/image load;
- latency делает demo/pilot workflow неприемлемым;
- concurrency corrupts/cross-contaminates responses;
- regression ломает текущий accepted llama.cpp contour.

Выбранный profile обязан содержать:

- exact OCR/VLM/LLM model IDs;
- exact runtime/server versions;
- quantization;
- context/image limits;
- topology;
- load/unload policy;
- timeout/concurrency;
- measured resource envelope;
- strengths and limitations;
- fallback behavior;
- explicit no-go cases.

## 20. Decision policy

Приоритеты решения:

1. evidence correctness и schema compliance;
2. hallucination/abstention safety;
3. stability/repeatability;
4. fit in 24 GB without destructive memory pressure;
5. end-to-end latency;
6. concurrency/throughput;
7. operational simplicity and packaging.

MLX выигрывает только при измеренном преимуществе. Существующий llama.cpp baseline сохраняется, если MLX не даёт достаточного quality/latency/resource improvement или создаёт operational risk.

Предварительная гипотеза для проверки, а не готовое решение:

- `Qwen3-VL-8B-Instruct-4bit + mlx-vlm` — основной VLM challenger;
- `Qwen3-VL-4B-Instruct-4bit` — fallback для resident topology;
- `Qwen3.5-9B-MLX-4bit` — основной LLM challenger;
- `Qwen3.5-4B-MLX-4bit` — fallback;
- `Qwen2.5-VL-7B + llama.cpp` — current proven baseline;
- Tesseract — baseline OCR, OCR challenger выбирается только после реального local compatibility smoke.

## 21. GitHub result

В Issue #68 опубликовать только sanitized summary:

- benchmark revision и commit SHA;
- exact hardware/runtime summary;
- candidate IDs;
- synthetic OCR/VLM/LLM metrics;
- отдельные aggregate real-local metrics;
- latency/resources;
- metric-integrity audit;
- process cleanup/memory release result;
- hallucination/abstention/repeatability;
- topology comparison;
- application integration PASS/FAIL;
- selected profile(s) или `no acceptable candidate`;
- known limitations;
- confirmation `no client data committed`.

Если code/harness/adapters исправлялись — открыть PR с tests и sanitized docs. Local raw artifacts не коммитить.

## 22. Критерий завершения

CTA-BENCH-002 становится `DONE`, когда:

1. сохранён и измерен существующий llama.cpp VLM baseline;
2. проверены MLX VLM 8B и 4B;
3. проверены current LLM, MLX LLM 9B и 4B;
4. сравнены минимум два OCR engines либо challenger зафиксирован как compatibility failure;
5. сравнены OCR-only, VLM-only и hybrid;
6. сравнены минимум две deployment topology;
7. frozen visual и LLM manifests сохранены;
8. synthetic и real-local evidence разделены;
9. quality/hallucination/abstention/schema/repeatability измерены;
10. cold/warm/single/concurrency latency измерены;
11. resource и process cleanup audit выполнены;
12. failures/timeouts/OOM включены в denominator;
13. canonical application integration проверена;
14. выбран profile или зафиксирован no-go;
15. sanitized result опубликован в Issue #68;
16. no client data committed подтверждено.
