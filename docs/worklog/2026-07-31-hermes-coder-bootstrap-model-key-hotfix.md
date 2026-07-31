# 2026-07-31 — Hotfix bootstrap Hermes Coder без обязательного model key

- Дата: `2026-07-31`
- ID: `hermes-coder-bootstrap-model-key-hotfix`
- Линия/фаза: `server operations`
- Статус: `завершено`
- Ветка: `fix/hermes-coder-optional-model-key-bootstrap`
- Базовый commit: `5481f368d0809b278355e5eaa9ed6de1a81c9780`

## Перед началом

### Цель

Сделать подготовительную установку изолированных Hermes Coder идемпотентной и не зависящей от наличия в Hermes Operator точного имени переменной ключа `gpt-5.6-luna`.

### Исходный контекст

Production installer успешно обновил `/srv/velvet`, создал отдельные checkout Velvet и Max, после чего остановился с сообщением `В operator env не найден ключ маршрута gpt-5.6-luna`. Из-за `set -e` завершилась SSH-сессия. Работающие production-боты, базы и Hermes Operator не изменились, однако подготовительный этап не дошёл до копирования config, установки systemd unit и сборки образов.

Причина заключалась в том, что installer считал модельные credentials обязательными даже для операции «подготовить, но не запускать». Кроме того, parser не поддерживал строки вида `export KEY=value` и при повторном запуске мог заменить уже заполненное модельное поле пустым значением.

### Планируемый объём

- разрешить installer завершать подготовку при отсутствующем ключе `mini/terra` или `luna`;
- оставлять соответствующее поле пустым и выводить предупреждение без значения секрета;
- сохранить строгий запрет запуска через отдельный preflight;
- поддержать `export KEY=value` в operator env;
- при повторном запуске не затирать уже заполненные coder credentials;
- добавить regression-контракт.

### Критерии готовности

- отсутствие model key не прерывает клонирование, конфигурацию, build и установку unit;
- значения секретов никогда не печатаются;
- существующие значения в `/srv/hermes-coders/secrets/*.env` имеют приоритет;
- preflight по-прежнему блокирует gateway при пустых обязательных полях;
- Bash syntax, unit tests, type check, project notes и Docker build проходят.

### Риски и ограничения

Installer сможет подготовить неработоспособную до заполнения credentials инфраструктуру. Это намеренно: systemd unit не запускается автоматически, а preflight остаётся обязательным барьером. Hotfix не пытается угадывать произвольное имя production-секрета и не копирует Telegram/GitHub credentials оператора.

## После завершения

### Фактически сделано

В `deploy/hermes-coders/install.sh`:

- удалены аварийные `SystemExit` для отсутствующих model keys;
- добавлены предупреждения без вывода значений;
- пустые model fields создаются для последующего безопасного заполнения;
- parser поддерживает префикс `export `;
- повторный запуск сохраняет уже заполненные model keys в coder env;
- финальная инструкция явно сообщает, что preflight требует заполнения всех пустых полей.

В `tests/test_hermes_coders_contract.py` добавлен контракт, запрещающий возвращение жёсткого отказа и проверяющий сохранение существующих credentials.

### Миграции и совместимость

SQL-миграций нет. Production Compose, работающие Telegram-боты, PostgreSQL, Hermes Operator и read-only роли не меняются. Повторный запуск installer использует уже созданные workspaces и продолжает с прерванного этапа.

### Проверки

После публикации ветки должны пройти:

- project notes contract;
- type check;
- unit tests;
- Docker build с реальной сборкой Hermes Coder images;
- Bash syntax validation installer.

### PR и commit

- Ветка: `fix/hermes-coder-optional-model-key-bootstrap`
- Основные commits: `d3b048916c368e63da8f0adf326e70f3fb487af7`, `dbfe010b6937cb7865196fce5e07142689518c2b`
- PR создаётся после добавления worklog.

### Незавершённое

После merge требуется обновить `/srv/velvet`, повторно запустить installer, проверить что unit остаётся inactive, затем определить фактические model credentials и заполнить отдельные Telegram/GitHub tokens до preflight.

### Следующий шаг

Открыть PR, дождаться зелёного CI, слить hotfix и повторить только безопасный подготовительный installer на VPS без запуска gateway.
