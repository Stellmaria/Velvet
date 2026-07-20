# Инвентаризация consumers handler aliases

Машинный срез оставшегося compatibility API `velvet_bot.handlers.*` после закрытия production consumers.

## Сводка

- alias-файлов: **25**;
- файлов-consumers: **23**;
- references: **57**;
- aliases с references: **25**;
- aliases без references: **0**;
- динамических prefix references: **2**;
- references на уже отсутствующие aliases: **0**.

## Alias status

- `velvet_bot.handlers.analytics_dashboard` → `velvet_bot.presentation.telegram.routers.analytics_controllers.dashboard`: используется.
- `velvet_bot.handlers.analytics_dashboard_overrides` → `velvet_bot.presentation.telegram.routers.analytics_controllers.dashboard_overrides`: используется.
- `velvet_bot.handlers.analytics_discussion_overrides` → `velvet_bot.presentation.telegram.routers.analytics_controllers.discussion_overrides`: используется.
- `velvet_bot.handlers.analytics_management` → `velvet_bot.presentation.telegram.routers.analytics_controllers.management`: используется.
- `velvet_bot.handlers.analytics_management_aliases` → `velvet_bot.presentation.telegram.routers.analytics_controllers.management_aliases`: используется.
- `velvet_bot.handlers.analytics_management_common` → `velvet_bot.presentation.telegram.routers.analytics_controllers.management_common`: используется.
- `velvet_bot.handlers.analytics_management_publications` → `velvet_bot.presentation.telegram.routers.analytics_controllers.management_publications`: используется.
- `velvet_bot.handlers.analytics_management_tags` → `velvet_bot.presentation.telegram.routers.analytics_controllers.management_tags`: используется.
- `velvet_bot.handlers.backup_center` → `velvet_bot.presentation.telegram.routers.quality_operations_controllers.backup_center`: используется.
- `velvet_bot.handlers.channel_analytics` → `velvet_bot.presentation.telegram.routers.analytics_controllers.channel`: используется.
- `velvet_bot.handlers.error_center` → `velvet_bot.presentation.telegram.routers.core_operations_controllers.error_center`: используется.
- `velvet_bot.handlers.owner_actions` → `velvet_bot.presentation.telegram.routers.core_operations_controllers.owner_actions`: используется.
- `velvet_bot.handlers.owner_menu` → `velvet_bot.presentation.telegram.routers.core_operations_controllers.owner_menu`: используется.
- `velvet_bot.handlers.publication_center` → `velvet_bot.presentation.telegram.routers.publication.center`: используется.
- `velvet_bot.handlers.publication_center_safe` → `velvet_bot.presentation.telegram.routers.publication.safe`: используется.
- `velvet_bot.handlers.supervisor_codex` → `velvet_bot.presentation.telegram.routers.supervisor.codex`: используется.
- `velvet_bot.handlers.supervisor_console` → `velvet_bot.presentation.telegram.routers.supervisor.console`: используется.
- `velvet_bot.handlers.supervisor_control` → `velvet_bot.presentation.telegram.routers.supervisor.control`: используется.
- `velvet_bot.handlers.supervisor_git` → `velvet_bot.presentation.telegram.routers.supervisor.git`: используется.
- `velvet_bot.handlers.supervisor_logs` → `velvet_bot.presentation.telegram.routers.supervisor.logs`: используется.
- `velvet_bot.handlers.supervisor_process` → `velvet_bot.presentation.telegram.routers.supervisor.process`: используется.
- `velvet_bot.handlers.supervisor_self` → `velvet_bot.presentation.telegram.routers.supervisor.self_control`: используется.
- `velvet_bot.handlers.supervisor_status` → `velvet_bot.presentation.telegram.routers.supervisor.status`: используется.
- `velvet_bot.handlers.system_center` → `velvet_bot.presentation.telegram.routers.system`: используется.
- `velvet_bot.handlers.watermark` → `velvet_bot.presentation.telegram.routers.core_operations_controllers.watermark`: используется.

## Consumers

### `scripts/inventory_architecture_layout.py`

- line 139: `velvet_bot.handlers` (dynamic-prefix-reference).

### `tests/test_analytics_dashboard.py`

- line 4: `velvet_bot.handlers.analytics_dashboard` (from-import).

### `tests/test_analytics_phase2_callbacks.py`

- line 5: `velvet_bot.handlers.analytics_management` (from-import).

### `tests/test_fresh_runtime_log_hotfix.py`

- line 12: `velvet_bot.handlers.supervisor_status` (import).

### `tests/test_inline_management_menus.py`

- line 17: `velvet_bot.handlers.supervisor_control` (from-import).

### `tests/test_owner_action_menu.py`

- line 7: `velvet_bot.handlers.owner_actions` (from-import).

### `tests/test_p2ae_supervisor_console_watcher.py`

- line 6: `velvet_bot.handlers.supervisor_console` (import).

### `tests/test_p2p_backup_center_boundary.py`

- line 7: `velvet_bot.handlers.backup_center` (import).

### `tests/test_p2q_channel_analytics_boundary.py`

