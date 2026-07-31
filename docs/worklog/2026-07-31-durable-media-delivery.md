# Durable media delivery

- Дата: `2026-07-31`
- ID: `#457`
- Линия/фаза: `P0 · media generation delivery`
- Статус: `завершено`
- Ветка: `agent/issue-457-durable-media-delivery`
- Базовый commit: `e46832138d77d9219b0be9adb14dd95763fcacde`

## Перед началом

### Цель

Собрать единый provider-neutral durable pipeline доставки результатов фото и видео, чтобы успешная и оплаченная генерация не терялась из-за перезапуска процесса, ошибки CDN или Telegram и не запускалась повторно при восстановлении.

### Исходный контекст

`ai_tasks` переводилась в `success` до best-effort доставки файла. Активная доставка зависела от порядка installer stages и monkeypatch worker-классов. После provider success сбой процесса мог оставить пользователя без результата, а обычный retry создавал риск второй платной provider task.

### Планируемый объём

- отдельное durable-состояние provider submit/success, URL resolution, download, original, preview и notification;
- provider-neutral application use cases и infrastructure adapters;
- recovery worker с DB claim/lock;
- восстановление только по сохранённому `provider_task_id`;
- redelivery с проверкой actor/workspace ownership без submit и списания;
- совместимый rollout с нейтрализацией legacy delivery installers;
- миграция и regression-тесты критических сценариев.

### Критерии готовности

- provider success не означает автоматически успешную доставку;
- original и preview имеют независимые outcomes;
- restart recovery не вызывает новую генерацию;
- expired URL фиксируется явно;
- повторные попытки и ошибки сохраняются в БД;
- старые успешные задачи доступны для backfill/redelivery;
- CI и проектные контракты проходят.

### Риски и ограничения

- физическое удаление всех legacy stage names относится к более широкому installer cleanup в #455;
- provider URL может истечь до первой успешной загрузки, поэтому это отдельный terminal outcome, а не скрытый retry;
- Telegram может принять preview, но отклонить document, поэтому каналы доставки нельзя объединять в один флаг.

## После завершения

### Фактически сделано

- добавлены `media_delivery_jobs` и `media_delivery_items`;
- реализованы `ResolveProviderResult`, `DeliverMediaResult` и `RedeliverMediaResult`;
- добавлены PostgreSQL repository, provider-result resolver, HTTP downloader и Telegram transport;
- все generation slots используют один process-level runtime, а recovery сериализуется через DB claims;
- task queue сохраняет provider submission/success и восстанавливает crash-window по тому же provider task;
- worker больше не владеет отправкой файлов, а legacy `_deliver_best_effort` принудительно становится no-op guard;
- redelivery проверяет принадлежность задачи пользователю и workspace;
- добавлены typed task view, UI-кнопка повторной доставки и structured outcome logs.

### Миграции и совместимость

Добавлена миграция `migrations/z029_durable_media_delivery.sql`. Существующие stage names временно остаются совместимыми оболочками, но их legacy installers нейтрализуются и не могут перехватить доставку. Старые успешные `ai_tasks` импортируются backfill-механизмом.

### Проверки

- syntax compilation новых модулей;
- regression tests: partial original/preview delivery, expired URL, missing result URL, restart recovery, redelivery без generation API и legacy override guard;
- project notes contract;
- package architecture inventory regeneration;
- полная GitHub Actions CI-матрица PR #488.

### PR и commit

- PR: `#488`
- основной commit реализации: `03762369d7c377f58c9b0ef254c4a7ca64eec2e8`
- commit ремонта CI и architecture baseline: `dadd9905482ddbbad5075a12460b69634f4f06be`

### Ремонт CI

- PostgreSQL integration fixtures очищают `media_delivery_jobs` до `ai_tasks`;
- устаревший тест прямой GRS-доставки заменён проверкой durable delivery ownership;
- пересобраны P2 stability, repository layout, Telegram navigation и package architecture inventories;
- обновлены reviewed numeric baselines и канонические inventory labels;
- временные repair-workflows удалены, штатная `.github/workflows/tests.yml` восстановлена.

### Незавершённое

Физическое удаление устаревших installer stages и дальнейшее упрощение composition остаётся в scope issue #455. Для issue #457 активная доставка уже принадлежит единому durable pipeline.

### Следующий шаг

Подтвердить чистую CI-матрицу финального head и после этого перевести PR из draft в ready.
