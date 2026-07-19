# Сессия: перенос оставшихся archive-and-public controllers в presentation

- Дата: 2026-07-19
- ID: `2026-07-19-p3c-archive-public-controllers`
- Линия/фаза: Velvet Archive, P3C
- Статус: `частично`
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

- source-level и inventory contracts подготовлены;
- полный CI будет записан после создания PR;
- active bundle routers: 56;
- duplicate registrations: 0;
- direct legacy imports в domain bundles: 0.

### PR и commit

- рабочая ветка: `agent/p3c-archive-public-controllers`;
- runtime move commit: `6220476c4abdee43abdc5a4a4ecd18ff8aeb4b0a`;
- PR и проверенный финальный head будут добавлены после CI.

### Незавершённое

До зелёного CI срез считается частично завершённым. Пять standalone handler implementations ещё требуют классификации: являются ли они активными runtime controllers, вложенными routers или служебными файлами, которые следует переносить либо удалить в P3D.

### Следующий шаг

Открыть PR, пройти CI и слить срез. После этого реализовать разрешение крупных архивных изображений для администраторов и модераторов и добавить быстрые теги/алиасы персонажей для `/save`.
