# Сессия: явные presentation contracts workspace home

- Дата: 2026-07-24
- ID: `2026-07-24-workspace-home-presentation-contracts`
- Линия/фаза: workspace architecture cleanup
- Статус: `частично`
- Ветка: `agent/workspace-home-presentation-contracts`
- Базовый commit: `61d361fd38c84b56f8f3346ac6126965cd12ec70`

## Перед началом

### Цель

Удалить последние runtime-подмены home keyboard и render functions из `workspace_product_experience.py`, сохранив настройки подсказок и scoped Telegram commands через явные presentation contracts.

### Исходный контекст

Workspace installer сохранял оригинальные `_workspace_home_keyboard`, `_render_home` и `_render_member_home`, оборачивал их через `ContextVar`, повторно запрашивал роли и присваивал wrappers обратно в `workspace_owner_controls`. `owner_menu.py` вызывал installer во время импорта.

### Планируемый объём

- сделать `show_button_hints` явным параметром canonical home keyboard;
- читать preference и settings через публичный `WorkspaceProductService`;
- вынести role-aware Telegram command menu в отдельный presentation contract;
- устанавливать scoped commands из canonical render functions;
- удалить original aliases, ContextVar, wrappers, installer и import-time вызов;
- перевести существующие тесты на canonical APIs;
- добавить functional и architecture regression coverage.

### Критерии готовности

- home keyboard не зависит от ContextVar или порядка импортов;
- owner/member render не подменяются runtime installer;
- owner controls не обращается к private `_workspaces`;
- role-aware command menu доступно через явный модуль;
- owner menu подключает router без installer side effect;
- focused и полный CI зелёные.

### Риски и ограничения

Callback data, роли, module checks и внешний Telegram UX должны сохраниться. Срез не переносит обработчики архива или watermark из `workspace_product_experience.py`.

## После завершения

### Фактически сделано

- подготовлен explicit keyboard preference contract;
- подготовлен отдельный workspace command menu module;
- подготовлено удаление runtime installer и import-time mutation;
- добавлены functional и architecture regression-тесты.

### Миграции и совместимость

Миграции не требуются. Команды, callback data и role thresholds сохраняются.

### Проверки

Результаты будут записаны после применения checked transformation.

### PR и commit

Ветка `agent/workspace-home-presentation-contracts`; PR создаётся после focused validation.

### Незавершённое

- применить transformation;
- выполнить focused и полный CI;
- слить отдельный PR.

### Следующий шаг

После merge разделить оставшийся `workspace_product_experience.py` на архивный и watermark controller без runtime installation logic.
