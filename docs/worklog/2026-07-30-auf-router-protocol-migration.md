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
SQL/module storage migration выполняется отдельной фазой и не смешивается с Telegram protocol change. Старые callback payload и точные имена прежних FSM-групп сохраняются только в явной compatibility-границе, чтобы уже отправленные кнопки и незавершённые сценарии не терялись.

## После завершения

### Фактически сделано
- реальные photo/video/root/runtime/balance routers перенесены в `workspace_auf*`;
- controller и tests переключены на canonical symbols;
- новые callback prefixes: `auf:` и `aufv|`;
- legacy parsers принимают `meow:` и `meowv|`;
- новое workspace action: `auf`, legacy action `meow` продолжает приниматься;
- access-policy allowlist содержит новые и старые prefixes;
- active photo/video routers пишут только `auf_*` FSM-ключи и используют прямые строки «Ауф»;
- core photo-flow читает новые FSM-ключи с fallback на прежние `meow_*`;
- runtime branding monkey-patch больше не устанавливается;
- photo-ratio hotfix переведён на canonical `workspace_auf_photo` и `handle_scoped_auf_action`;
- persistent SQL identifiers возвращены к реально развёрнутой схеме;
- retired router files сведены к compatibility delegation;
- добавлены архитектурные контракты для router boundary, FSM dual-read и storage identifiers.

### Миграции и совместимость
PostgreSQL schema и module key не менялись. Старые Telegram callback payload принимаются через `LegacyMeowCallback` и `LegacyMeowVideoCallback`; старые FSM-группы находятся только в `workspace_auf_legacy.py`. Canonical routers создают новые payload и пишут новые `auf_*` данные.

### Проверки
- architecture, P2 stability и Telegram navigation inventories пересобраны;
- `python -m compileall -q velvet_bot tests` — успешно на cleanup head;
- встроенный audit подтвердил отсутствие пользовательского бренда «Мяу» в active routers;
- core dual-read helper и fallback `auf_workspace_id → meow_workspace_id` закреплены contract test;
- полный tests workflow, type check, Docker build и project notes contract запускаются на итоговом пользовательском commit.

### PR и commit
- PR: #428;
- active-router cleanup: `eac923df754aa7821bc88a1fd8d83e14d185e200`;
- core dual-read repair: `384df58f7aa8eac0c9416d59f5a4f33cca3fbdde`;
- merge commit фиксируется после зелёного CI.

### Незавершённое
- транзакционная SQL/module-key migration persistent `meow_*` identifiers;
- удаление legacy callback/FSM parsers после окончания переходного периода.

### Следующий шаг
После зелёного CI слить PR #428. Persistent SQL/module identifiers переименовывать только отдельной миграцией с backfill, dual-read/dual-write и проверкой production restore.
