# Инвентаризация consumers handler aliases

Машинный срез оставшегося compatibility API `velvet_bot.handlers.*` после закрытия production consumers.

## Сводка

- alias-файлов: **1**;
- файлов-consumers: **5**;
- references: **5**;
- aliases с references: **1**;
- aliases без references: **0**;
- динамических prefix references: **2**;
- references на уже отсутствующие aliases: **0**.

## Alias status

- `velvet_bot.handlers.channel_analytics` → `velvet_bot.presentation.telegram.routers.analytics_controllers.channel`: используется.

## Consumers

### `scripts/inventory_architecture_layout.py`

- line 139: `velvet_bot.handlers` (dynamic-prefix-reference).

### `tests/test_p2q_channel_analytics_boundary.py`

- line 7: `velvet_bot.handlers.channel_analytics` (import).

### `tests/test_p3c_analytics_controllers.py`

- line 8: `velvet_bot.handlers.channel_analytics` (literal-reference).

### `tests/test_p3c_quality_operations_controllers.py`

- line 41: `velvet_bot.handlers` (dynamic-prefix-reference).

### `tests/test_p3d_residual_handler_classification.py`

- line 11: `velvet_bot.handlers.channel_analytics` (literal-reference).

## Следующий срез

- фаза: **P3D**;
- цель: **retire the next compatibility alias group**;
- стратегия: migrate tests to canonical modules, then delete only aliases with no repository references.

## Правило обновления

```bash
python scripts/inventory_handler_alias_consumers.py --write --label <phase>
python scripts/inventory_handler_alias_consumers.py --check --label <phase>
```
