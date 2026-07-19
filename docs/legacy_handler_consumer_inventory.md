# Инвентаризация consumers старых handler paths

Машинный baseline production-кода, который ещё зависит от `velvet_bot.handlers.*` aliases.

## Сводка

- файлов-consumers: **0**;
- legacy references: **0**;
- затронутых legacy modules: **0**.

## Consumers

## Уже очищенные paths

- `velvet_bot/analytics_callbacks.py`.
- `velvet_bot/owner_menu.py`.
- `velvet_bot/owner_menu_compat.py`.
- `velvet_bot/presentation/telegram/routers/analytics_controllers/management_aliases.py`.
- `velvet_bot/presentation/telegram/routers/analytics_controllers/management_publications.py`.
- `velvet_bot/presentation/telegram/routers/analytics_controllers/management_tags.py`.
- `velvet_bot/presentation/telegram/routers/archive/guest.py`.
- `velvet_bot/presentation/telegram/routers/archive_and_public_controllers/admin_media_spoiler.py`.
- `velvet_bot/presentation/telegram/routers/characters/uncategorized.py`.
- `velvet_bot/presentation/telegram/routers/core_operations_controllers/watermark.py`.
- `velvet_bot/presentation/telegram/routers/public_archive/manager.py`.
- `velvet_bot/presentation/telegram/routers/public_archive/media_display.py`.
- `velvet_bot/presentation/telegram/routers/public_archive/notification_open.py`.
- `velvet_bot/presentation/telegram/routers/quality_operations_controllers/quality_ai_preview.py`.
- `velvet_bot/presentation/telegram/routers/quality_operations_controllers/quality_center.py`.
- `velvet_bot/presentation/telegram/routers/references/albums.py`.
- `velvet_bot/presentation/telegram/routers/references/comparison.py`.
- `velvet_bot/presentation/telegram/routers/references/comparison_help.py`.
- `velvet_bot/presentation/telegram/routers/references/documents.py`.
- `velvet_bot/presentation/telegram/routers/stories/management.py`.
- `velvet_bot/presentation/telegram/routers/stories/multi_story_kr.py`.
- `velvet_bot/presentation/telegram/routers/supervisor/codex.py`.
- `velvet_bot/quality_calibration_ui.py`.

## Следующий срез

- фаза: **P3D**;
- цель: **migrate compatibility tests and retire zero-consumer aliases**;
- стратегия: delete an alias only after canonical imports replace its tests and external contracts.

## Правило обновления

```bash
python scripts/inventory_legacy_handler_consumers.py --write --label <phase>
python scripts/inventory_legacy_handler_consumers.py --check --label <phase>
```
