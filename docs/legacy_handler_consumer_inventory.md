# Инвентаризация consumers старых handler paths

Машинный baseline production-кода, который ещё зависит от `velvet_bot.handlers.*` aliases.

## Сводка

- файлов-consumers: **19**;
- legacy references: **28**;
- затронутых legacy modules: **17**.

## Consumers

### `velvet_bot/analytics_callbacks.py`

- line 6: `velvet_bot.handlers.analytics_dashboard` (import; names: `AnalyticsCallback`).

### `velvet_bot/owner_menu.py`

- line 5: `velvet_bot.handlers.admin_directory` (import; names: `AdminDirectoryCallback`).
- line 6: `velvet_bot.handlers.analytics_dashboard` (import; names: `AnalyticsCallback`).
- line 7: `velvet_bot.handlers.backup_center` (import; names: `BackupCallback`).
- line 8: `velvet_bot.handlers.publication_center` (import; names: `PublicationCallback`).

### `velvet_bot/owner_menu_compat.py`

- line 50: `velvet_bot.handlers.admin_directory` (import; names: `admin_directory`).
- line 51: `velvet_bot.handlers.analytics_dashboard` (import; names: `analytics_dashboard`).
- line 52: `velvet_bot.handlers.backup_center` (import; names: `backup_center`).
- line 53: `velvet_bot.handlers.publication_center` (import; names: `publication_center`).
- line 54: `velvet_bot.handlers.system_center` (import; names: `system_center`).
- line 75: `velvet_bot.handlers.quality_center` (import; names: `quality_center`).

### `velvet_bot/presentation/telegram/routers/analytics_controllers/management_aliases.py`

- line 21: `velvet_bot.handlers.analytics_management_common` (import; names: `_edit, _short, _show_character_picker`).

### `velvet_bot/presentation/telegram/routers/analytics_controllers/management_publications.py`

- line 18: `velvet_bot.handlers.analytics_management_common` (import; names: `_date, _edit, _pager, _short`).

### `velvet_bot/presentation/telegram/routers/analytics_controllers/management_tags.py`

- line 16: `velvet_bot.handlers.analytics_management_common` (import; names: `_edit, _pager, _short, _show_character_picker`).

### `velvet_bot/presentation/telegram/routers/archive/guest.py`

- line 19: `velvet_bot.handlers.archive` (import; names: `parse_guest_save_character`).

### `velvet_bot/presentation/telegram/routers/archive_and_public_controllers/admin_media_spoiler.py`

- line 12: `velvet_bot.handlers.admin_media_display` (import; names: `replace_admin_archive_page`).

### `velvet_bot/presentation/telegram/routers/core_operations_controllers/watermark.py`

- line 303: `velvet_bot.handlers.owner_menu` (import; names: `show_owner_menu`).

### `velvet_bot/presentation/telegram/routers/public_archive/notification_open.py`

- line 11: `velvet_bot.handlers.public_archive` (import; names: `_send_public_archive_page`).

### `velvet_bot/presentation/telegram/routers/quality_operations_controllers/quality_ai_preview.py`

- line 11: `velvet_bot.handlers.quality_ai` (import; names: `quality_ai_module`).

### `velvet_bot/presentation/telegram/routers/quality_operations_controllers/quality_center.py`

- line 11: `velvet_bot.handlers.admin_directory` (import; names: `AdminDirectoryCallback`).
- line 12: `velvet_bot.handlers.analytics_dashboard` (import; names: `AnalyticsCallback`).

### `velvet_bot/presentation/telegram/routers/references/albums.py`

- line 21: `velvet_bot.handlers.references` (import; names: `parse_reference_character`).

### `velvet_bot/presentation/telegram/routers/references/comparison.py`

- line 22: `velvet_bot.handlers.reference_albums` (import; names: `parse_reference_selector`).

### `velvet_bot/presentation/telegram/routers/references/comparison_help.py`

- line 27: `velvet_bot.handlers.admin_directory` (import; names: `AdminDirectoryCallback`).

### `velvet_bot/presentation/telegram/routers/references/documents.py`

- line 20: `velvet_bot.handlers.reference_management` (import; names: `parse_reference_add_character`).

### `velvet_bot/presentation/telegram/routers/supervisor/codex.py`

- line 12: `velvet_bot.handlers.supervisor_status` (import; names: `show_supervisor_menu`).

### `velvet_bot/public_manager_preview_bridge.py`

- line 9: `velvet_bot.handlers.public_manager` (dynamic-reference).

### `velvet_bot/quality_calibration_ui.py`

- line 25: `velvet_bot.handlers.quality_ai` (import; names: `quality_ai`).

## Уже очищенные paths

- `velvet_bot/presentation/telegram/routers/characters/uncategorized.py`.
- `velvet_bot/presentation/telegram/routers/stories/management.py`.
- `velvet_bot/presentation/telegram/routers/stories/multi_story_kr.py`.

## Следующий срез

- фаза: **P3D**;
- цель: **retire the next reviewed legacy consumer group**;
- стратегия: move shared helpers to public contracts before deleting aliases.

## Правило обновления

```bash
python scripts/inventory_legacy_handler_consumers.py --write --label <phase>
python scripts/inventory_legacy_handler_consumers.py --check --label <phase>
```
