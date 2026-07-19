# Сессия: очистка runtime-ошибок Telegram

- Дата: 2026-07-19
- ID: `2026-07-19-runtime-error-cleanup`
- Линия/фаза: production stability hotfix
- Статус: завершено в коде, требуется обычный deploy
- Ветка: `agent/fix-runtime-errors-20260719`
- Базовый commit: `49e2fdd7fff632e38dcc3899711294316b2fd9f6`

## Цель

Убрать ложные инциденты, которые создавались при временной недоступности Telegram, и автоматически закрыть накопленный исторический сетевой шум без сокрытия настоящих ошибок приложения.

## Исходный контекст

В production-логах сотнями повторялись `ClientConnectorError`, `Cannot connect to host api.telegram.org`, Windows semaphore timeout и стандартные aiogram backoff-сообщения. Aiogram самостоятельно восстанавливал polling, но error center регистрировал каждую попытку как новую аварию владельца.

## Сделано

- добавлен ранний runtime guard для восстановимых ошибок Telegram polling;
- фильтр охватывает `ServerDisconnectedError`, `ClientConnectorError`, невозможность подключения к `api.telegram.org`, semaphore timeout, reset и connection timeout;
- стандартное `Sleep for ... seconds and try again` больше не попадает в incident center;
- `TelegramConflictError`, ошибки базы и другие реальные сбои не подавляются;
- при старте error center известные старые сетевые инциденты отмечаются просмотренными точечным SQL-фильтром;
- установка защиты выполняется до bootstrap через `velvet_bot.app`;
- добавлены regression-тесты фильтра, очистки и идемпотентной установки.

## Совместимость

Миграции и схема PostgreSQL не изменены. Очистка затрагивает только непросмотренные записи `error_incidents` от `aiogram.dispatcher`, совпадающие с известными восстановимыми сетевыми шаблонами.

## Проверка

- исходники нового модуля и тестов проверены компиляцией Python;
- полный GitHub CI должен подтвердить интеграцию с текущим проектом;
- после merge требуется обновить локальный `main` и перезапустить Supervisor.

## Ограничения

Код не может исправить физическую сеть Windows, VPN, DNS или доступ провайдера к Telegram. Он прекращает ложные аварийные уведомления и сохраняет реальные ошибки видимыми. Живой GUI smoke-test Krita по-прежнему выполняется на рабочей Windows-машине, поскольку GitHub CI не создаёт интерактивную desktop-сессию.
