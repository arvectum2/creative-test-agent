# OpenCode ТЗ — CTA-BENCH-002 Target Hardware OCR/VLM Benchmark

Каноническая задача: `CTA-BENCH-002`  
Issue: `#68`  
Контур: `LOCAL_IDE`  
Целевая среда: Mac mini / фактическое клиентское железо

## Цель

На одном frozen benchmark set сравнить минимум три режима визуального извлечения и выбрать воспроизводимый кандидат для `CTA-MODEL-001 — Production Local Model Profile`:

1. OCR-only;
2. VLM-only;
3. OCR + VLM hybrid.

Решение принимается по измеренным quality, hallucination, abstention, repeatability, latency и resource metrics. Нельзя заменять измерения предположениями или называть результат validated model accuracy.

## Жёсткие ограничения

- приложение и model endpoints слушают только loopback;
- cloud fallback, external telemetry и внешние inference API отключены;
- реальные клиентские assets остаются локальными;
- не коммитить DB, weights, screenshots, previews, raw client outputs или benchmark artifacts с client content;
- synthetic и real-local результаты хранить и агрегировать раздельно;
- failures/timeouts включать в denominator;
- не подбирать thresholds на том же наборе, который используется как финальный comparison set;
- не менять canonical `VisualEvidenceEnvelope`, traceability или abstention policy ради улучшения benchmark score.

## 1. Подготовка

1. Checkout актуального `main` после merge PR #67.
2. Создать рабочую ветку `feat/cta-bench-002`, если потребуется исправление harness/docs.
3. Зафиксировать:
   - commit SHA;
   - macOS и architecture;
   - Mac model / CPU / GPU cores;
   - total RAM;
   - свободное место;
   - Python/runtime versions;
   - llama.cpp/MLX/OCR runtime versions;
   - model IDs, file hashes, quantization, context size и image limits.
4. Создать backup локальной DB и benchmark output root.
5. Проверить `.gitignore` для benchmark artifacts.
6. Найти и изучить существующие CTA-VISION-001 harness, synthetic golden pack, manifests и accepted output schemas. Переиспользовать их, а не создавать параллельный несовместимый формат.

## 2. Frozen case set

Сформировать immutable manifest с SHA-256 для:

### Synthetic set

- canonical synthetic creative golden pack;
- минимум один clean text-heavy case;
- минимум один low-resolution/blur case;
- минимум один mixed Russian/English case;
- минимум один no-text case;
- минимум один case с assessed absence CTA/packshot/promo badge;
- минимум один case, где корректное действие — abstain.

### Real-local set

При наличии согласованных локальных Ozon/client assets:

- один clean contrast case;
- один dense layout;
- один low-confidence linkage/visual case;
- один multi-asset case;
- один Cyrillic-heavy case.

Real-local manifest может содержать только local IDs и hashes. Ни image bytes, ни client names в Git не публиковать.

После начала comparison не менять case set. Любое изменение создаёт новую benchmark revision.

## 3. Режимы

### A. OCR-only

Использовать наиболее зрелый локально доступный OCR engine из существующей конфигурации проекта. Зафиксировать preprocessing, language packs, orientation/deskew и confidence behavior.

### B. VLM-only

Использовать текущий локальный VLM profile, совместимый с OpenAI-style adapter проекта. Зафиксировать model hash, quantization, context, image resolution и prompt version.

### C. Hybrid

OCR output передаётся в VLM как отдельный provenance-bound input; raw image остаётся доступным VLM. Нельзя скрыто заменять OCR/VLM outputs вручную.

Дополнительные модели или quantizations допускаются отдельными candidate IDs.

## 4. Cold/warm protocol

Для каждого candidate:

1. cold start после полного остановa runtime;
2. warm-up asset, не входящий в scored set;
3. минимум три повторных scored run на synthetic set;
4. минимум два повторных run на real-local set, если он используется;
5. фиксированный порядок либо детерминированная seeded permutation;
6. одинаковые timeouts и concurrency в основном comparison;
7. отдельный throughput run можно делать после single-request comparison.

Записывать startup time, first-token/first-result latency, total latency и timeout/error type.

## 5. Quality dimensions

Для каждого asset/field фиксировать:

- OCR text exact/normalized match и character/word errors, где reference существует;
- visual-summary factual support;
- brand/logo prominence;
- packshot detection;
- CTA detection/text;
- promo badge;
- hierarchy;
- readability;
- cognitive load;
- message–visual binding;
- extraction confidence;
- provenance/reference completeness;
- unsupported inference;
- correct missing-versus-absent semantics;
- correct abstention/review-required behavior.

