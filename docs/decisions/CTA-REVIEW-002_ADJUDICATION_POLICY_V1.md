# CTA-REVIEW-002 — Adjudication Operational Policy v1.0

Дата утверждения: 2026-07-31  
Статус: `APPROVED FOR CLIENT DEMO AND CONTROLLED PILOT`  
Связанная задача: `CTA-REVIEW-002 — Independent Review Adjudication`

## Решение

Для текущего клиентского демонстрационного и controlled-pilot контура утверждается реализованная provisional policy без изменения порогов и ролей.

## Reviewer process

- Для итогового independent-review статуса необходимы минимум два различных reviewer subject.
- Review выполняются независимо и сохраняются append-only.
- Новая версия review не заменяет историю другого reviewer и не изменяет предыдущие записи.
- Single review считается incomplete independent review и не даёт controlled release.

## Material disagreement

Disagreement считается material, если выполняется хотя бы одно условие:

1. различаются итоговые decisions;
2. различается severity correctness;
3. spread по любой 1–5 dimension равен или превышает 2.

История расхождения сохраняется даже после adjudication.

## Adjudication

- Adjudicator имеет роль `manager` или `admin`.
- Adjudicator не совпадает ни с одним basis reviewer.
- Adjudication требует final decision, confidence и обязательный rationale.
- Basis review IDs и fingerprint неизменны.
- Новая review revision делает предыдущую adjudication stale.
- Stale adjudication не считается действующим разрешением расхождения.

## Release boundary и SLA

- Single review, unresolved material disagreement и stale adjudication блокируют controlled client release.
- Рабочий SLA определяется release boundary: обязательная независимая проверка и adjudication должны быть завершены до передачи отчёта Заказчику.
- Автоматический release по истечении времени запрещён.
- Active/stale disagreement эскалируется `manager`/`admin`.
- Final sign-off выполняет `manager`/`admin`, не участвовавший в basis reviews.

## Audit и retention

- Review и adjudication сохраняются в project-scoped audit trail.
- Evidence JSON и calibration exports сохраняют reviewer streams, disagreement state, basis fingerprint и adjudication status.
- Записи хранятся на срок жизни проекта.
- Удаление допускается только в рамках утверждённой процедуры удаления или retention всего проекта; выборочное редактирование/удаление review и adjudication не допускается.

## Claims boundary

Policy не разрешает заявления о:

- validated model accuracy;
- causal creative lift;
- numeric uplift prediction;
- automatic threshold tuning;
- automatic model selection;
- regulatory или medical approval.

## Acceptance evidence

- GitHub CI: PASS;
- Mac mini/OpenCode acceptance: PASS;
- targeted review/report tests: 29 passed;
- migration replay: PASS;
- loopback-only/no external API calls: confirmed;
- no client data committed: confirmed.

## Изменение policy

Любое изменение reviewer count, thresholds, roles, release boundary или retention оформляется новой versioned decision record. История v1.0 не переписывается.
