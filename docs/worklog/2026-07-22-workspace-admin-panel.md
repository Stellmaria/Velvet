# Сессия: кнопочная панель управления личными пространствами

- Дата: 2026-07-22
- ID: `2026-07-22-workspace-admin-panel`
- Линия/фаза: personal workspace administration
- Статус: `частично`
- Ветка: `agent/workspace-admin-panel-2`
- Базовый commit: `cf6cc71e5f157311a9a0f421448dc096612418ba`

## Перед началом

### Цель

Добавить Стэл отдельную кнопочную панель управления разрешениями на создание личных архивов и доступностью модулей в уже созданных пространствах.

### Исходный контекст

После включения пользовательского интерфейса личного пространства Стэл могла управлять доступами только slash-командами `/workspace_grant`, `/workspace_revoke` и `/workspace_module`. Кнопка «Пространства» в owner menu открывала системный workspace ID 1, а не список пользователей, разрешений и личных архивов.

### Планируемый объём

- заменить вход «Пространства» в owner menu на административную панель;
- показать список creation grants и созданных личных пространств;
- добавить карточку Telegram ID с состоянием grant, лимитом и архивами;
- добавить выдачу доступа через кнопочную FSM-форму;
- добавить переключатели модулей будущего архива;
- добавить переключатели `is_allowed` для модулей существующего workspace;
- сохранить отдельный пользовательский `is_enabled` и запрет удаления системного Velvet;
- добавить pagination, проверки global owner и regression tests;
- обновить generated inventories и справочные контракты.

### Критерии готовности

- Стэл открывает управление пространствами одной кнопкой из `/menu`;
- видны активные и отозванные разрешения;
- новый Telegram ID получает grant без slash-команды;
- модули future grant переключаются кнопками;
- существующие workspace открываются из карточки пользователя;
- модуль существующего workspace разрешается или запрещается кнопкой;
- отключение `public_archive` также выключает публичность;
- обычный пользователь не может вызвать административные callbacks;
- tests, type-check, Docker и project notes contract проходят.

### Риски и ограничения

Telegram Bot API не позволяет получить имя произвольного пользователя только по ID, поэтому панель гарантированно показывает Telegram ID и данные workspace. Имя или username не выдумываются. Отзыв creation grant не удаляет уже созданный архив и не лишает владельца его данных; существующие модули управляются отдельно.

## После завершения

### Фактически сделано

- кнопка «🏛 Пространства» открывает отдельную панель Стэл;
- добавлены списки grants и личных архивов с pagination;
- добавлена выдача доступа по Telegram ID через FSM-форму;
- добавлены переключатели модулей future grant;
- добавлены переключатели `is_allowed` существующего workspace;
- отключение `public_archive` также выключает публичность;
- пользовательский `is_enabled` сохранён отдельно от политики Стэл;
- persistence размещён в domain administration service, Telegram controller не содержит SQL;
- добавлены global-owner guards, regression tests и mobile-safe подписи кнопок;
- обновлены architecture, P2 stability, repository layout и Telegram navigation inventories.

### Миграции и совместимость

Новая миграция не требуется. Используются существующие `workspace_creation_grants`, `workspace_members`, `workspace_modules`, `workspace_settings` и `characters`. Старые slash-команды сохранены как аварийный резерв.

### Проверки

Проверенный implementation head до финализации журнала: `60be992d1fb07e1749b3bb5377fe47fb8566abc7`.

- tests run `1622`: **1162 tests, success**;
- type check run `275`: **success**;
- Docker build run `1068`: **success**;
- project notes contract run `925`: **success**.

Первый прогон отдельно выявил только ожидаемые generated inventory, worklog и mobile navigation-contract хвосты. Они исправлены и повторный полный CI прошёл.

### PR и commit

PR #293: `Add button-based workspace administration for Stel`.

Ветка содержит domain administration service, owner controller, UI-клавиатуры, regression tests и generated contracts. Временные workflow после обновления inventories удалены.

### Незавершённое

Требуется живая Telegram-проверка после merge: открыть панель Стэл, выдать тестовый grant, переключить future module и модуль существующего тестового workspace. Это эксплуатационная проверка, поэтому статус остаётся `частично`.

### Следующий шаг

Обновить локальный `main`, перезапустить бота и проверить новый путь `/menu` → «🏛 Пространства» от имени Стэл.
