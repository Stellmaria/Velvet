# Сессия: полный перенос локальных артефактов в Telegram Storage

- Дата: 2026-07-21
- ID: `2026-07-21-full-telegram-storage-migration`
- Ветка: `agent/full-telegram-storage-migration`
- Базовый commit: `a9711ab7d55e352fb1330034a17822d31a59d06e`
- Статус: реализовано, ожидает CI и живой запуск на Windows

## Реальная структура Telegram-форума

| Назначение | message_thread_id |
|---|---:|
| Watermarks Final | 3 |
| DB Backups Encrypted | 4 |
| Diagnostics Incidents | 9 |
| Exports Reports | 11 |
| Codex Patches | 7 |
| Releases Emergency | 13 |
| Rework Review | 15 |

Общий chat ID: `-1004459280894`.

## Что реализовано

- единый PostgreSQL-индекс `telegram_storage_objects` и нормализованные части `telegram_storage_parts`;
- SHA256, logical key, исходное имя, размер, тип, ветка, Telegram message/file IDs и manifest;
- разбиение файлов больше лимита Bot API на части до 45 MiB;
- возобновляемый перенос: повторный запуск распознаёт уже загруженный SHA и завершает локальную очистку без повторной отправки;
- удаление локального файла только после успешной отправки всех частей и записи индекса в PostgreSQL;
- удаление orphan-сообщений, если PostgreSQL не принял объект;
- автоматический первый проход после обновления и ручной повтор через `/storage_migrate force`;
- поиск `/storage_find`, скачивание по сохранённым `file_id` через `/storage_download`;
- обзор `/storage`.

## Категории

### Watermarks Final

- перенос старых одобренных watermark через существующий Telegram `file_id` без повторного скачивания на ПК;
- обновление storage-полей `media_files`;
- перенос самостоятельных watermark jobs;
- удаление source/output/preview/request/response завершённых jobs только после подтверждённого хранения;
- отменённые jobs очищаются как ненужные рабочие файлы.

### DB Backups Encrypted

- dump и JSON-manifest упаковываются в ZIP;
- ZIP шифруется потоковым AES-256-GCM;
- ключ получается через scrypt из `STORAGE_ENCRYPTION_SECRET`, затем fallback на `SUPERVISOR_TOKEN` или `BOT_TOKEN`;
- перед отправкой выполняется контрольная расшифровка и сверка SHA256;
- после сохранения `backup_runs.file_path` очищается, а запись связывается с Telegram storage object.

### Diagnostics Incidents

Переносятся закрытые/неактивные файлы из:

- `SUPERVISOR_LOG_DIR`;
- `diagnostics`;
- `runtime/supervisor/incidents`.

Файлы, изменённые менее десяти минут назад, считаются активными и не удаляются.

### Exports Reports

По умолчанию сканируются:

- `exports`;
- `reports`;
- `runtime/exports`;
- `runtime/reports`.

### Codex Patches

- завершённые задачи упаковываются в ZIP с task JSON, prompt, diff, Codex output, test output, git status и git log;
- активные `queued/running/testing` задачи не затрагиваются;
- после Telegram-индекса worktree удаляется через `git worktree remove --force` и `git worktree prune`;
- тяжёлые поля задачи очищаются из `codex_tasks.json`, основные метаданные и storage object ID остаются.

### Releases Emergency

Переносятся артефакты из `releases`, `dist`, `runtime/releases`, а также ZIP/7z/RAR/TAR в корне проекта.

### Rework Review

Создаётся JSON-снимок активной очереди `media_rework_items`. Медиа не копируются повторно: сохраняются ID, file_id и текущие решения.

## Защита от опасной очистки

Не переносятся и не удаляются:

- `.env`;
- ключи и сертификаты;
- `.git`;
- виртуальные окружения;
- `node_modules`;
- кэши Python/pytest/mypy;
- файлы, изменённые в течение active grace period;
- активные Codex worktrees;
- рабочая PostgreSQL и Ollama-модели.

## Конфигурация

Основные переменные добавлены в `.env.example`. `STORAGE_MIGRATE_ON_START=true` выполняет один initial full pass после применения миграции. Следующие запуски не повторяют initial pass; досканирование запускается через `/storage_migrate force`.

## Ограничения живого запуска

Бот должен иметь право отправлять документы и удалять собственные сообщения во всех перечисленных ветках. Фактическая выгрузка и удаление локальных файлов произойдут на целевом Windows-компьютере после Supervisor Update и запуска новой версии.
