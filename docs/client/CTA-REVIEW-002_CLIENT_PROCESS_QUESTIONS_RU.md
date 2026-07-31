# CTA-REVIEW-002 — утверждённый процесс independent review и adjudication

Дата утверждения: 2026-07-31  
Статус: `APPROVED`  
Связанная задача: `CTA-REVIEW-002`

Изначально этот документ использовался как перечень вопросов Заказчику. Для текущего демонстрационного и controlled-pilot контура ответы зафиксированы ниже. Техническая policy v1.0 хранится в `docs/decisions/CTA-REVIEW-002_ADJUDICATION_POLICY_V1.md`.

## 1. Роли и ответственность

1. Для итогового статуса требуются два независимых reviewer subject.
2. Роли reviewers могут различаться по типу finding; система не навязывает конкретную профессиональную комбинацию.
3. Для high/critical и иных included findings применяется тот же минимум — два независимых reviewer.
4. Adjudicator имеет роль `manager` или `admin`.
5. Final sign-off выполняет `manager` или `admin`.
6. Adjudicator обязан быть отличен от всех basis reviewers.
7. Исключение, при котором basis reviewer становится adjudicator, не допускается в policy v1.0.

## 2. Независимость review

- Reviewers сохраняют оценки в отдельных append-only streams.
- Оценки другого reviewer не являются основанием для перезаписи уже сохранённой review.
- Новая версия review создаётся отдельной revision и сохраняет историю.
- Reviewer identity должна быть стабильной в auth и local/no-auth режимах.
- System finding и review history не редактируются adjudication-процессом.

## 3. Material disagreement

Disagreement считается material, если:

- различаются итоговые decisions;
- различается severity correctness;
- spread по любой 1–5 dimension равен или превышает 2.

Adjudicated disagreement остаётся видимым в calibration history и disagreement metrics.

## 4. Adjudication workflow

1. Adjudicator видит latest basis reviews и immutable basis fingerprint.
2. Обязательны final decision, confidence и rationale.
3. Новая review revision делает предыдущую adjudication stale.
4. Stale basis отклоняется; требуется новый adjudication round.
5. Исходные review и предыдущие adjudications сохраняются.

## 5. SLA, escalation и release blocking

- Single review, unresolved material disagreement и stale adjudication блокируют controlled client release.
- SLA определяется release boundary: обязательная независимая проверка и adjudication должны быть завершены до передачи отчёта Заказчику.
- Автоматический release по времени запрещён.
- Active/stale disagreement эскалируется `manager`/`admin`.
- Final sign-off выполняет `manager`/`admin`, не участвовавший в basis reviews.

## 6. Visibility

В browser UI, evidence JSON, calibration ZIP, Client Report v2 и Calibration Quality Dashboard должны быть различимы:

- single/incomplete review;
- agreement;
- active disagreement;
- current adjudication;
- stale adjudication;
- reviewer histories;
- human-added findings;
- release-blocking reason.

## 7. Retention и audit

- Review/adjudication records append-only.
- Records сохраняются в project audit trail на срок жизни проекта.
- Выборочное редактирование или удаление review/adjudication запрещено.
- Удаление возможно только в рамках утверждённой процедуры удаления/retention всего проекта.
- Evidence exports содержат basis IDs/fingerprint и текущий adjudication state.

## 8. Human-added findings

- Human-added findings не перезаписывают system findings.
- Для текущей policy v1.0 semantic merge/cluster остаётся отдельной методологической операцией.
- Human-added findings отображаются отдельно в review evidence и Calibration Quality Dashboard.

## 9. Claims boundary

Процесс не является доказательством:

- validated model accuracy;
- causal creative lift;
- numeric uplift prediction;
- automatic threshold tuning;
- regulatory/medical approval.

## Итог

Процесс утверждён для клиентской демонстрации и controlled pilot без изменения реализованных reviewer count, disagreement thresholds, roles и release boundary.
