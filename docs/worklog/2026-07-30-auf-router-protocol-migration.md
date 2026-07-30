# 2026-07-30 — перенос Telegram router-протокола в Ауф

- Дата: 2026-07-30
- ID: `auf-router-protocol-migration`
- Линия/фаза: AI media generation / Telegram protocol cleanup
- Статус: `завершено`
- Ветка: `agent/final-auf-router-layer`
- Базовый commit: `28025c2b65b6aa70baf9c22d840ceab5b0394b1e`

## Перед началом

### Цель
Перенести активные generation-router файлы, callback classes и новые callback payload с Meow на Ауф, сохранив чтение уже отправленных Telegram-кнопок.

### Исходный контекст
Runtime и wallet уже находились в canonical `auf_*` domains, но production controller продолжал импортировать `workspace_meow*`, создавать `meow:`/`meowv|` payload и использовать классы `MeowCallback`/`MeowForm`.

### Планируемый объём
- создать canonical `workspace_auf*` routers;
- выпускать новые callback payload с `auf:` и `aufv|`;
- принимать старые payload через legacy parsers;
- перевести production imports и tests;
- оставить retired files короткими compatibility modules;
- синхронизировать generated inventories.

### Критерии готовности
- production imports используют `workspace_auf*`;
- новые кнопки используют Auf callback classes;
- старые callback payload продолжают маршрутизироваться;
- retired router files не содержат реализации;
- полный CI проходит.

### Риски и ограничения
Старые FSM-сессии могут потребовать повторного входа в незавершённый сценарий после deploy. SQL/module storage migration выполняется отдельной фазой и не смешивается с Telegram protocol change.

## После завершения

### Фактически сделано
- реальные photo/video/root/runtime/balance routers перенесены в `workspace_auf*`;
- controller и tests переключены на canonical symbols;
- новые callback prefixes: `auf:` и `aufv|`;
- legacy parsers принимают `meow:` и `meowv|`;
- новое workspace action: `auf`, legacy action `meow` продолжает приниматься;
- access-policy allowlist содержит новые и старые prefixes;
- retired router files сведены к compatibility delegation;
- добавлен архитектурный contract для router boundary.

### Миграции и совместимость
PostgreSQL schema и module key не менялись. Старые Telegram callback payload принимаются через `LegacyMeowCallback` и `LegacyMeowVideoCallback`.

### Проверки
Generated architecture, P2 stability и Telegram navigation inventories пересобираются после миграции; полный CI запускается на итоговом head.
Точечная очистка SQL-контракта, photo FSM/data и installer chain выполняется отдельным финальным commit перед CI.

### PR и commit
PR и итоговый commit фиксируются после зелёного CI.

### Незавершённое
- SQL table/module-key migration с `meow_*` на `auf_*`;
- удаление legacy callback parsers после окончания переходного периода;
- явная миграция незавершённых FSM-сессий, если production storage сохраняет их между deploy.

### Следующий шаг
Получить зелёный CI, слить router migration, затем отдельным PR переименовать persistent SQL/module identifiers с транзакционной data migration.
