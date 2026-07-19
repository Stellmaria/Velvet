# Сессия: перенос archive/public archive presentation controllers

- Дата: 2026-07-19
- ID: `2026-07-19-p3c-archive-public-controllers`
- Линия/фаза: Velvet Archive, P3C
- Статус: `завершено`
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
- publication router сохранён перед catch-all обработчиком автоматического архива темы;
- Phase 9 и P3 architecture contracts переведены на canonical paths;
- добавлены проверки identity, alias size, canonical router ownership и порядка imports;
- layout inventory обновлён до 37 implementations и 31 aliases.

### Миграции и совместимость

Миграции PostgreSQL не требуются и не изменялись. Команды `/save`, `/save18`, `/archive`, `/gallery`, callback prefixes, Guest Mode, public likes/subscriptions, media downloads и manager actions сохранены. Старые import paths и monkeypatch targets продолжают работать.

### Проверки

- tests #974: 862 теста, success;
- docker build #510: success;
- project notes contract #371: success;
- architecture inventory: root imports 0, active routers 55, archive/public bundle 32, duplicates 0, implementations 37, aliases 31;
- отдельные исправления после первого CI не потребовались.

### PR и commit

- PR: #199 `Move archive and public archive controllers into presentation`;
- ветка: `agent/p3c-archive-public-controllers`;
- основной перенос выполнен серией содержательных commits через GitHub Contents API;
- финальная документационная фиксация выполнена после зелёного CI.

### Незавершённое

Внутренние imports между частью archive/public archive controllers всё ещё проходят через совместимые legacy aliases. Это контролируемый остаток P3D и не влияет на runtime semantics. Очистка import graph выполняется только отдельным срезом после завершения физических переносов.

### Следующий шаг

Слить PR #199 после зелёного финального CI. Затем продолжить отдельным P3C-срезом переноса publication presentation controllers.
