# Сессия: явные presentation contracts workspace home

- Дата: 2026-07-24
- ID: `2026-07-24-workspace-home-presentation-contracts`
- Линия/фаза: workspace architecture cleanup
- Статус: `завершено`
- Ветка: `agent/workspace-home-presentation-contracts`
- Базовый commit: `61d361fd38c84b56f8f3346ac6126965cd12ec70`

## Перед началом

### Цель

Удалить последние runtime-подмены home keyboard и render functions из `workspace_product_experience.py`, сохранив настройки подсказок и scoped Telegram commands через явные presentation contracts.

### Исходный контекст

Workspace installer сохранял оригинальные `_workspace_home_keyboard`, `_render_home` и `_render_member_home`, оборачивал их через `ContextVar`, повторно запрашивал роли и присваивал wrappers обратно в `workspace_owner_controls`. `owner_menu.py` вызывал installer во время импорта. Дополнительно `save_mode_runtime.py` подменял старый command builder ради `/save_set`.

### Планируемый объём

- сделать `show_button_hints` явным параметром canonical home keyboard;
- читать preference и settings через публичный `WorkspaceProductService`;
- вынести role-aware Telegram command menu в отдельный presentation contract;
- устанавливать scoped commands из canonical render functions;
- удалить original aliases, ContextVar, wrappers, installer и import-time вызов;
- включить `/save` и `/save_set` в единый canonical command menu;
- перевести существующие тесты на canonical APIs;
- добавить functional и architecture regression coverage.

### Критерии готовности

- home keyboard не зависит от ContextVar или порядка импортов;
- owner/member render не подменяются runtime installer;
- owner controls не обращается к private `_workspaces`;
- role-aware command menu доступно через явный модуль;
- owner menu подключает router без installer side effect;
- save-mode runtime не подменяет command builder;
- focused и полный CI зелёные.

### Риски и ограничения

Callback data, роли, module checks и внешний Telegram UX должны сохраниться. Срез не переносит обработчики архива или watermark из `workspace_product_experience.py`.

## После завершения

### Фактически сделано

- `show_button_hints` стал явным параметром canonical home keyboard;
- owner/member render используют публичные service contracts;
- role-aware commands вынесены в `workspace_command_menu.py`;
- `/save` и `/save_set` включены в единый canonical command menu;
- scoped commands устанавливаются из canonical render functions;
- удалены ContextVar, original aliases, home/render wrappers, installer и import-time вызов;
- `save_mode_runtime.py` больше не подменяет workspace command builder;
- обновлены прежние boundary tests и Telegram navigation inventory;
- добавлены functional и architecture regression-тесты;
- временные transformation scripts и workflows удалены.

### Миграции и совместимость

Миграции не требуются. Callback data, role thresholds, module checks и маршруты `/save`/`/save_set` сохраняются.

### Проверки

- checked transformations: success;
- focused home presentation tests: success;
- existing workspace command tests: success;
- quick references contract: success;
- hint preference boundary: success;
- save single/set and forwarded-media routing: success;
- owner-menu composition: success;
- Telegram navigation inventory: success;
- Docker build `1253`: success;
- type check `503`: success;
- полный suite `1850`: 1317 тестов, все кодовые тесты success; единственный failure был вызван промежуточным статусом worklog и устранён этим commit;
- финальный CI повторно запущен с допустимым статусом `завершено`.

### PR и commit

- PR: `#317 Replace workspace home runtime wrappers with explicit contracts`;
- applied implementation head: `2b5704b421b8806cc1b2a568f096f63c19fc7b92`.

### Незавершённое

Нет в рамках этого среза.

### Следующий шаг

После merge разделить оставшийся `workspace_product_experience.py` на архивный и watermark controller без runtime installation logic.
