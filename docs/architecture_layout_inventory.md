# Инвентаризация физической архитектуры Velvet

Машинный срез переходной структуры после закрытия P2.

## Сводка

- прямые imports `velvet_bot.handlers.*` в root Router: **0**;
- доменных router bundles: **4**;
- активных handler imports в bundles: **55**;
- дублирующих регистраций между bundles: **0**;
- физических legacy handler-файлов: **68**;
- корневых Python-модулей `velvet_bot/*.py`: **110**;
- файлов с `compat` в имени: **5**;
- активных compatibility-компонентов: **8**.

## Router bundles

- `velvet_bot/presentation/telegram/routers/analytics.py`: 5 handlers.
- `velvet_bot/presentation/telegram/routers/archive_and_public.py`: 32 handlers.
- `velvet_bot/presentation/telegram/routers/core_operations.py`: 5 handlers.
- `velvet_bot/presentation/telegram/routers/quality_operations.py`: 13 handlers.

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

- фаза: **P3C**;
- цель: **Supervisor and system presentation controllers**;
- стратегия: canonical presentation modules plus temporary handler re-exports.

## Правило обновления

После изменения root Router, bundles, `handlers/` или compatibility запустите:

```bash
python scripts/inventory_architecture_layout.py --write --label <phase>
python scripts/inventory_architecture_layout.py --check
```
