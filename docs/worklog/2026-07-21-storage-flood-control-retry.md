# Сессия: Telegram Storage flood-control retry

- Дата: 2026-07-21
- ID: `2026-07-21-storage-flood-control-retry`
- Линия/фаза: production hotfix / Telegram Storage
- Статус: `завершено`
- Ветка: `agent/fix-storage-flood-control`
- Базовый commit: `f0bfff96af4d087aa9485a158b08f405ce38ef74`

## Перед началом

### Цель

Устранить каскад WARNING `#41`–`#47`, возникавший при Telegram flood control во время плановой выгрузки Codex и Rework файлов в Telegram Storage.

### Исходный контекст

Плановая Telegram Storage migration продолжала отправлять документы после первого ответа Bot API `Too Many Requests`. Каждый следующий Codex/Rework candidate немедленно получал тот же `TelegramRetryAfter`, а service boundary записывал отдельный WARNING в Error Center.

За один запуск появились ошибки `#41`–`#47` с `retry_after` 32–34 секунды.

Корневая причина: `TelegramStorageUploader` отправлял документы без общего send slot, минимального интервала и обработки `TelegramRetryAfter`. Exception поднимался в item-level boundary, после чего migration loop переходил к следующему файлу вместо ожидания разрешённого Telegram времени.

### Планируемый объём

- сериализовать Telegram Storage `send_document` внутри uploader;
- выдерживать минимальный интервал между успешными отправками в storage chat;
- при `TelegramRetryAfter` ждать указанное Telegram время и повторять тот же документ;
- ограничить число повторов и сохранить обычные ошибки видимыми;
- добавить regression-тест на flood wait;
- не менять storage schema, logical keys и политику удаления локальных файлов.

### Критерии готовности

- единичный `TelegramRetryAfter` не превращает candidate в failed item;
- migration не переходит к следующим файлам до окончания flood wait;
- локальный файл удаляется только после успешной отправки и записи индекса;
- остальные Telegram/API и database failures продолжают подниматься;
- профильные тесты и полный CI проходят.

### Риски и ограничения

Срез затрагивает только общий `TelegramStorageUploader`. Прямой watermark backfill использует отдельный Bot API send boundary и не смешивается с этим hotfix. Cancellation не должна перехватываться, а исчерпание пяти flood retries обязано оставаться видимой ошибкой.

## После завершения

### Фактически сделано

- все document uploads через `TelegramStorageUploader` сериализованы одним async lock;
- между успешными отправками установлен storage-specific интервал 1.1 секунды;
- `TelegramRetryAfter` больше не попадает в item failure boundary при первом flood response;
- uploader ждёт `retry_after + 1 секунда` и повторяет тот же document до пяти попыток;
- flood wait записывается на INFO, а не создаёт отдельную Error Center запись;
- cancellation и прочие Telegram/API ошибки не подавляются;
- существующая компенсация orphan messages и правило удаления локальных файлов сохранены.

### Миграции и совместимость

Миграции PostgreSQL и изменения environment schema не требуются. Logical keys, Telegram thread mapping и storage object format не изменены.

### Проверки

Добавлен regression-тест, который моделирует `retry_after=34`, проверяет ожидание 35 секунд, повтор одного document, запись storage index и отсутствие orphan cleanup. Docker workflow прошёл. Полный tests workflow и project notes contract повторно запускаются после исправления формата worklog.

### PR и commit

- PR: `#248 Retry Telegram storage flood waits`;
- head branch: `agent/fix-storage-flood-control`;
- текущий head до notes-fix: `bcf235a13370b6691b5f0f42078df43c5aa55dbb`.

### Незавершённое

Прямой watermark backfill использует отдельный Bot API send boundary. Наблюдаемая серия `#41`–`#47` возникла в общем uploader на Codex/Rework items и закрыта этим hotfix. Перенос watermark send на тот же reusable gate выполняется отдельным срезом только при подтверждённой telemetry-проблеме.

### Следующий шаг

После зелёного CI и merge перейти к финальному P3D-срезу `channel_analytics`: исправить безопасное чтение optional Telegram counters, перевести остаточные тесты на canonical controller и удалить последний `velvet_bot.handlers.*` alias.
