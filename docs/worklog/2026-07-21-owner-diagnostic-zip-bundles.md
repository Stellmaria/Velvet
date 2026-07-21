# Сессия: owner diagnostic ZIP bundles

- Дата: 2026-07-21
- ID: `2026-07-21-owner-diagnostic-zip-bundles`
- Линия/фаза: production diagnostics and owner feedback
- Статус: `завершено`
- Ветка: `agent/owner-diagnostic-zip-bundles`
- Базовый commit: `6c8f09628c175dc2c9de54cfac40d4a78c05b205`

## Перед началом

### Цель

Добавить безопасную диагностическую выгрузку только в личные сообщения владельца. Пакет должен иметь стабильный формат для дальнейшего анализа вместе с актуальным GitHub-кодом и не содержать `.env`, токены, DSN, дамп базы, пользовательские медиа или тексты сообщений.

### Исходный контекст

Velvet уже имел System Health JSON, Error Center с дедупликацией инцидентов, WorkerManager и owner-only access middleware. Однако системный JSON не объединял активные инциденты, workers, безопасный хвост логов, commit SHA и runtime facts в один переносимый пакет. Автоматической критической ZIP-диагностики владельцу не было.

### Планируемый объём

- добавить `Velvet Diagnostic Bundle v1`;
- включить manifest, runtime snapshot, workers, активные инциденты, безопасное окружение и ограниченный log tail;
- добавить `/diag`, `/diagnostics`, `/diag_export` и кнопки периодов;
- разрешить выгрузку только в private chat владельца;
- проверять критическое состояние каждые 5 минут;
- автоматически отправлять ZIP только при серьёзных проблемах;
- ограничить повтор одинаковой аварии шестью часами и общий поток тридцатью минутами;
- не добавлять PostgreSQL migration и не создавать параллельную таблицу ошибок.

### Критерии готовности

- ZIP содержит стабильный schema marker и commit SHA;
- секреты редактируются до записи в архив;
- архив не содержит database dump, media или `.env`;
- ручные периоды ограничены `1h`, `6h`, `24h`, `3d`, `7d`;
- автоматический worker зарегистрирован с интервалом 300 секунд;
- повторная одинаковая критическая диагностика подавляется cooldown;
- полный CI, Docker и notes contract проходят.

### Риски и ограничения

- владельцы, заданные только username без numeric Telegram ID, могут запросить ZIP вручную, но автоматическая доставка возможна только в известные `ALLOWED_USER_IDS`;
- in-memory log tail начинается после запуска текущего процесса и не является заменой Supervisor log archive;
- cooldown хранится в памяти процесса и сбрасывается после полного перезапуска;
- диагностический ZIP не является backup и намеренно не содержит пользовательские данные.

## После завершения

### Фактически сделано

- добавлен `DiagnosticBundleService` с форматом `velvet-diagnostic-bundle/v1`;
- добавлен bounded redacted INFO+ log buffer;
- ZIP включает `manifest.json`, `summary.md`, `runtime_snapshot.json`, `workers.json`, `incidents.json`, `recent_logs.txt` и `environment_safe.json`;
- добавлены owner-команды `/diag`, `/diagnostics`, `/diag_export` и callback-кнопки для 1/24/72/168 часов;
- команда `/diag` добавлена в owner BotFather menu;
- автоматический monitor зарегистрирован в WorkerManager каждые 300 секунд;
- автоматические триггеры: PostgreSQL/Telegram unavailable, disk below 5%, failed worker или 3 ошибки подряд, active CRITICAL incident, failed/error/invalid backup;
- одинаковый trigger ограничен 6 часами, любые автоматические ZIP ограничены 30 минутами;
- сервис использует существующий `ErrorIncidentRepository`, без дублирования Error Center.

### Миграции и совместимость

PostgreSQL migration не требуется. Существующие `/system`, Error Center, backup, Supervisor и worker contracts сохраняются. Добавлены новые owner-only команды и один новый worker. Автоматическая отправка использует только numeric owner IDs.

### Проверки

Добавлены tests для допустимых периодов, состава ZIP, redaction и автоматического cooldown. Полный GitHub CI должен проверить unit/integration suite, Docker build, command/help inventory, architecture contracts и project notes contract.

### PR и commit

PR создаётся из `agent/owner-diagnostic-zip-bundles` в `main`. Финальный merge commit фиксируется после зелёного CI.

### Незавершённое

Живая проверка на целевом Windows-боте остаётся эксплуатационным шагом: открыть `/diag`, скачать ручной ZIP и выполнить controlled CRITICAL test через существующий Error Center. Долговременное хранение cooldown в PostgreSQL намеренно не включено в первый срез.

### Следующий шаг

После merge обновить локальный `main`, перезапустить Supervisor, выполнить `/diag_export 24h` и загрузить полученный ZIP в ChatGPT для проверки реального формата. Затем отдельным срезом добавить AI duration/error/cost metrics в диагностический bundle без включения пользовательского контента.
