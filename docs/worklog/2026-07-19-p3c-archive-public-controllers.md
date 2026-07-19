# Сессия: перенос оставшихся archive-and-public controllers в presentation

- Дата: 2026-07-19
- ID: `2026-07-19-p3c-archive-public-controllers`
- Линия/фаза: Velvet Archive, P3C
- Статус: `завершено`
- Ветка: `agent/p3c-archive-public-controllers`
- Базовый commit: `c335e670ef2429f9d9846e1cbaab06882b11fe13`

## Перед началом

### Цель

Убрать последние прямые imports из `velvet_bot.handlers` в bundle `archive_and_public`, сохранив существующие команды, callback contracts, порядок регистрации и поведение архивных, стартовых и служебных Telegram-контроллеров.

### Исходный контекст

После merge PR #207 bundles analytics, core operations и quality operations полностью используют canonical presentation paths. В `archive_and_public` оставались девять прямых legacy controllers: Telegram analytics import, discussion updates, `/start`, привязка промтов, три admin media controller, media browser и inline help.

### Планируемый объём

- создать пакет `archive_and_public_controllers`;
- перенести девять implementations с повторным использованием исходных Git blob SHA;
- заменить старые handler paths module aliases;
- переключить bundle на canonical imports без изменения include order;
- сохранить publication router перед archive catch-all;
- расширить P3C archive contracts на новые aliases;
- обновить общую P3 architecture contract и inventory;
- не менять бизнес-логику, SQL, миграции, callback data, команды, права или пользовательские тексты.

### Критерии готовности

- bundle не импортирует ни одного `velvet_bot.handlers.*` controller;
- legacy imports возвращают те же canonical module objects;
- canonical files содержат реальные router implementations;
- число active bundle routers остаётся 56, дублей остаётся 0;
- active legacy implementations уменьшаются с 14 до 5;
- handler aliases увеличиваются с 54 до 63;
- publication router остаётся перед archive catch-all;
- tests, Docker build и project notes contract зелёные.

### Риски и ограничения

Bundle объединяет несвязанные исторические функции. Поэтому срез меняет только физическое владение controller modules. Декомпозиция больших media handlers, удаление aliases и классификация пяти оставшихся standalone implementations вынесены в P3D. Исходные blobs переиспользованы без ручного копирования.

## После завершения

### Фактически сделано

- создан `velvet_bot/presentation/telegram/routers/archive_and_public_controllers`;
- перенесены девять оставшихся прямых legacy controllers;
- старые paths заменены module aliases;
- `archive_and_public.py` использует только canonical presentation paths;
- порядок регистрации сохранён;
- расширены `test_p3c_archive_public_controllers.py` и общий P3 router contract;
- inventory обновлён до 5 active implementations и 63 aliases;
- следующим этапом назначен P3D: классификация пяти standalone implementations и controlled compatibility retirement.

### Миграции и совместимость

Миграции PostgreSQL не нужны. Slash-команды, callbacks, middleware boundaries, Telegram file IDs, media display behavior, analytics import, `/start`, inline help и archive catch-all не изменены. Legacy imports сохраняют module identity.

### Проверки

- первый CI: Docker build #558 и project notes contract #412 прошли; tests #1022 выявил только устаревший source-path contract;
- `tests/test_phase9_owner_use_cases.py` переведён с legacy `handlers/telegram_analytics_import.py` на canonical controller;
- повторный CI: tests #1025, Docker build #561, project notes contract #414 — success;
- active bundle routers: 56;
- duplicate registrations: 0;
- direct legacy imports в domain bundles: 0;
- active legacy implementations: 5, aliases: 63.

### PR и commit

- PR: #208 `Move remaining archive and public controllers into presentation`;
- рабочая ветка: `agent/p3c-archive-public-controllers`;
- runtime move commit: `6220476c4abdee43abdc5a4a4ecd18ff8aeb4b0a`;
- проверенный runtime head: `5658792a4343028a5bf90cd81440d4c43deaa61e`.

### Незавершённое

Пять standalone handler implementations ещё требуют классификации в P3D: являются ли они активными runtime controllers, вложенными routers или служебными файлами. Это не блокирует завершение bundle migration.

### Следующий шаг

Слить PR #208. После этого реализовать разрешение крупных архивных изображений для администраторов и модераторов и добавить быстрые теги/алиасы персонажей для `/save` и других сценариев разрешения имени.
