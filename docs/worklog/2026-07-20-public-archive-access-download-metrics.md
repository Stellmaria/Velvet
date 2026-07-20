# Сессия: Public archive access, downloads and metrics

- Дата: 2026-07-20
- ID: `2026-07-20-public-archive-access-download-metrics`
- Линия/фаза: public archive access and moderation workflow
- Статус: `завершено`
- Ветка: `agent/public-archive-access-download-metrics`
- Базовый commit: `6476b78b2435fa9a59a3a103e9d6633fabc02738`

## Перед началом

### Цель

Открыть restricted-материалы публичного архива участникам канала `-1003951213065`, разрешить им скачивать исходный файл без watermark, а для остальных пользователей показывать скачивание только после админского одобрения watermarked-версии. Добавить счётчики просмотров и скачиваний, а также признак просмотра владельцем `7221553045`.

### Исходный контекст

До среза `requires_adult_channel` полностью исключал материал из публичных SQL-выборок, скачивание было доступно только менеджерам, а public catalog содержал устаревшие дубли обработчиков open/show/like/sub/download. В базе отсутствовали watermark approval и агрегированная статистика по пользователям.

### Планируемый объём

- заменить default member channel на `-1003951213065`;
- сделать public directory и archive page member-aware;
- разрешить member download оригинала независимо от watermark;
- разрешить nonmember download только при `watermark_applied` и `watermark_approved`;
- добавить view/download activity tables;
- показывать админу views, downloads и owner-review state;
- убрать дубли media callbacks из catalog router;
- не реализовывать само нанесение watermark в этом срезе.

### Критерии готовности

- обычный пользователь не видит restricted/oversized материал;
- участник канала видит его и может скачать оригинал;
- обычный пользователь получает watermarked-файл только после approval;
- каждый open/show и успешный download учитываются;
- карточка менеджера показывает метрики и статус просмотра `7221553045`;
- download callback проходит public middleware, но файл выдаётся только после runtime policy check;
- миграции и полный CI проходят.

### Риски и ограничения

Проверка членства зависит от прав бота на `getChatMember`; при недоступном канале доступ закрывается. Telegram Bot API не может скачать часть oversized-файлов для локальной переработки, поэтому members получают уже сохранённый Telegram original file_id. Сам fast-watermark workflow, замена file_id и approval UI выполняются отдельным следующим срезом.

## После завершения

### Фактически сделано

- default `ADULT_CHANNEL_ID` изменён на `-1003951213065`;
- public visibility SQL получил режимы member access для restricted и oversized изображений;
- catalog menus и exact archive offsets используют member-aware выборки;
- download handler перенесён в `public_archive.media_display` и применяет двухуровневую policy;
- members и managers получают original source, остальные только approved watermarked source;
- добавлены `public_media_view_stats` и `public_media_download_stats`;
- в `media_files` добавлены source/watermark approval поля;
- admin caption показывает views, downloads, owner review и watermark state;
- public catalog оставлен только владельцем меню и фильтров, duplicate media callbacks удалены;
- access middleware пропускает `pub:download`, но не принимает решение о выдаче файла.

### Миграции и совместимость

Добавлена технически зарезервированная миграция `999999_public_archive_downloads_and_watermarks.sql`. Старые файлы получают безопасные defaults: watermark отсутствует и публичное скачивание для nonmembers закрыто. Участники канала продолжают скачивать текущий original file_id, пока fast-watermark не сохранит отдельный source file_id.

### Проверки

Обновлены public archive UI/access/boundary tests и добавлены проверки member original, nonmember denial, approved watermarked download, метрик и migration contracts. Полный GitHub CI запускается в PR.

### PR и commit

PR создаётся из ветки `agent/public-archive-access-download-metrics`; итоговый merge commit фиксируется после зелёного CI.

### Незавершённое

Fast watermark, preview/keep/change-template approval UI и очередь доработки ещё не реализованы.

### Следующий шаг

Добавить admin fast-watermark workflow с шаблоном `bottom_right / AUTO / 70% / 19.7% / 4.4%`, заменой archive file_id без отправки в topic и явным approval перед открытием публичного скачивания.
