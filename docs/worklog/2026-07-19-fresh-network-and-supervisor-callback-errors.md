# Сессия: свежие сетевые уведомления и устаревший callback Supervisor

- Дата: 2026-07-19
- ID: `2026-07-19-fresh-network-and-supervisor-callback-errors`
- Линия/фаза: production stability hotfix
- Статус: `завершено`
- Ветка: `agent/fix-fresh-network-and-supervisor-callback-errors`
- Базовый commit: `a03ec0c060cca8339a186cb3f7313e50331f99b5`

## Перед началом

### Цель

Убрать свежие ложные уведомления Supervisor о восстановимых обрывах Telegram и исключить `query is too old` в меню статуса Supervisor.

### Исходный контекст

В production 19 июля 2026 года Supervisor отправил уведомления по `ClientConnectorError`, `ClientOSError [WinError 1236]`, таймауту семафора и стандартному aiogram backoff. Отдельно обработчик `handle_supervisor_status_callback` подтверждал callback только после Supervisor I/O и редактирования Telegram-сообщения, поэтому Telegram успевал отклонить ответ как устаревший.

### Планируемый объём

- расширить фильтр Supervisor для восстановимых polling-сбоев;
- подтверждать callback статуса до внешнего I/O;
- безопасно подавлять только точные варианты устаревшего callback;
- добавить регрессионные тесты.

### Критерии готовности

- наблюдавшиеся сетевые строки не открывают Supervisor alert;
- реальные ошибки dispatcher остаются видимыми;
- callback подтверждается первым await;
- CI проходит полностью.

### Риски и ограничения

Фильтрация не исправляет физическую сеть Windows, VPN, DNS или маршрут до Telegram. Она убирает только уведомительный шум для ошибок, которые aiogram повторяет самостоятельно.

## После завершения

### Фактически сделано

- добавлен `velvet_supervisor.polling_log_filter`;
- учтены `ServerDisconnectedError`, `ClientConnectorError`, `ClientOSError`, `WinError 1236`, таймаут семафора, reset/timeout и aiogram backoff;
- фильтр устанавливается в фактически используемом `runtime_extended`;
- `handle_supervisor_status_callback` подтверждает query до чтения статуса и редактирования сообщения;
- точные stale-query ответы Telegram безопасно игнорируются;
- ошибки Supervisor после уже подтверждённого callback отправляются обычным сообщением.

### Миграции и совместимость

Миграции и схема PostgreSQL не изменены. Форматы Supervisor API и callback data не изменены.

### Проверки

Добавлен `tests/test_fresh_runtime_log_hotfix.py` с проверкой всех наблюдавшихся сетевых вариантов, сохранения реальных ошибок, раннего callback acknowledgment и безопасного stale-query fallback. Полный GitHub Actions CI запускается через PR.

### PR и commit

Ветка: `agent/fix-fresh-network-and-supervisor-callback-errors`. PR создаётся после проверки diff.

### Незавершённое

После merge локальный Supervisor необходимо обновить и перезапустить. Стабильность внешнего соединения с Telegram остаётся свойством сети, а не Python-кода.

### Следующий шаг

Обновить рабочий `main`, перезапустить Supervisor и проверить, что новые временные обрывы не создают Telegram-уведомления об ошибке.
