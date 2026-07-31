# CTA-CAL-003 — Calibration Quality Dashboard

## Назначение

Calibration Quality Dashboard объединяет finding-level expert review, independent-review adjudication, human-added omissions, workflow measurements и campaign-level outcome coverage в одном project-scoped представлении.

Dashboard предназначен для методологической калибровки и контроля процесса. Он не измеряет валидированную точность модели, не прогнозирует uplift и не доказывает причинный brand lift.

## Evidence classes

Каждый case получает явный класс:

- `real_client` — реальный клиентский case в локальном/закрытом контуре;
- `synthetic` — синтетический fixture или proxy;
- `unclassified` — источник ещё не классифицирован.

Фильтры и exports сохраняют классы раздельно. Dashboard не объединяет real и synthetic evidence в скрытый composite score.

Case также имеет `inclusion_status`: `included`, `excluded` или `deferred`. Только included cases участвуют в текущих агрегатах. Excluded/deferred records сохраняются в БД и audit trail.

## Resolved-review policy

Для rate-метрик используется только resolved assessment:

1. current append-only adjudication, если активное расхождение adjudicated;
2. consensus независимых reviewer, если latest reviews находятся в agreement;
3. single review, unresolved disagreement и stale adjudication не включаются в resolved denominator и остаются видимыми как coverage gaps.

Adjudicated disagreement остаётся disagreement для методологической метрики: adjudication разрешает итоговое решение, но не стирает факт первоначального расхождения.

## Метрики

### Expert-supported finding rate

`correctness >= 4 / (correctness >= 4 + correctness <= 2)` по resolved system findings. Нейтральная оценка `3` исключается из yes/no denominator.

Это observed expert support в выбранном evidence set, а не validated model accuracy.

### Actionability rate

Resolved findings с `actionability >= 4` / все resolved findings.

### Traceability rate

Resolved findings с `traceability >= 4` / все resolved findings.

### Human-added findings

Количество distinct latest human-added findings. Они не превращаются в системные findings и не проходят semantic deduplication автоматически.

### Harmful false positives

Количество resolved system findings с итоговым decision `harmful_false_positive`.

### Reviewer disagreement

Findings с material disagreement / findings с минимум двумя независимыми reviewer. В numerator входят pending, stale и adjudicated disagreements. Provisional materiality policy наследуется из CTA-REVIEW-002.

### Operator touch time

Медиана per-case суммы явно записанных `operator_touch_seconds`, в минутах. Touch time не выводится из audit timestamps, browser session или wall-clock duration.

### Manual action count

Медиана per-case суммы явно записанных целочисленных non-negative manual actions. `operator_touch_seconds <= wall_clock_seconds` валидируется при записи.

### Outcome coverage

Included cases с минимум одним observed campaign outcome / included cases. Это descriptive coverage; missing outcomes не заполняются, а campaign outcome не атрибутируется причинно отдельному asset.

## API

- `GET /calibration-dashboard/projects/{project_id}`;
- `GET /calibration-dashboard/projects/{project_id}/cases`;
- `PUT /calibration-dashboard/projects/{project_id}/cases/{case_id}`;
- `GET /calibration-dashboard/projects/{project_id}/workflow-measurements`;
- `POST /calibration-dashboard/projects/{project_id}/workflow-measurements`;
- `GET /calibration-dashboard/projects/{project_id}/export.json`;
- `GET /calibration-dashboard/projects/{project_id}/export.xlsx`;
- `GET /calibration-dashboard/projects/{project_id}/manifest.json`.

Все endpoints project-scoped. Writes требуют роли `admin`, `manager` или `analyst`; workflow measurements append-only.

## Browser workflow

Открыть `/ui/projects/{project_id}/calibration`.

Оператор может переключить evidence filter, увидеть definition/coverage каждой метрики, классифицировать case, добавить append-only workflow measurement и скачать deterministic JSON/XLSX/manifest.

## Determinism and integrity

JSON сериализуется с сортированными ключами. XLSX получает фиксированные document properties и нормализованные ZIP timestamps. Ответы содержат SHA-256 header; manifest содержит размер и SHA-256 обоих exports.

`generated_at` выводится из latest persisted evidence, а не из времени запроса, поэтому неизменный evidence state даёт одинаковые export bytes.

## Claim boundary

Dashboard всегда фиксирует:

- `validated_model_accuracy_claimed=false`;
- `causal_interpretation_allowed=false`;
- `numeric_uplift_prediction_generated=false`;
- `automatic_threshold_tuning_performed=false`;
- `automatic_model_selection_performed=false`;
- `missing_evidence_inferred=false`;
- `real_and_synthetic_evidence_merged=false`.

## Ограничения

- client process sign-off CTA-REVIEW-002 остаётся отдельным gate;
- layout/usability и migration replay проверяются локально на Mac mini;
- dashboard не обучает модель и не выбирает production thresholds;
- реальные клиентские файлы не попадают в Git или CI artifacts.
