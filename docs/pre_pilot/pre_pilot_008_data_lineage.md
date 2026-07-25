# PRE-PILOT-008 — строгая привязка Data Quality к lineage

## Проблема

До PRE-PILOT-008 Data Quality выбирал последний завершённый `NormalizationRun` для таблицы. При изменении подтверждённых mappings после нормализации отчёт мог одновременно использовать:

- текущие mappings для оценки покрытия;
- сущности и метрики из старой нормализации;
- старый `mapping_fingerprint`, скрытый внутри выбранного run.

Такой отчёт выглядел внутренне согласованным, хотя фактически объединял два разных состояния данных.

Повторный `force`-inspection также создаёт новую историческую запись `SourceInspection` и новый набор `SourceTable`. Подсчёт всех таблиц всех inspections завышал фактическое число активных таблиц импорта.

## Новое правило выбора normalization

Data Quality строит fingerprint текущего подтверждённого mapping-контракта по тем же полям, которые сохраняет normalizer:

- mapping ID и source-column ID;
- позиция и заголовок колонки;
- inferred type;
- target field;
- mapping profile;
- decision source.

Использовать можно только завершённый normalization run, для которого одновременно совпадают:

```text
source_table_id
normalizer_version
mapping_fingerprint
status = completed
```

Последний завершённый run с другим fingerprint сохраняется как историческое доказательство, но не участвует в Data Quality.

## Поведение при stale normalization

Когда завершённая нормализация существует, но не соответствует текущим mappings:

- `normalization_run_id` нового Data Quality run остаётся `null`;
- все normalization-derived counts остаются нулевыми;
- readiness фиксирует `normalization_available=false`;
- создаётся blocking issue `normalization_stale_for_current_mapping`;
- issue содержит текущий fingerprint, ID и fingerprint последней завершённой нормализации, а также версии normalizer;
- remediation требует повторной нормализации после подтверждения текущих mappings.

После повторной нормализации Data Quality выбирает новый совпадающий run и снова выполняет проверки нормализованных строк.

## Lineage в summary и fingerprint

`summary.lineage` содержит:

```text
current_mapping_fingerprint
selected_normalization_run_id
selected_normalization_mapping_fingerprint
latest_completed_normalization_run_id
latest_completed_mapping_fingerprint
normalizer_version_required
```

Эти значения также входят в `input_fingerprint` Data Quality. Появление новой нормализации или изменение mappings создаёт новое состояние отчёта и не позволяет вернуть ранее закэшированный результат.

Версия Data Quality Engine повышена до `1.1.0`.

## Активные таблицы

`source_table_count` теперь считает таблицы только из последнего завершённого inspection каждого source file внутри import session. Исторические таблицы предыдущих forced inspections сохраняются, но не увеличивают активное покрытие.

## Границы

Изменение не удаляет и не переписывает исторические normalization runs, mappings, inspections или исходные файлы. Оно не создаёт прогнозов, не подтверждает точность модели и не разрешает выводы о causal lift или рыночной эффективности.