Не сводить всё к одному composite score без показа исходных dimensions.

## 6. Hallucination и abstention

Отдельно считать:

- unsupported populated fields;
- invented OCR text;
- invented logo/packshot/CTA/promo;
- unsupported diagnostic observations;
- missed required abstention;
- excessive abstention при достаточном evidence;
- invalid/missing trace references;
- cases, где confidence не соответствует evidence quality.

Manual audit выполняется blind к candidate name, где это практически возможно.

## 7. Repeatability

Для каждого candidate сравнить повторные outputs:

- exact structured-output equality;
- normalized field stability;
- reference/fingerprint stability;
- confidence variance;
- recommendation-state variance;
- OCR text variance;
- timeout/error variance.

Nondeterministic differences сохранять, а не усреднять молча.

## 8. Resources

Измерить и записать:

- peak RSS;
- system RAM pressure/swap;
- GPU utilization и allocated memory, если доступно;
- CPU utilization;
- model load time;
- disk footprint;
- per-asset latency p50/p90/max;
- batch throughput;
- energy/thermal throttling observations, если доступны штатными средствами.

Resource sampling interval и tools должны быть указаны в report.

## 9. Integration acceptance

Для каждого финального candidate проверить:

- output валидируется canonical schema;
- `VisualEvidenceEnvelope` и source fingerprint создаются;
- populated observations получают references;
- unassessed `null` не получает ложный reference;
- assessed absence остаётся citable;
- unsupported finding abstains/requires review;
- missing extraction не снижает legacy creative score автоматически;
- test-run storage/API сохраняют provenance;
- Client Demo и Campaign Evidence UI открывают result;
- report generation не ломается.

## 10. Автоматические проверки

До и после benchmark выполнить canonical compile/model-registry/migration checks и targeted visual tests. Точные команды определить из актуальных CI workflows и CTA-VISION-001 docs.

Минимум:

```bash
python -m compileall -q src scripts tests
python scripts/check_model_registry.py
alembic upgrade head
```

Затем выполнить существующие visual-context, traceability, abstention, campaign-evidence, client-demo и report-v2 targeted tests.

Если harness изменён — добавить regression tests и отдельный deterministic synthetic self-test.

## 11. Artifacts

Локальный ignored root:

`artifacts/cta-bench-002/<benchmark_revision>/`

Обязательные файлы:

- `environment.json`;
- `case_manifest.json`;
- `candidate_manifest.json`;
- `runs.jsonl`;
- `field_metrics.csv`;
- `case_metrics.csv`;
- `resource_samples.csv`;
- `summary.xlsx`;
- `SUMMARY.md`;
- `integrity_manifest.json`.

Real-local rows должны использовать sanitized local IDs/hashes. Raw client outputs не включать в публикуемый sanitized summary.

## 12. Decision rule

Кандидат не может быть выбран, если:

- нарушает loopback-only;
- имеет silent cloud fallback;
- ломает canonical schema/provenance;
- систематически придумывает evidence;
- не abstains на unreadable/missing inputs;
- нестабилен между повторными runs;
- не помещается в доступную память;
- latency делает клиентскую демонстрацию или pilot workflow практически неприемлемыми.

Выбранный candidate должен иметь:

- measured strengths;
- measured limitations;
- recommended use cases;
- fallback behavior;
- resource envelope;
- explicit no-go cases.

Допустимый итог: `no acceptable candidate`.

## 13. GitHub result

В Issue #68 опубликовать только sanitized summary:

- benchmark revision и commit SHA;
- hardware/runtime summary;
- candidate IDs без локальных secrets/paths;
- synthetic metrics;
- отдельные aggregate real-local metrics, если разрешено;
- latency/resources;
- hallucination/abstention/repeatability;
- integration PASS/FAIL;
- selected candidate или `no acceptable candidate`;
- known limitations;
- confirmation `no client data committed`.

Если harness/code исправлялся — открыть PR с tests и sanitized docs. Local raw artifacts не коммитить.

## Критерий завершения

CTA-BENCH-002 становится `DONE`, когда:

1. минимум три режима сравнены;
2. frozen manifests и hashes сохранены;
3. synthetic и real-local evidence разделены;
4. quality/hallucination/abstention/repeatability измерены;
5. cold/warm latency и resources измерены;
6. failures/timeouts учтены;
7. canonical integration проверена;
8. выбран кандидат или зафиксирован no-go;
9. sanitized result опубликован в Issue #68;
10. no client data committed подтверждено.
