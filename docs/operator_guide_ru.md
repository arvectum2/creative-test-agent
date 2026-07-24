# Creative Test Agent — Руководство оператора

## Установка
1. Клонировать репозиторий:
   ```bash
   git clone <repo-url>
   cd creative-test-agent
   ```
2. Создать виртуальное окружение:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # Linux/Mac
   ```
3. Установить зависимости:
   ```bash
   pip install -e ".[dev]"
   ```

## Запуск
```bash
make run
```
Открыть http://localhost:8000/

## Загрузка demo-профиля
```bash
make load-demo-profile
```
Загружает клиента NovaBank, проект, креативы A/B/C и брендбук.

## Создание клиента и проекта
Через UI:
1. Нажать "New Client", заполнить название и описание.
2. В карточке клиента нажать "New Project".
3. Указать название проекта.

## Загрузка брендбука
1. Перейти в Brandbooks → Upload Brandbook.
2. Выбрать PDF/DOCX/TXT файл, указать проект.
3. Нажать "Ingest" после загрузки.

## Запуск batch-теста
```bash
make run-demo-batch
```
Или через UI: Batches → New Batch → Queue → Run All.

## Экспорт отчёта
На странице отчёта нажать DOCX, PPTX или PDF-ready.

## Резервное копирование

```bash
python scripts/backup_data.py
python scripts/check_backup.py <путь-к-backup.zip>
```

Backup считается готовым только после `Backup integrity: PASS`.

## Восстановление

1. Остановить приложение.
2. Проверить исходный архив:
   ```bash
   python scripts/check_backup.py <путь-к-backup.zip>
   ```
3. Запустить restore:
   ```bash
   python scripts/restore_data.py <путь-к-backup.zip>
   ```
4. Убедиться, что создан отдельный `pre_restore_...zip`.
5. Запустить приложение и проверить проект, исходные материалы и отчёты.

Не используйте `--skip-pre-restore-backup` в обычной работе.

## Репетиция оператора и восстановления

```bash
make operator-recovery-rehearsal
```

Или напрямую:

```bash
python scripts/operator_recovery_rehearsal.py run \
  --workspace data/rehearsals/pre_pilot_006
python scripts/operator_recovery_rehearsal.py validate \
  --input data/rehearsals/pre_pilot_006
```

После автоматического PASS заполните:

```text
data/rehearsals/pre_pilot_006/evidence/operator_checklist.json
```

Чек-лист должен заполнять реальный оператор во время наблюдаемой сессии. Автоматический запуск не доказывает, что сценарий пройден без помощи разработчика.

## Релизный манифест
```bash
make release-manifest
```

## Проверка готовности
```bash
make release-check
make pilot-check
make check-server
make client-pilot-check
```

## Устранение неполадок
- **Ошибка подключения к БД**: проверить, что каталог базы существует и доступен для записи.
- **Backup не проходит проверку**: не выполнять restore; создать новый backup и изучить точную ошибку размера, SHA-256 или структуры.
- **Restore сообщает, что приложение запущено**: штатно остановить сервер; `--force` использовать только осознанно.
- **После переноса на другой компьютер не открываются файлы**: текущий подтверждённый сценарий рассчитан на те же настроенные пути; требуется миграция путей.
- **LLM не отвечает**: проверить `CTA_LLM_PROVIDER=stub` для тестов или запустить Ollama.
- **Тесты падают**: `make pilot-check` покажет детали.
