# Инвентаризация consumers handler aliases

Машинный срез оставшегося compatibility API `velvet_bot.handlers.*` после закрытия production consumers.

## Сводка

- alias-файлов: **9**;
- файлов-consumers: **9**;
- references: **25**;
- aliases с references: **9**;
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
- `velvet_bot.handlers.channel_analytics` → `velvet_bot.presentation.telegram.routers.analytics_controllers.channel`: используется.

## Consumers

### `scripts/inventory_architecture_layout.py`

- line 139: `velvet_bot.handlers` (dynamic-prefix-reference).

### `tests/test_analytics_dashboard.py`

- line 4: `velvet_bot.handlers.analytics_dashboard` (from-import).

### `tests/test_analytics_phase2_callbacks.py`

- line 5: `velvet_bot.handlers.analytics_management` (from-import).

### `tests/test_p2q_channel_analytics_boundary.py`

- line 7: `velvet_bot.handlers.channel_analytics` (import).

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

### `tests/test_p3c_quality_operations_controllers.py`

- line 41: `velvet_bot.handlers` (dynamic-prefix-reference).

### `tests/test_p3d_residual_handler_classification.py`

- line 12: `velvet_bot.handlers.analytics_management_common` (literal-reference).
- line 15: `velvet_bot.handlers.analytics_management_tags` (literal-reference).
- line 18: `velvet_bot.handlers.analytics_management_aliases` (literal-reference).
- line 21: `velvet_bot.handlers.analytics_management_publications` (literal-reference).

### `tests/test_phase14_analytics_management_split.py`

- line 48: `velvet_bot.handlers.analytics_management` (literal-reference).

### `tests/test_phase5_discussion_and_backups.py`

- line 12: `velvet_bot.handlers.analytics_discussion_overrides` (from-import).

## Следующий срез

- фаза: **P3D**;
- цель: **retire the next compatibility alias group**;
- стратегия: migrate tests to canonical modules, then delete only aliases with no repository references.

## Правило обновления

```bash
python scripts/inventory_handler_alias_consumers.py --write --label <phase>
python scripts/inventory_handler_alias_consumers.py --check --label <phase>
```
