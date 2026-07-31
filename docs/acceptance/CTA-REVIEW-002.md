# CTA-REVIEW-002 — Independent Review Adjudication

Дата фиксации: 2026-07-31  
Каноническая задача: `CTA-REVIEW-002`  
Контур: `HYBRID + CLIENT`  
Итоговый статус: `DONE`

## Цель

Сохранять независимые экспертные оценки одного system finding, автоматически выявлять существенные расхождения и разрешать активное расхождение отдельной append-only записью adjudication без изменения system finding и исходных review.

## Реализованный scope

- reviewer-specific append-only revision streams;
- стабильный `reviewer_subject_id` для auth и local/no-auth режимов;
- автоматический расчёт disagreement по последней ревизии каждого reviewer;
- append-only `FindingAdjudication` с immutable basis review IDs и SHA-256 fingerprint;
- stale-basis protection при изменении review после открытия adjudication;
- API и browser workflow в project scope;
- обязательные adjudicator, role, final decision, confidence и rationale;
- запрет adjudication для analyst и для участника basis reviews;
- audit events, evidence JSON, deterministic calibration ZIP;
- интеграция с Client Report v2: unresolved disagreement и incomplete independent review остаются `not_reviewed` и блокируют controlled release;
- migration, synthetic acceptance tests и отдельный CI workflow.

## Утверждённая operational policy v1.0

1. Для итогового independent-review статуса требуются минимум два различных reviewer subject.
2. Material disagreement возникает, если различается decision, различается severity correctness или spread хотя бы одной 1–5 dimension равен или превышает 2.
3. Adjudication выполняет только `admin` или `manager`.
4. Adjudicator не может совпадать ни с одним basis reviewer.
5. Review и adjudication append-only; новая версия создаётся отдельной записью.
6. Новая review revision делает прежнюю adjudication stale.
7. Single review, unresolved disagreement и stale adjudication блокируют controlled client release.
8. Эскалация и final sign-off выполняются `manager`/`admin`, не участвовавшим в basis reviews.
9. SLA определяется release boundary: обязательная проверка и adjudication должны быть завершены до передачи отчёта Заказчику.
10. Evidence сохраняется в project audit trail и exports на срок жизни проекта.
11. Claims о validated accuracy, causal lift и automatic threshold tuning запрещены.

Полная фиксация решения: `docs/decisions/CTA-REVIEW-002_ADJUDICATION_POLICY_V1.md`.

## Acceptance gates

### GitHub acceptance

- [x] DB model и migration;
- [x] reviewer-specific revision streams;
- [x] deterministic disagreement calculation;
- [x] append-only adjudication и stale-basis protection;
- [x] API, UI, audit и exports;
- [x] Client Report v2 release boundary;
- [x] synthetic tests и dedicated CI workflow;
- [x] real client data отсутствуют в repository.

### Local acceptance — Mac mini / OpenCode

- [x] clean migration на копии локальной БД;
- [x] два declared experts независимо проходят review одного synthetic finding;
- [x] revision одного эксперта не supersede review другого;
- [x] disagreement появляется автоматически;
- [x] третий adjudicator сохраняет решение без UUID/JSON editing;
- [x] stale basis отклоняется после новой review revision;
- [x] evidence JSON, ZIP и Client Report v2 отражают pending/current/stale adjudication;
- [x] loopback-only и отсутствие внешних API подтверждены;
- [x] sanitized acceptance record опубликован без client data.

Локальный результат: **PASS**. Targeted tests: **29 passed**. Migration replay: **PASS**.

### Client acceptance

- [x] утверждено минимальное число reviewers;
- [x] утверждён критерий material disagreement;
- [x] утверждены роли и независимость adjudicator;
- [x] утверждены SLA, escalation и final sign-off;
- [x] утверждены retention/audit требования;
- [x] утверждён synthetic acceptance pack;
- [x] operational process v1.0 принят без изменения реализованных правил.

## Defect fixed during acceptance

Commit `741e7772a0ebac0b5929c9c1d5bcf2a049dbb9d7` устранил возможность controlled release при наличии только одного independent review. Теперь single-review finding остаётся `not_reviewed`, получает `independent_review_incomplete` и блокирует release до второй независимой оценки.

## Итог

Все GitHub, local и client-process gates пройдены. CTA-REVIEW-002 готова к merge и использованию в демонстрационном и controlled-pilot контуре.
