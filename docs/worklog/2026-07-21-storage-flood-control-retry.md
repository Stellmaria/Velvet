# Сессия: Telegram Storage flood-control retry

- Дата: 2026-07-21
- ID: `2026-07-21-storage-flood-control-retry`
- Линия/фаза: production hotfix / Telegram Storage
- Статус: `выполняется`
- Ветка: `agent/fix-storage-flood-control`
- Базовый commit: `f0bfff96af4d087aa9485a158b08f405ce38ef74`

## Перед началом

### Ошибка

Плановая Telegram Storage migration продолжала отправлять документы после первого ответа Bot API `Too Many Requests`. Каждый следующий Codex/Rework candidate немедленно получал тот же `TelegramRetryAfter`, а service boundary записывал отдельный WARNING в Error Center.

За один запуск появились ошибки `#41`–`#47` с `retry_after` 32–34 секунды.

### Корневая причина

`TelegramStorageUploader` отправлял документы без общего send slot, минимального интервала и обработки `TelegramRetryAfter`. Exception поднимался в item-level boundary, после чего migration loop переходил к следующему файлу вместо ожидания разрешённого Telegram времени.

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
