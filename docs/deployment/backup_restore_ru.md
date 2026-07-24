# Резервное копирование и восстановление

## Скрипты

| Скрипт | Назначение |
|--------|-----------|
| `scripts/backup_data.py` | Создание проверенного backup-архива |
| `scripts/check_backup.py` | Полная проверка структуры и SHA-256 |
| `scripts/restore_data.py` | Безопасное восстановление из backup |
| `scripts/operator_recovery_rehearsal.py` | Изолированная репетиция backup/restore |

## Создание backup

```bash
# Локально
python scripts/backup_data.py

# С заданным путём
python scripts/backup_data.py data/backups/pilot_before_change.zip

# Через Docker
make server-backup
```

По умолчанию архив создаётся в `CTA_BACKUP_ROOT` с уникальным именем:

```text
cta_backup_YYYYMMDD_HHMMSS_microseconds.zip
```

## Формат backup v2

Архив включает:

- согласованный снимок SQLite-базы;
- `storage/`, если `CTA_BACKUP_INCLUDE_UPLOADS=true` и там есть файлы;
- `exports/`, если `CTA_BACKUP_INCLUDE_EXPORTS=true` и там есть файлы;
- `manifest.json`.

Снимок базы создаётся через SQLite Backup API, а не прямым копированием работающего файла БД. Это включает зафиксированное состояние WAL и снижает риск несогласованного архива.

Для каждого файла в `manifest.json` сохраняются:

```text
path
size_bytes
sha256
```

Также сохраняются версия формата, backup ID, время, число файлов, общий размер и счётчики всех таблиц SQLite.

### Что не входит в backup

- `.env` и другие файлы окружения;
- секреты приложения;
- сессионные cookie;
- кэш;
- логи;
- сам каталог backup.

## Проверка backup

```bash
python scripts/check_backup.py data/backups/pilot_before_change.zip
```

Проверка отклоняет архив при наличии:

- неподдерживаемой версии формата;
- повреждённого ZIP или JSON-манифеста;
- дублирующихся ZIP-записей;
- файлов, не перечисленных в манифесте;
- отсутствующих перечисленных файлов;
- несовпадения размера или SHA-256;
- абсолютных путей, `..`, обратных слешей или drive-like путей;
- `.env` файлов;
- символических ссылок;
- зашифрованных ZIP-записей;
- несоответствия `included` реальному составу архива;
- повреждённой SQLite-базы.

## Восстановление

Остановите приложение перед восстановлением:

```bash
python scripts/restore_data.py data/backups/pilot_before_change.zip
```

При необходимости явного восстановления, когда health endpoint ещё отвечает:

```bash
python scripts/restore_data.py data/backups/pilot_before_change.zip --force
```

По умолчанию restore выполняет:

1. Полную проверку исходного backup.
2. Проверку, что приложение остановлено.
3. Закрытие текущего database engine.
4. Обязательное создание pre-restore backup текущего состояния.
5. Извлечение только перечисленных файлов в временный каталог.
6. Повторную проверку извлечённых файлов.
7. Поэтапную замену базы, storage и exports.
8. Повторную проверку всех восстановленных файлов по SHA-256.
9. `PRAGMA integrity_check` для восстановленной SQLite-базы.

`ZipFile.extractall` не используется.

### Emergency-only режим

Отказ от pre-restore backup требует отдельного флага:

```bash
python scripts/restore_data.py data/backups/pilot_before_change.zip \
  --force \
  --skip-pre-restore-backup
```

Этот режим предназначен только для аварийной ситуации, когда текущее состояние уже невозможно сохранить. В обычной процедуре и автоматической репетиции он не используется.

## Репетиция восстановления

```bash
python scripts/operator_recovery_rehearsal.py run \
  --workspace data/rehearsals/pre_pilot_006

python scripts/operator_recovery_rehearsal.py validate \
  --input data/rehearsals/pre_pilot_006
```

Репетиция создаёт только синтетическое изолированное окружение, выполняет полный рабочий цикл, backup, контролируемое повреждение, restore и проверку критических артефактов.

Она также создаёт незаполненный чек-лист реального оператора. Автоматическая репетиция не считается доказательством, что пользователь прошёл сценарий без помощи разработчика.

## Ограничение по путям

Некоторые записи БД содержат локальные пути к файлам. Проверенный сценарий восстановления предполагает те же настроенные пути `CTA_DATABASE_URL`, `CTA_STORAGE_ROOT` и `CTA_EXPORTS_ROOT`.

Перенос на другой компьютер или в другой корневой каталог может потребовать отдельной миграции путей и не считается подтверждённым PRE-PILOT-006 сценарием.

## Docker-команды

```bash
make server-backup
make server-restore BACKUP=data/backups/pilot_before_change.zip
```

## Важно

- restore заменяет только те компоненты, которые явно включены в архив;
- текущая база и файлы могут быть заменены восстановленными версиями;
- приложение должно быть остановлено;
- наличие backup не заменяет проверку восстановления;
- успешное восстановление не является доказательством точности модели или соответствия регуляторным требованиям.
