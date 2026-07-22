# Сессия: Telegram alert noise and storage retry

- Дата: 2026-07-22
- ID: `2026-07-22-telegram-alert-noise-and-storage-retry`
- Линия/фаза: production diagnostics and Telegram storage reliability
- Статус: `завершено`
- Ветка: `agent/fix-diagnostic-alert-noise-retries`
- Базовый commit: `d146e08850265cf341e7a9fe136b7dd8196fce23`

## Перед началом

### Цель

Убрать ложные аварийные инциденты от штатного Telegram polling backoff, прекратить feedback loop при временной недоставке диагностического ZIP и повторять временно сорванные загрузки Telegram Storage без потери исходного файла.

### Исходный контекст

В production-логе повторялись `Bad Gateway` и `RetryAfter` от `GetUpdates`, хотя aiogram самостоятельно восстанавливает polling. Попытка отправить автоматический диагностический ZIP при том же сбое создавалась как отдельный warning-инцидент. Telegram Storage повторял только flood-control, а request timeout и server-side 5xx сразу завершали candidate с предупреждением.

### Планируемый объём

- расширить классификацию временных polling-сбоев;
- не сохранять временную недоставку diagnostic bundle как новый инцидент;
- добавить ограниченный retry для network/server ошибок Telegram Storage;
- оставить постоянные и прикладные ошибки видимыми;
- добавить точечные regression tests.

### Критерии готовности

- `Bad Gateway` и `RetryAfter` от `aiogram.dispatcher` не попадают в Error Center;
- application handler errors продолжают попадать в Error Center;
- временная недоставка автоматического ZIP не создаёт рекурсивный warning;
- Telegram Storage повторяет request timeout и server-side failures с bounded backoff;
- после исчерпания попыток ошибка остаётся видимой и локальный файл не удаляется;
- project notes contract и профильные тесты проходят в CI.

### Риски и ограничения

Фильтрация применяется только к известным сообщениям polling и к конкретному сообщению недоставки diagnostic bundle. Она не скрывает ошибки Telegram handlers. Retry ограничен пятью попытками; длительная недоступность Telegram по-прежнему фиксируется как реальная ошибка после исчерпания попыток.

## После завершения

### Фактически сделано

- добавлен классификатор recoverable polling для network disconnect, request timeout, Telegram server 5xx и flood-control backoff;
- фильтр Error Center подавляет только `Failed to fetch updates` с известными временными причинами;
- временный `Bad Gateway` при доставке автоматического diagnostic bundle больше не создаёт отдельный инцидент;
- Telegram Storage uploader повторяет `TelegramNetworkError` и `TelegramServerError` с exponential backoff;
- существующий `TelegramRetryAfter` использует тот же общий лимит попыток;
- добавлены regression tests для polling, diagnostic feedback loop и storage retry.

### Миграции и совместимость

PostgreSQL migration не требуется. Формат diagnostic bundle, schema Error Center, storage object model и owner-команды не меняются. Изменяется только классификация временного Telegram transport noise и политика повторов отправки.

### Проверки

Добавлены и обновлены:

- `tests/test_transient_connection_recovery.py`;
- `tests/test_telegram_storage_transient_retry.py`.

Полный tests workflow, type check, Docker build и project notes contract должны быть выполнены GitHub Actions после открытия PR.

### PR и commit

Изменения подготовлены в ветке `agent/fix-diagnostic-alert-noise-retries`. Draft PR открывается в `main`; итоговый merge commit фиксируется после зелёного CI.

### Незавершённое

Нужна живая Windows-проверка после обновления production: дождаться штатного Telegram backoff, убедиться в отсутствии новых polling-инцидентов и выполнить controlled storage upload с временным сетевым сбоем.

### Следующий шаг

После зелёного CI обновить локальный `main`, перезапустить Supervisor и отметить старые инциденты Error Center просмотренными. Они не удаляются автоматически, поскольку уже сохранены в PostgreSQL до исправления фильтра.
