# Инвентаризация физической архитектуры Velvet

Машинный срез переходной структуры после закрытия P2.

## Сводка

- прямые imports `velvet_bot.handlers.*` в root Router: **0**;
- доменных router bundles: **4**;
- активных router imports в bundles: **59**;
- дублирующих регистраций между bundles: **0**;
- физических legacy handler-файлов: **0**;
- активных legacy handler implementations: **0**;
- временных handler module aliases: **0**;
- корневых Python-модулей `velvet_bot/*.py`: **117**;
- файлов с `compat` в имени: **5**;
- активных compatibility-компонентов: **8**.

## Router bundles

- `velvet_bot/presentation/telegram/routers/analytics.py`: 5 routers.
- `velvet_bot/presentation/telegram/routers/archive_and_public.py`: 34 routers.
- `velvet_bot/presentation/telegram/routers/core_operations.py`: 6 routers.
- `velvet_bot/presentation/telegram/routers/quality_operations.py`: 14 routers.

## Handler module aliases


## Активная compatibility-граница

### Pre-import

- `ai-quality-schema`.
- `set-consistency-dashboard`.
- `quality-calibration-dashboard`.
- `media-set-actions`.
- `media-set-ai-discovery`.
- `media-set-ui`.
- `owner-menu-navigation`.

### Post-import

- `quality-calibration-report-ui`.

## Следующий срез

- фаза: **P3D**;
- цель: **compatibility alias retirement and canonical import cleanup**;
- стратегия: remove temporary handler aliases in reviewed consumer groups.

## Правило обновления

```bash
python scripts/inventory_architecture_layout.py --write --label <phase>
python scripts/inventory_architecture_layout.py --check --label <phase>
```
