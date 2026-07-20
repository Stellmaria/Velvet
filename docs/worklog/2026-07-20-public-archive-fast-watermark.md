# Сессия: Fast watermark для публичного архива

- Дата: 2026-07-20
- ID: `2026-07-20-public-archive-fast-watermark`
- Линия/фаза: public archive moderation workflow
- Статус: `завершено`
- Ветка: `agent/public-archive-fast-watermark`
- Базовый commit: `60930db3a492ae0b0d7d99212d65f494a09854f4`

## Перед началом

### Цель

Добавить в админскую карточку публичного архива быстрый запуск watermark по стандартному шаблону, использовать существующий Krita bridge, показать preview с решением оставить или изменить шаблон и после подтверждения заменить файл в архиве без отправки в тему персонажа.

### Исходный контекст

После access/download среза база уже хранит original file_id, watermark flags, approval metadata и template JSON. Общий watermark pipeline поддерживает immutable source, revisions, Krita requests и preview, но не знает о media_files публичного архива.

### Планируемый объём

- стандарт: bottom_right, AUTO, 70%, 19.7%, 4.4%;
- кнопка `⚡ Быстрый watermark` в manager card;
- archive job через отрицательный source_message_id без новой таблицы;
- preview: оставить и заменить либо открыть изменение шаблона;
- проверить неизменность pixel dimensions;
- сохранить финал как lossless PNG;
- гарантировать output byte size не меньше source byte size через безопасный PNG metadata chunk;
- загрузить PNG документом без Telegram photo compression;
- сохранить original file_id и заменить active archive file_id;
- сбросить stale preview cache;
- включить watermark_applied и watermark_approved только после подтверждения;
- не отправлять файл в archive topic.

### Критерии готовности

- default settings точно совпадают с заданным шаблоном;
- кнопка запуска доступна владельцу из публичного архива;
- unsupported/oversized source через Bot API завершается понятным alert;
- Krita output с изменёнными dimensions отклоняется;
- output меньше source дополняется валидным PNG metadata без изменения pixels;
- approve сохраняет original Telegram file_id и заменяет active file_id;
- nonmember download открывается через уже существующий watermark approval policy;
- полный CI проходит.

### Риски и ограничения

Telegram Bot API не скачивает часть крупных файлов. Для таких материалов fast workflow не изменяет архив и сообщает, что нужен локальный исходник. Byte size не является метрикой качества, поэтому размер сохраняется metadata padding только после проверки dimensions и валидности PNG. Новая миграция не требуется.

## После завершения

### Фактически сделано

- WatermarkSettings получил стандарт Velvet public archive;
- WatermarkJob определяет archive media через отрицательный source_message_id;
- manager keyboard получил кнопку fast watermark/re-watermark;
- public archive callback подключён к существующему watermark Router;
- source скачивается в immutable Krita bridge sources;
- archive preview показывает решения оставить/заменить или изменить template;
- expanded keyboard сохраняет все position/color/opacity/size/margin controls;
- approval проверяет dimensions, lossless PNG и minimum byte size;
- финальный документ загружается в Telegram без photo compression;
- media_files сохраняет original file_id, получает новый active file_id и approval flags;
- preview cache очищается;
- archive topic не используется.

### Миграции и совместимость

Новая миграция не нужна. Используются поля, добавленные `999999_public_archive_downloads_and_watermarks.sql`, и существующие watermark_jobs/watermark_revisions из Krita bridge.

### Проверки

Добавлены regression tests для шаблона, archive job marker, review/edit keyboard, dimensions, PNG byte floor, manager button и SQL replacement contract. Полный GitHub CI запускается в PR.

### PR и commit

PR создаётся из ветки `agent/public-archive-fast-watermark`; итоговый merge commit фиксируется после зелёного CI.

### Незавершённое

Очередь «отправить на доработку» и отдельная ветка для Qwen/admin rejects остаются следующим срезом.

### Следующий шаг

Добавить unified rework queue, admin/Qwen sources, topic delivery и действия вернуть в проверку/принять.