- line 7: `velvet_bot.handlers.channel_analytics` (import).

### `tests/test_p2s_error_center_markup_boundary.py`

- line 7: `velvet_bot.handlers.error_center` (import).

### `tests/test_p2x_publication_report_boundary.py`

- line 7: `velvet_bot.handlers.publication_center` (import).

### `tests/test_p3c_analytics_controllers.py`

- line 9: `velvet_bot.handlers.channel_analytics` (literal-reference).
- line 12: `velvet_bot.handlers.analytics_dashboard_overrides` (literal-reference).
- line 15: `velvet_bot.handlers.analytics_discussion_overrides` (literal-reference).
- line 18: `velvet_bot.handlers.analytics_management` (literal-reference).
- line 21: `velvet_bot.handlers.analytics_dashboard` (literal-reference).
- line 24: `velvet_bot.handlers.analytics_management_common` (literal-reference).
- line 27: `velvet_bot.handlers.analytics_management_tags` (literal-reference).
- line 30: `velvet_bot.handlers.analytics_management_aliases` (literal-reference).
- line 33: `velvet_bot.handlers.analytics_management_publications` (literal-reference).
- line 76: `velvet_bot.handlers.channel_analytics` (literal-reference).
- line 77: `velvet_bot.handlers.analytics_dashboard_overrides` (literal-reference).
- line 78: `velvet_bot.handlers.analytics_discussion_overrides` (literal-reference).
- line 79: `velvet_bot.handlers.analytics_management` (literal-reference).
- line 80: `velvet_bot.handlers.analytics_dashboard` (literal-reference).

### `tests/test_p3c_core_operations_controllers.py`

- line 10: `velvet_bot.handlers.error_center` (literal-reference).
- line 13: `velvet_bot.handlers.owner_actions` (literal-reference).
- line 16: `velvet_bot.handlers.owner_menu` (literal-reference).
- line 19: `velvet_bot.handlers.watermark` (literal-reference).

### `tests/test_p3c_publication_controllers.py`

- line 10: `velvet_bot.handlers.publication_center` (literal-reference).
- line 13: `velvet_bot.handlers.publication_center_safe` (literal-reference).

### `tests/test_p3c_quality_operations_controllers.py`

- line 40: `velvet_bot.handlers` (dynamic-prefix-reference).

### `tests/test_p3c_supervisor_system_presentation.py`

- line 9: `velvet_bot.handlers.supervisor_control` (literal-reference).
- line 12: `velvet_bot.handlers.supervisor_status` (literal-reference).
- line 15: `velvet_bot.handlers.supervisor_process` (literal-reference).
- line 18: `velvet_bot.handlers.supervisor_git` (literal-reference).
- line 21: `velvet_bot.handlers.supervisor_logs` (literal-reference).
- line 24: `velvet_bot.handlers.supervisor_console` (literal-reference).
- line 27: `velvet_bot.handlers.supervisor_self` (literal-reference).
- line 30: `velvet_bot.handlers.supervisor_codex` (literal-reference).
- line 33: `velvet_bot.handlers.system_center` (literal-reference).
- line 70: `velvet_bot.handlers.supervisor_control` (literal-reference).
- line 71: `velvet_bot.handlers.system_center` (literal-reference).

### `tests/test_p3d_residual_handler_classification.py`

- line 12: `velvet_bot.handlers.analytics_management_common` (literal-reference).
- line 15: `velvet_bot.handlers.analytics_management_tags` (literal-reference).
- line 18: `velvet_bot.handlers.analytics_management_aliases` (literal-reference).
- line 21: `velvet_bot.handlers.analytics_management_publications` (literal-reference).
- line 24: `velvet_bot.handlers.watermark` (literal-reference).

### `tests/test_phase14_analytics_management_split.py`

- line 48: `velvet_bot.handlers.analytics_management` (literal-reference).

### `tests/test_phase5_discussion_and_backups.py`

- line 12: `velvet_bot.handlers.analytics_discussion_overrides` (from-import).
- line 16: `velvet_bot.handlers.backup_center` (from-import).

### `tests/test_phase6_runtime.py`

- line 12: `velvet_bot.handlers.system_center` (from-import).

### `tests/test_publication_workflow.py`

- line 7: `velvet_bot.handlers.publication_center` (from-import).
- line 8: `velvet_bot.handlers.publication_center_safe` (from-import).

### `tests/test_supervisor.py`

- line 16: `velvet_bot.handlers.supervisor_control` (from-import).

### `tests/test_supervisor_logs_callback.py`

- line 11: `velvet_bot.handlers.supervisor_logs` (from-import).
- line 41: `velvet_bot.handlers.supervisor_logs` (literal-reference).

## Следующий срез

- фаза: **P3D**;
- цель: **retire the next compatibility alias group**;
- стратегия: migrate tests to canonical modules, then delete only aliases with no repository references.

## Правило обновления

```bash
python scripts/inventory_handler_alias_consumers.py --write --label <phase>
python scripts/inventory_handler_alias_consumers.py --check --label <phase>
```
