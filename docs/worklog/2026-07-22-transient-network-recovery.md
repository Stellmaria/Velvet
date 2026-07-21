# Сессия: Transient network recovery

- Дата: 2026-07-22
- ID: `2026-07-22-transient-network-recovery`
- Линия/фаза: runtime resilience
- Статус: `завершено`
- Ветка: `agent/transient-network-recovery`
- Базовый commit: `b575abdbaf9b1f50c284c58f474ffa38a9ce45c5`

## Перед началом

### Цель

Устранить ложные ERROR-инциденты после локального сетевого разрыва Windows `WinError 1236`, при котором одновременно закрывались Telegram HTTP-соединение и PostgreSQL-сессии фоновых процессов.

### Исходный контекст

Aiogram самостоятельно восстанавливал polling после временного `TelegramNetworkError`, а asyncpg-пул заменял повреждённое соединение при следующих обращениях. Однако `WorkerManager` записывал каждую неуспешную итерацию как `logger.exception`, поэтому один общий сетевой разрыв создавал отдельные ошибки `media-quality`, `ai-quality` и `aiogram.dispatcher` в постоянном центре инцидентов.

### Планируемый объём

- единая классификация временных сетевых ошибок и закрытых asyncpg-соединений;
- принудительное истечение соединений пула после transient-сбоя;
- отсутствие автоматического повтора всей итерации воркера;
- повтор на следующем штатном цикле;
- подавление восстанавливаемых polling-сообщений `ClientOSError / WinError 1236` в error center;
- тревога только при устойчивом сетевом отказе;
- regression tests и обновление generated inventory.

### Критерии готовности

- единичный `ConnectionDoesNotExistError` не создаёт ERROR-инцидент;
- PostgreSQL pool получает `expire_connections()`;
- следующая штатная итерация воркера успешно восстанавливает состояние;
- три последовательных transient-сбоя создают одну общую сетевую тревогу;
- `Failed to fetch updates` с `WinError 1236` не попадает в error center;
- обычные программные ошибки продолжают логироваться с traceback.

### Риски и ограничения

Полная итерация воркера намеренно не перезапускается сразу: внешняя операция могла успеть выполниться до потери подтверждения, а автоматический replay способен продублировать Telegram-уведомление или публикацию. Восстановление откладывается до следующего штатного запуска.

## После завершения

### Фактически сделано

- добавлен `infrastructure/transient_connections.py`;
- распознаются `asyncpg.ConnectionDoesNotExistError`, reset/abort/timeout, Windows network codes и характерные сообщения;
- `WorkerManager` принимает общий transient recovery hook;
- после transient-сбоя вызывается `Pool.expire_connections()`;
- первые временные сбои пишутся на INFO вместо ERROR;
- на третьем последовательном сбое создаётся одна общая ERROR-запись без отдельных traceback каждого воркера;
- после успешной итерации `consecutive_failures` сбрасывается;
- на handler центра ошибок устанавливается фильтр восстанавливаемого aiogram polling;
- добавлены unit/regression tests классификатора, фильтра, пула и менеджера;
- обновлён Telegram navigation inventory.

### Миграции и совместимость

SQL-миграции не требуются. Сигнатура `WorkerManager()` обратно совместима: новый callback необязателен. Обычные исключения продолжают обрабатываться прежним `logger.exception`.

### Проверки

- classifier tests для asyncpg и `WinError 1236`;
- filter tests для aiogram polling;
- pool expiry test;
- восстановление worker snapshot после следующей итерации;
- persistent outage threshold test;
- полный CI репозитория перед merge.

### PR и commit

PR будет открыт после записи ветки и слит только при зелёных обязательных проверках.

### Незавершённое

Старые уже записанные инциденты `#14`, `#16` и `#52` автоматически не удаляются: история ошибок сохраняется. После обновления они не должны переоткрываться от единичного локального сетевого обрыва.

### Следующий шаг

После стабилизации runtime продолжить перевод private/public directory builders на workspace taxonomy и workspace-scoped character stories.
