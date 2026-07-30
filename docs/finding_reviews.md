# CTA-REVIEW-001 — Finding-Level Expert Review

## Назначение

Модуль хранит экспертную оценку каждого system finding отдельно. Исходный вывод агента фиксируется в неизменяемом JSON snapshot и связывается с SHA-256. Исправление экспертной оценки создаёт новую ревизию; существующие строки не обновляются и не удаляются.

`missed_by_system` оформляется как отдельный human finding. Для него `system_finding_snapshot` отсутствует, а `system_finding_fabricated=false` фиксируется в human snapshot и export.

## Решения

- `supported`;
- `partially_supported`;
- `unsupported`;
- `harmful_false_positive`;
- `needs_rewording`;
- `missed_by_system` — только для human finding.

Для system finding сохраняются correctness, relevance, actionability, traceability, severity correctness, reviewer confidence, rationale и comment.

## API

```text
GET  /finding-reviews/projects/{project_id}/findings
GET  /finding-reviews/projects/{project_id}/findings/{finding_id}
POST /finding-reviews/projects/{project_id}/findings/{finding_id}/reviews
POST /finding-reviews/projects/{project_id}/human-findings
GET  /finding-reviews/projects/{project_id}/reviews
GET  /finding-reviews/projects/{project_id}/evidence.json
GET  /finding-reviews/projects/{project_id}/calibration-package.zip
```

При сохранении system review клиент обязан передать `expected_system_finding_sha256`, полученный при чтении finding. Несовпадение блокирует запись с `409 finding_snapshot_changed`.

## Browser flow

Из campaign evidence workspace пользователь открывает кампанию, видит findings конкретного asset и переходит по кнопке `Review finding`. UUID и JSON вводить не нужно. На странице показаны текст finding, evidence identifiers, текущий hash и история ревизий.

Отдельная кнопка `Add missed finding` создаёт human finding в контексте открытой кампании. Список ревизий и ссылки на export доступны через `Review history`.

## Append-only contract

- каждая новая экспертная оценка получает следующий `revision_number`;
- `supersedes_review_id` связывает ревизии;
- ORM запрещает UPDATE и DELETE для `FindingReview`;
- system snapshot и SHA-256 сохраняются в каждой ревизии;
- stale browser form не может записать review после изменения finding;
- project scope проверяется через campaign evidence workspace;
- запись и human omission создают audit events.

## Экспорт

`evidence.json` содержит все ревизии, оба вида snapshots и claim boundary. ZIP calibration package содержит:

```text
finding_reviews_evidence.json
expert_review.csv
package_manifest.json
```

CSV совместим с полями PRE-PILOT-007 `expert_review.csv`. Human omissions экспортируются как `finding_origin=human_added`.

## Границы

Модуль не выполняет multi-reviewer adjudication, не строит calibration dashboard, не настраивает thresholds автоматически и не подтверждает accuracy, causal brand lift или market effectiveness.
