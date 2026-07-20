# Инвентаризация физической архитектуры Velvet

Машинный срез переходной структуры после закрытия P2.

## Сводка

- прямые imports `velvet_bot.handlers.*` в root Router: **0**;
- доменных router bundles: **4**;
- активных router imports в bundles: **58**;
- дублирующих регистраций между bundles: **0**;
- физических legacy handler-файлов: **25**;
- активных legacy handler implementations: **0**;
- временных handler module aliases: **25**;
- корневых Python-модулей `velvet_bot/*.py`: **117**;
- файлов с `compat` в имени: **5**;
- активных compatibility-компонентов: **8**.

## Router bundles

- `velvet_bot/presentation/telegram/routers/analytics.py`: 5 routers.
- `velvet_bot/presentation/telegram/routers/archive_and_public.py`: 34 routers.
- `velvet_bot/presentation/telegram/routers/core_operations.py`: 5 routers.
- `velvet_bot/presentation/telegram/routers/quality_operations.py`: 14 routers.

## Handler module aliases

- `velvet_bot/handlers/analytics_dashboard.py`.
- `velvet_bot/handlers/analytics_dashboard_overrides.py`.
- `velvet_bot/handlers/analytics_discussion_overrides.py`.
- `velvet_bot/handlers/analytics_management.py`.
- `velvet_bot/handlers/analytics_management_aliases.py`.
- `velvet_bot/handlers/analytics_management_common.py`.
- `velvet_bot/handlers/analytics_management_publications.py`.
- `velvet_bot/handlers/analytics_management_tags.py`.
- `velvet_bot/handlers/backup_center.py`.
- `velvet_bot/handlers/channel_analytics.py`.
- `velvet_bot/handlers/error_center.py`.
- `velvet_bot/handlers/owner_actions.py`.
- `velvet_bot/handlers/owner_menu.py`.
- `velvet_bot/handlers/publication_center.py`.
- `velvet_bot/handlers/publication_center_safe.py`.
- `velvet_bot/handlers/supervisor_codex.py`.
- `velvet_bot/handlers/supervisor_console.py`.
- `velvet_bot/handlers/supervisor_control.py`.
- `velvet_bot/handlers/supervisor_git.py`.
- `velvet_bot/handlers/supervisor_logs.py`.
- `velvet_bot/handlers/supervisor_process.py`.
- `velvet_bot/handlers/supervisor_self.py`.
- `velvet_bot/handlers/supervisor_status.py`.
- `velvet_bot/handlers/system_center.py`.
- `velvet_bot/handlers/watermark.py`.

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
