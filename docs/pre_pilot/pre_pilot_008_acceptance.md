# PRE-PILOT-008 acceptance

PRE-PILOT-008 считается выполненным, когда:

- Data Quality вычисляет fingerprint текущих подтверждённых mappings;
- выбранный normalization run обязан совпадать по `source_table_id`, `normalizer_version`, `mapping_fingerprint` и завершённому статусу;
- завершённая нормализация с другим mapping fingerprint не используется;
- stale-сценарий создаёт blocking issue `normalization_stale_for_current_mapping`;
- stale Data Quality run не содержит `normalization_run_id` и normalization-derived counts;
- issue и `summary.lineage` содержат проверяемые fingerprints и run IDs;
- повторная нормализация по текущим mappings восстанавливает штатную оценку;
- `input_fingerprint` меняется при смене mappings или появлении новой normalization;
- forced re-inspection не увеличивает `source_table_count` историческими таблицами;
- версия Data Quality Engine повышена;
- исторические mappings, inspections, normalizations и исходные файлы не изменяются;
- focused regression tests и полный CI проходят;
- финальный CI использует `contents: read` и не содержит bootstrap/diagnostic-кода.

Не входит в acceptance:

- удаление исторических inspections или normalization runs;
- автоматическая повторная нормализация;
- обучение или выбор модели;
- обещание точности;
- причинная оценка creative lift;
- выводы о рыночной эффективности или compliance approval.
