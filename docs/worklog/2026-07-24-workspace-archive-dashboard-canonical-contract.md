# Сессия: canonical workspace archive dashboard contract

- Дата: 2026-07-24
- ID: `2026-07-24-workspace-archive-dashboard-canonical-contract`
- Линия/фаза: workspace architecture cleanup
- Статус: `завершено`
- Ветка: `agent/archive-dashboard-canonical-contract`
- Базовый commit: `fcd76d402acf90ac626124a0468cc37c3ba27230`

## Перед началом

### Цель

Сделать публичный archive dashboard contract фактическим владельцем загрузки строк, клавиатуры и callback-представления, чтобы команда `/archive` и кнопка модуля использовали одну реализацию без private presentation helpers.

### Исходный контекст

После PR #319 отдельный archive command controller уже использовал `build_workspace_archive_dashboard`, но сам contract оставался compatibility wrapper над `_load_archive_characters` и `_archive_dashboard_keyboard` из `workspace_owner_controls.py`. Callback кнопки модуля продолжал обрабатывать legacy handler этого большого router.

### Планируемый объём

- перенести SQL-загрузку и построение dashboard keyboard в публичный contract;
- добавить типизированную immutable строку персонажа;
- добавить отдельный callback controller для `wsp:module:archive`;
- подключить новый router перед broad owner-controls router;
- обновить функциональные и architecture regressions;
- актуализировать Telegram navigation inventory.

### Критерии готовности

- `workspace_archive_dashboard.py` не импортирует private archive helpers;
- `/archive` и кнопка модуля используют `build_workspace_archive_dashboard`;
- callback controller сохраняет viewer role и module checks;
- canonical router подключён раньше `workspace_owner_controls_router`;
- dashboard text, empty states, topic links и возврат в workspace покрыты тестами;
- navigation inventory не содержит violations.

### Риски и ограничения

Legacy `_load_archive_characters`, `_archive_dashboard_keyboard` и `_render_archive_dashboard` пока физически остаются в `workspace_owner_controls.py`, но после этого среза не участвуют ни в command, ни в module callback flow. Их удаление остаётся отдельным механическим шагом из-за размера исторического файла.

## После завершения

### Фактически сделано

- `workspace_archive_dashboard.py` теперь сам загружает типизированные `WorkspaceArchiveCharacter`;
- публичный builder самостоятельно формирует character keyboard и итоговый dashboard;
- удалена compatibility-зависимость от private loader и keyboard helpers;
- добавлен `workspace_archive_dashboard_controller.py` для callback входа модуля;
- новый router подключён перед `workspace_owner_controls_router`;
- добавлены regressions для текста, кнопок, topic URL, workspace navigation и router order;
- Telegram navigation inventory обновлён до 441 Python-файла без violations.

### Миграции и совместимость

Миграции не требуются. SQL, callback prefix `wpa`, workspace callback data, роли, module checks и пользовательские тексты сохранены.

### Проверки

- source-level architecture regressions обновлены;
- functional dashboard contract tests обновлены;
- router composition regression добавлен;
- полный type check, test suite, project notes contract и Docker build выполняются в PR CI.

### PR и commit

- ветка: `agent/archive-dashboard-canonical-contract`;
- PR: `#320 Make workspace archive dashboard canonical`.

### Незавершённое

Функциональных незавершённых пунктов в рамках среза нет. Legacy archive dashboard helpers остаются только как недостижимый исторический код внутри `workspace_owner_controls.py`.

### Следующий шаг

Удалить из `workspace_owner_controls.py` legacy `_load_archive_characters`, `_archive_dashboard_keyboard`, `_render_archive_dashboard` и старый `handle_workspace_archive_entry`, затем опубликовать canonical home keyboard contract вместо `_workspace_home_keyboard`.
