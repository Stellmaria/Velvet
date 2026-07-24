# Сессия: archive presentation contract и явный home hint controller

- Дата: 2026-07-24
- ID: `2026-07-24-workspace-archive-presentation-contract`
- Линия/фаза: workspace architecture cleanup
- Статус: `завершено`
- Ветка: `agent/workspace-archive-presentation-contract`
- Базовый commit: `1ecceed19d0319fd081bd5c298b8a322e7c71354`

## Перед началом

### Цель

Убрать прямое использование private archive presentation helpers из отдельного archive controller и заменить историческое имя `workspace_product_experience.py` на имя, соответствующее фактической ответственности контроллера.

### Исходный контекст

После PR #318 команда `/archive` находилась в отдельном router, но импортировала `_load_archive_characters` и `_archive_dashboard_keyboard` напрямую из большого `workspace_owner_controls.py`. Оставшийся home preference controller при этом всё ещё назывался `workspace_product_experience.py`, хотя обслуживал только переключение подсказок.

### Планируемый объём

- добавить явную archive dashboard view-модель;
- предоставить публичный builder готового текста и клавиатуры;
- перевести archive command controller на публичный contract;
- переименовать home preference controller;
- обновить router composition и architecture tests;
- сохранить текущие тексты, callback data, role и module checks.

### Критерии готовности

- `workspace_archive_controller.py` не импортирует `workspace_owner_controls` и private archive helpers;
- archive dashboard contract возвращает готовые text, keyboard и character count;
- исторический `workspace_product_experience.py` удалён;
- `owner_menu.py` подключает явно названный `workspace_home_hint_router`;
- функциональный и architecture regression coverage обновлены;
- Telegram navigation inventory актуален.

### Риски и ограничения

Срез сохраняет legacy реализации загрузки строк и построения клавиатуры внутри `workspace_owner_controls.py`, но изолирует их за единственной compatibility boundary в публичном presentation contract. SQL, callback data и пользовательские сценарии не меняются.

## После завершения

### Фактически сделано

- добавлен `workspace_archive_dashboard.py` с immutable `WorkspaceArchiveDashboard`;
- builder формирует готовый текст, keyboard и character count;
- `workspace_archive_controller.py` больше не знает о private archive helpers;
- добавлен `workspace_home_hint_controller.py` с фактической home hint ответственностью;
- удалён исторический `workspace_product_experience.py`;
- `owner_menu.py` переведён на `workspace_home_hint_router`;
- обновлены controller, hint, quick references, template callback, home presentation и router-order tests;
- добавлен функциональный тест archive dashboard view-модели;
- Telegram navigation inventory обновлён до 440 Python-файлов.

### Миграции и совместимость

Миграции не требуются. `/archive`, archive callback data, роли, module checks, тексты интерфейса и порядок специализированных routers сохранены.

### Проверки

- source-level architecture regressions обновлены;
- функциональный archive dashboard contract test добавлен;
- изменённые Python-файлы подготовлены к type check и полному test suite в PR CI;
- Telegram navigation inventory обновлён без violations.

### PR и commit

- ветка: `agent/workspace-archive-presentation-contract`;
- PR создаётся после финального сравнения ветки с `main`.

### Незавершённое

Функциональных незавершённых пунктов в рамках этого среза нет. Legacy archive dashboard implementation пока остаётся в `workspace_owner_controls.py` и доступна новому contract только как изолированная compatibility boundary.

### Следующий шаг

Перевести canonical callback dashboard внутри `workspace_owner_controls.py` на публичный `build_workspace_archive_dashboard`, затем удалить legacy `_load_archive_characters` и `_archive_dashboard_keyboard` полностью. После этого опубликовать home keyboard contract вместо оставшегося private `_workspace_home_keyboard`.
