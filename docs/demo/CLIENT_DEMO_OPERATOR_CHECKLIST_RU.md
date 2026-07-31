# Creative Test Agent — операторский checklist перед клиентской демонстрацией

Версия: 1.0  
Дата: 2026-07-31

## За день до встречи

- [ ] Зафиксирован commit/tag демонстрационной сборки.
- [ ] Создан backup локальной DB, storage и exports.
- [ ] Проверен свободный disk space.
- [ ] Проверен local model profile и путь к weights.
- [ ] Отключены cloud LLM/VLM providers и внешняя telemetry.
- [ ] Подготовлен synthetic fallback project.
- [ ] Подготовлен минимум один полный contrast case и один case с ограничениями.
- [ ] Проверены Client Report v2 и Calibration Dashboard exports.
- [ ] Проверено, что в Git нет real client files, DB, screenshots, reports или model weights.

## За 30 минут

### Security preflight

- [ ] `CTA_LOCAL_ONLY_MODE=true`.
- [ ] App слушает только `127.0.0.1`/localhost.
- [ ] Local model endpoint слушает только loopback.
- [ ] `CTA_ALLOW_CLOUD_LLM=false`.
- [ ] Trusted hosts ограничены localhost/127.0.0.1.
- [ ] `/health`, `/health/db`, `/version` возвращают ожидаемый статус.
- [ ] Outbound network monitor не показывает calls приложения наружу.

### Data preflight

- [ ] Открывается нужный project.
- [ ] Campaign Evidence Workspace содержит ожидаемые cases.
- [ ] Creative previews отображаются.
- [ ] Linkage confidence и missing warnings видимы.
- [ ] Contrast case имеет visual evidence, diagnostics и factual outcomes.
- [ ] Case classifications в Calibration Dashboard корректны.
- [ ] Real и synthetic cases не смешаны.

### Model preflight

- [ ] Local OCR/VLM health-check проходит.
- [ ] Один контрольный asset обрабатывается без timeout.
- [ ] Visual evidence envelope содержит fingerprint/provenance.
- [ ] Unsupported observation приводит к abstention/review-required, а не hallucinated fact.
- [ ] Proposed и effective recommendation различимы.

### Review preflight

- [ ] Есть два различных reviewer subject для демонстрации.
- [ ] Есть отдельный `manager`/`admin` adjudicator.
- [ ] Single-review state блокирует release.
- [ ] Material disagreement создаётся воспроизводимо.
- [ ] Adjudication page показывает basis fingerprint.
- [ ] Stale adjudication scenario подготовлен, но не обязателен для основной встречи.

### Export preflight

- [ ] Client Report v2 открывается.
- [ ] Evidence JSON/manifest доступны.
- [ ] Calibration JSON и XLSX скачиваются.
- [ ] Повторные exports имеют одинаковые bytes для неизменного evidence state.
- [ ] SHA-256 header совпадает с manifest.
- [ ] XLSX открывается без repair warning.
- [ ] Missing values остаются `null`/empty.

## Порядок вкладок браузера

1. `/health`
2. `/ui/projects/{project_id}`
3. `/ui/projects/{project_id}/campaign-evidence`
4. `/ui/projects/{project_id}/campaign-evidence/demo`
5. выбранный campaign detail
6. finding review
7. finding adjudication
8. `/ui/projects/{project_id}/calibration`
9. calibration XLSX/JSON/manifest
10. audit/project history

Открыть вкладки заранее, но обновить ключевые страницы непосредственно перед встречей.

## Во время встречи

- [ ] Сначала показать исходные evidence и factual outcomes, затем diagnostic conclusions.
- [ ] На каждом спорном выводе показать reference/confidence/provenance.
- [ ] Не скрывать missing, uncertain linkage или abstention.
- [ ] Не называть expert-supported finding rate «точностью модели».
- [ ] Не обещать numeric uplift prediction.
- [ ] Не заявлять causal attribution individual asset.
- [ ] Показать single-review release block.
- [ ] Показать independent reviewer streams.
- [ ] Показать adjudication как отдельное решение, не merge мнений.
- [ ] Переключить real/synthetic filters в dashboard.
- [ ] Скачать минимум один deterministic export.

## Fallback matrix

| Сбой | Действие |
|---|---|
| Local VLM не отвечает | Перейти на уже сохранённый diagnostic/evidence; не включать cloud fallback |
| Real project не открывается | Открыть synthetic fallback и явно показать `synthetic` evidence class |
| Live report generation медленная | Открыть ранее сформированный локальный report и manifest |
| Review identity конфликтует | Использовать заранее подготовленные distinct reviewer subjects |
| Adjudication stale | Показать stale protection как feature и открыть новый round |
| XLSX viewer недоступен | Показать JSON + manifest + SHA-256, XLSX открыть после встречи |
| Интернет отсутствует | Нормальный режим; весь обязательный контур local-first |

## После встречи

- [ ] Зафиксированы вопросы и возражения Заказчика.
- [ ] Отдельно записаны requested metrics и requested report fields.
- [ ] Не отправлены real exports без согласованного канала.
- [ ] Локальные временные files и screenshots обработаны по data policy.
- [ ] Проверен audit trail встречи/демонстрационных действий.
- [ ] Создан backup обновлённого evidence state.
- [ ] Запрос следующей партии данных сформирован через CTA-DATA-002 pack.

## Go / no-go

Демонстрация начинается только если одновременно:

- app и local model loopback-only;
- DB и project доступны;
- contrast case открывается;
- report/dashboard открываются;
- reviewers/adjudicator различны;
- exports и hashes проверены;
- synthetic fallback готов;
- нет риска показать неразрешённые реальные материалы вне согласованного контура.
