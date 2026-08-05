# CTA-RELEASE-PREP-001 — On-Premise Release Skeleton

Версия приложения: `0.1.0-rc1`  
Режим: закрытый локальный контур  
Граница задачи: подготовка воспроизводимого релизного пакета. Установка в инфраструктуру конкретного клиента относится к `CTA-DEPLOY-001`.

## 1. Состав релизного пакета

Детерминированный ZIP содержит:

- исходный код приложения, миграции и операционные скрипты;
- Dockerfile и серверный Docker Compose профиль;
- безопасный шаблон `.env.onprem.example`;
- версионированный `release-manifest.json`;
- CycloneDX SBOM `sbom.cdx.json`;
- текстовый экспорт зависимостей `dependency-export.txt`;
- `SHA256SUMS` для каждого файла пакета;
- ссылку на frozen model profile и контрольные хэши моделей без весов;
- инструкции по установке, резервному копированию, обновлению, откату и диагностике.

Пакет намеренно не содержит клиентские материалы, секреты, локальные базы, кэши, логи, абсолютные пользовательские пути и веса моделей.

## 2. Предварительные требования

Для сборки и проверки:

- Python 3.11 или новее;
- `venv` и `pip`;
- доступ к Python package index только на этапе установки зависимостей;
- не менее 10 GB свободного места для приложения и временных файлов;
- Docker Engine с Docker Compose v2 — только для контейнерного запуска.

Для frozen production model profile на принятой целевой машине:

- Mac mini Apple M4 Pro, 24 GB unified memory;
- VLM `mlx-community/Qwen3-VL-4B-Instruct-4bit` на `127.0.0.1:8091`;
- LLM `mlx-community/Qwen3.5-4B-MLX-4bit` на `127.0.0.1:8093`;
- точные ревизии и хэши находятся в `config/model_profiles/production/cta_model_001.mac_mini_m4pro_24gb.frozen.json`.

Веса моделей загружаются отдельно на целевой машине и никогда не входят в релизный ZIP.

## 3. Сборка и валидация

Из корня репозитория:

```bash
python scripts/cta_release_prep_001.py \
  --project-root . \
  build \
  --source-revision "$(git rev-parse HEAD)"
```

Результат:

```text
data/release/cta-release-prep-001/
├── creative-test-agent-onprem-0.1.0-rc1/
├── creative-test-agent-onprem-0.1.0-rc1.zip
└── creative-test-agent-onprem-0.1.0-rc1.zip.sha256
```

Повторная проверка ZIP:

```bash
python scripts/cta_release_prep_001.py \
  --project-root . \
  validate \
  --bundle data/release/cta-release-prep-001/creative-test-agent-onprem-0.1.0-rc1.zip
```

Валидация завершается ошибкой при любом из условий:

- изменился файл или его SHA-256;
- в архив попал секрет, закрытый ключ, локальная БД или вес модели;
- обнаружен абсолютный пользовательский путь;
- повреждён frozen model profile или его внутренний integrity hash;
- шаблон окружения разрешает облачный fallback, публичный bind или отключённую авторизацию;
- SBOM, manifest или `SHA256SUMS` отсутствуют либо не соответствуют содержимому.

## 4. Чистая синтетическая установка

Обязательный acceptance gate выполняется в новом временном окружении:

```bash
python scripts/cta_release_prep_001_clean_install.py \
  --bundle data/release/cta-release-prep-001/creative-test-agent-onprem-0.1.0-rc1.zip \
  --evidence artifacts/local-acceptance/CTA-RELEASE-PREP-001/clean-install.json
```

Скрипт самостоятельно:

1. безопасно распаковывает ZIP;
2. создаёт новую virtual environment;
3. устанавливает приложение и dev-зависимости;
4. валидирует release manifest, SBOM и хэши;
5. компилирует исходники;
6. проверяет registry моделей и миграции;
7. запускает closed-loop и server-readiness проверки;
8. проверяет `/health` через FastAPI TestClient;
9. создаёт синтетическую SQLite-запись;
10. выполняет backup, повреждает запись, делает restore и подтверждает восстановление исходного значения.

