# Сессия: перенос archive/public archive presentation controllers

- Дата: 2026-07-19
- ID: `2026-07-19-p3c-archive-public-controllers`
- Линия/фаза: Velvet Archive, P3C
- Статус: `частично`
- Ветка: `agent/p3c-archive-public-controllers`
- Базовый commit: `1e4dc6194a2b9671979a32d473537b46c59c6818`

## Перед началом

### Цель

Перенести связный набор активных Telegram-контроллеров сохранения и открытого архива из legacy `velvet_bot/handlers` в канонические presentation-пакеты без изменения команд, callback contracts, порядка регистрации и поведения пользовательских сценариев.

### Исходный контекст

После слияния PR #198 архитектурный inventory содержал 44 активных legacy implementations и 24 временных module aliases. Следующим P3C-срезом были назначены контроллеры archive/public archive.

### Планируемый объём

- перенести `archive`, `guest_archive` и `spoiler_save` в `presentation/telegram/routers/archive/`;
- перенести `public_archive`, `public_manager`, `public_media_display` и `public_notification_open` в `presentation/telegram/routers/public_archive/`;
- заменить старые handler-файлы module aliases того же объекта;
- перевести active router bundle на canonical imports при неизменном порядке 32 registrations;
- обновить Phase 9 source-path contract, P3 router inventory и layout inventory;
- добавить regression-тесты module identity и canonical ownership;
- не менять команды, callback data, PostgreSQL repositories, media delivery и тексты.

### Критерии готовности

- canonical archive/public archive modules содержат реальные router implementations;
- legacy paths возвращают те же module objects и не содержат decorators;
- publication router остаётся перед catch-all archive router;
- active legacy implementations уменьшаются с 44 до 37;
- aliases увеличиваются с 24 до 31;
- полный tests, Docker build и project notes contract зелёные.

### Риски и ограничения

Контроллеры используют исторические imports друг друга, а `archive` содержит catch-all обработчик сообщений темы. Внутренние legacy imports сохраняются через aliases, а порядок регистрации не меняется, чтобы физический перенос не смешивался с cleanup import graph и изменением маршрутизации.

## После завершения

### Фактически сделано

- семь archive/public archive controllers перенесены в canonical presentation packages;
- старые paths заменены короткими aliases через `importlib` и `sys.modules`;
- `archive_and_public` использует canonical imports без изменения порядка 32 routers;
- Phase 9 и P3 architecture contracts переведены на canonical paths;
- добавлены проверки identity, alias size, canonical router ownership и порядка imports;
- layout inventory обновлён до 37 implementations и 31 aliases.

### Миграции и совместимость

Миграции PostgreSQL не требуются и не изменялись. Команды `/save`, `/save18`, `/archive`, `/gallery`, callback prefixes, Guest Mode, public likes/subscriptions, media downloads и manager actions сохранены. Старые import paths и monkeypatch targets продолжают работать.

### Проверки

Статическая сверка router order и layout inventory выполнена. Обязательные GitHub Actions будут зафиксированы после открытия PR.

### PR и commit

- ветка: `agent/p3c-archive-public-controllers`;
- PR: будет создан после фиксации worklog и inventory;
- основной перенос выполнен серией содержательных commits через GitHub Contents API.

### Незавершённое

До завершения среза требуется получить зелёные tests, Docker build и project notes contract, затем обновить эту запись финальными номерами прогонов. Внутренние imports через legacy aliases остаются контролируемой совместимостью P3D.

### Следующий шаг

После зелёного CI слить archive/public archive PR и продолжить отдельным P3C-срезом переноса publication presentation controllers.
