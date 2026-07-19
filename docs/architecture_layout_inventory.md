# Инвентаризация физической архитектуры Velvet

Машинный срез переходной структуры после закрытия P2.

## Сводка

- прямые imports `velvet_bot.handlers.*` в root Router: **0**;
- доменных router bundles: **4**;
- активных router imports в bundles: **55**;
- дублирующих регистраций между bundles: **0**;
- физических legacy handler-файлов: **68**;
- активных legacy handler implementations: **37**;
- временных handler module aliases: **31**;
- корневых Python-модулей `velvet_bot/*.py`: **110**;
- файлов с `compat` в имени: **5**;
- активных compatibility-компонентов: **8**.

## Router bundles

- `velvet_bot/presentation/telegram/routers/analytics.py`: 5 routers.
- `velvet_bot/presentation/telegram/routers/archive_and_public.py`: 32 routers.
- `velvet_bot/presentation/telegram/routers/core_operations.py`: 5 routers.
- `velvet_bot/presentation/telegram/routers/quality_operations.py`: 13 routers.

## Handler module aliases

- `velvet_bot/handlers/admin_directory.py`.
- `velvet_bot/handlers/admin_stories.py`.
- `velvet_bot/handlers/admin_uncategorized.py`.
- `velvet_bot/handlers/admin_universe_story_flow.py`.
- `velvet_bot/handlers/archive.py`.
- `velvet_bot/handlers/character_aliases.py`.
- `velvet_bot/handlers/characters.py`.
- `velvet_bot/handlers/guest_archive.py`.
- `velvet_bot/handlers/kr_profile_overrides.py`.
- `velvet_bot/handlers/kr_universe_entry.py`.
- `velvet_bot/handlers/multi_story_kr.py`.
- `velvet_bot/handlers/public_archive.py`.
- `velvet_bot/handlers/public_manager.py`.
- `velvet_bot/handlers/public_media_display.py`.
- `velvet_bot/handlers/public_notification_open.py`.
- `velvet_bot/handlers/reference_albums.py`.
- `velvet_bot/handlers/reference_comparison.py`.
- `velvet_bot/handlers/reference_comparison_help.py`.
- `velvet_bot/handlers/reference_documents.py`.
- `velvet_bot/handlers/reference_management.py`.
- `velvet_bot/handlers/references.py`.
- `velvet_bot/handlers/spoiler_save.py`.
- `velvet_bot/handlers/supervisor_codex.py`.
- `velvet_bot/handlers/supervisor_console.py`.
- `velvet_bot/handlers/supervisor_control.py`.
- `velvet_bot/handlers/supervisor_git.py`.
- `velvet_bot/handlers/supervisor_logs.py`.
- `velvet_bot/handlers/supervisor_process.py`.
- `velvet_bot/handlers/supervisor_self.py`.
- `velvet_bot/handlers/supervisor_status.py`.
- `velvet_bot/handlers/system_center.py`.

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
- цель: **publication presentation controllers**;
- стратегия: canonical presentation modules plus temporary handler module aliases.

## Правило обновления

```bash
python scripts/inventory_architecture_layout.py --write --label <phase>
python scripts/inventory_architecture_layout.py --check --label <phase>
```