В acceptance-файл не записываются пароли, абсолютные локальные пути, содержимое БД и клиентские данные.

## 5. Подготовка окружения

Скопируйте шаблон:

```bash
cp .env.onprem.example .env.server
```

Обязательно замените:

```text
CTA_SECRET_KEY=REQUIRED_CHANGE_ME_WITH_64_RANDOM_CHARACTERS
CTA_BOOTSTRAP_ADMIN_PASSWORD=REQUIRED_CHANGE_ME_WITH_A_STRONG_PASSWORD
CTA_BOOTSTRAP_ADMIN_EMAIL=admin@example.invalid
```

Сгенерировать секрет можно локально:

```bash
python -c "import secrets; print(secrets.token_urlsafe(64))"
```

Перед запуском проверьте неизменяемые ограничения:

```text
CTA_HOST=127.0.0.1
CTA_LOCAL_ONLY_MODE=true
CTA_ALLOW_CLOUD_LLM=false
CTA_ENABLE_AUTH=true
CTA_SECURITY_FAIL_CLOSED=true
CTA_SECURITY_HEADERS_ENABLED=true
CTA_CORS_ALLOWED_ORIGINS=
```

Для доступа с другой машины не меняйте bind на `0.0.0.0` без отдельного защищённого reverse proxy, firewall, HTTPS и согласованного сетевого контура. Такой клиентский deployment не входит в эту задачу.

## 6. Запуск

### Вариант A: Python

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
set -a
source .env.server
set +a
python scripts/run_migrations.py
python scripts/bootstrap_admin.py
uvicorn src.main:app --host 127.0.0.1 --port 8000
```

### Вариант B: Docker Compose

```bash
cp .env.onprem.example .env.server
# заменить REQUIRED_CHANGE_ME и адрес администратора

docker compose -f docker-compose.server.yml build
docker compose -f docker-compose.server.yml up -d
docker compose -f docker-compose.server.yml exec creative-test-agent python scripts/run_migrations.py
docker compose -f docker-compose.server.yml exec creative-test-agent python scripts/bootstrap_admin.py
```

Проверки:

```bash
curl --fail http://127.0.0.1:8000/health
curl --fail http://127.0.0.1:8000/health/db
```

## 7. Frozen model profile

До запуска production-model режима:

```bash
# production CLI default указывает на draft-профиль, поэтому для frozen-режима
# всегда передавайте запечатанный frozen-профиль явно:
export CTA_FROZEN_PROFILE=config/model_profiles/production/cta_model_001.mac_mini_m4pro_24gb.frozen.json

python scripts/cta_model_001.py validate --profile "$CTA_FROZEN_PROFILE" --mode frozen
python scripts/cta_model_001.py start --profile "$CTA_FROZEN_PROFILE"
python scripts/cta_model_001.py preflight --profile "$CTA_FROZEN_PROFILE" --require-runtime
python scripts/cta_model_001.py status --profile "$CTA_FROZEN_PROFILE"
```

Оба endpoint должны быть loopback-only, а фактические model identity должны совпасть с frozen profile. Любое расхождение — `NO-GO`.

Остановка:

```bash
python scripts/cta_model_001.py stop --profile "$CTA_FROZEN_PROFILE"
```

После остановки порты `8091` и `8093` должны быть свободны, PID-файлы удалены, residual process count равен нулю.

## 8. Резервное копирование

Перед каждым обновлением:

```bash
python scripts/backup_data.py data/backups/pre-upgrade.zip
```

Проверьте, что команда завершилась успешно и архив существует. Backup включает согласованный SQLite snapshot и, согласно настройкам, локальные uploads/exports. Секреты и env-файлы в архив не включаются.

Контейнерный вариант:

```bash
docker compose -f docker-compose.server.yml exec creative-test-agent \
  python scripts/backup_data.py data/backups/pre-upgrade.zip
