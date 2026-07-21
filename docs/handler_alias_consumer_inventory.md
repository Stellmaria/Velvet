# Инвентаризация consumers handler aliases

Машинный срез оставшегося compatibility API `velvet_bot.handlers.*` после закрытия production consumers.

## Сводка

- alias-файлов: **0**;
- файлов-consumers: **2**;
- references: **2**;
- aliases с references: **0**;
- aliases без references: **0**;
- динамических prefix references: **2**;
- references на уже отсутствующие aliases: **0**.

## Alias status


## Consumers

### `scripts/inventory_architecture_layout.py`

- line 139: `velvet_bot.handlers` (dynamic-prefix-reference).

### `tests/test_p3c_quality_operations_controllers.py`

- line 41: `velvet_bot.handlers` (dynamic-prefix-reference).

## Следующий срез

- фаза: **P3E**;
- цель: **repository and root-module layout normalization**;
- стратегия: keep handler aliases at zero while migrating repository consumers by domain.

## Правило обновления

```bash
python scripts/inventory_handler_alias_consumers.py --write --label <phase>
python scripts/inventory_handler_alias_consumers.py --check --label <phase>
```