```

## 9. Обновление

1. Остановить приложение и локальные model runtime процессы.
2. Создать и проверить backup.
3. Сохранить текущий релизный ZIP и его `.sha256`.
4. Проверить новый ZIP командой `validate`.
5. Распаковать новый пакет в отдельный каталог.
6. Перенести только `.env.server` и data volumes; не копировать старый исходный код поверх нового.
7. Установить зависимости в новую virtual environment либо пересобрать Docker image.
8. Запустить миграции.
9. Выполнить health, closed-loop и минимальный synthetic smoke.
10. Только после PASS переключить рабочий запуск на новый каталог/image.

## 10. Откат

Условие отката: ошибка миграции, невозможность входа, деградация закрытого контура, повреждение данных, несовпадение model identity или провал smoke-test.

Порядок:

```bash
# остановить приложение
python scripts/cta_model_001.py stop --profile "$CTA_FROZEN_PROFILE"

# вернуть предыдущий код/image
# затем восстановить pre-upgrade backup
python scripts/restore_data.py data/backups/pre-upgrade.zip --force

# проверить состояние
python scripts/check_migrations.py
python scripts/check_closed_loop.py
python scripts/check_server_readiness.py
```

По умолчанию restore создаёт дополнительный pre-restore backup. Параметр `--skip-pre-restore-backup` допустим только в контролируемой аварийной репетиции, когда исходное состояние уже сохранено отдельно.

Откат считается завершённым только после PASS проверки БД, health endpoint и стандартного синтетического сценария.

## 11. Диагностика

### Приложение не запускается

```bash
python scripts/check_server_readiness.py
python scripts/check_migrations.py
python -m compileall -q src scripts
```

Проверьте Python 3.11+, доступность каталогов `data/db`, `data/storage`, `data/exports`, `data/backups` и отсутствие placeholder-секретов.

### Невозможно войти

- `CTA_ENABLE_AUTH=true`;
- выполнен `scripts/bootstrap_admin.py`;
- пароль не короче заданного `CTA_PASSWORD_MIN_LENGTH`;
- cookie не блокируется браузером;
- `CTA_SECRET_KEY` не менялся после создания активной сессии.

### Модель недоступна

```bash
python scripts/cta_model_001.py status --profile "$CTA_FROZEN_PROFILE"
python scripts/cta_model_001.py preflight --profile "$CTA_FROZEN_PROFILE" --require-runtime
```

Не разрешайте облачный fallback. При несовпадении identity остановите runtime и повторно проверьте frozen profile.

### Restore не выполняется

- приложение остановлено либо указан `--force` в контролируемом контуре;
- backup проходит встроенную validation;
- используются те же configured data paths;
- достаточно свободного места для staging и pre-restore backup.

### Release validator отклоняет архив

Не отключайте проверку. Удалите запрещённый файл из source tree или исправьте шаблон/manifest, пересоберите ZIP и повторите validation.

## 12. Известные ограничения

- это release candidate для закрытого тестирования, не production SLA;
- конкретная клиентская сеть, HTTPS, reverse proxy, firewall и домен относятся к `CTA-DEPLOY-001`;
- веса моделей устанавливаются отдельно;
- application dependencies пока фиксируются в SBOM как declared version specs, а frozen model runtime — точными pins;
- SQLite подходит для одиночного/малого pilot-контура, но не для высококонкурентной multi-tenant нагрузки;
- нет SSO, MFA, автоматического password reset и Kubernetes orchestration;
- видео-анализ не входит в текущий релизный контур.

## 13. GO / NO-GO

`GO` допускается только если одновременно:

- deterministic build повторён с тем же SHA-256;
- bundle validator — PASS;
- GitHub workflow `CTA-RELEASE-PREP-001` — PASS;
- clean-machine synthetic install — PASS;
- backup/restore rehearsal — PASS;
- Mac mini frozen profile preflight и lifecycle — PASS;
- в пакете нет секретов, client data, local paths, caches и model weights.

Любой незакрытый пункт означает `NO-GO` для передачи пакета тестировщику или установки в клиентский контур.
