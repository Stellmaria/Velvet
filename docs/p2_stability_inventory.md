# P2 stability inventory

AST-инвентаризация широких исключений и callback acknowledgment.

## Сводка

- широких `except Exception`: **70** в **43** файлах;
- callback handlers: **97**;
- missing/late acknowledgment: **0**;
- guarded acknowledgment после одной mutation/query: **25**;
- delegated wrappers: **4**.

## Risky callbacks

- Нет. Callback late/missing baseline закрыт.

## Guarded acknowledgment

- `velvet_bot/handlers/admin_large_media_preview.py:179` `handle_admin_large_media_preview`.
- `velvet_bot/handlers/admin_media_display.py:125` `handle_admin_archive_display`.
- `velvet_bot/handlers/admin_media_spoiler.py:18` `handle_admin_media_spoiler`.
- `velvet_bot/handlers/admin_stories.py:335` `handle_story_picker`.
- `velvet_bot/handlers/error_center.py:47` `acknowledge_all_errors_callback`.
- `velvet_bot/handlers/kr_profile_overrides.py:85` `handle_kr_profile`.
- `velvet_bot/handlers/kr_profile_overrides.py:103` `handle_kr_multi_story_done`.
- `velvet_bot/handlers/kr_universe_entry.py:27` `handle_admin_set_kr`.
- `velvet_bot/handlers/kr_universe_entry.py:66` `handle_public_set_kr`.
- `velvet_bot/handlers/media_prompt_binding.py:110` `handle_prompt_button`.
- `velvet_bot/handlers/media_prompt_binding.py:215` `handle_prompt_remove`.
- `velvet_bot/handlers/multi_story_kr.py:232` `handle_admin_open_multi_story`.
- `velvet_bot/handlers/multi_story_kr.py:458` `handle_public_open_multi_story`.
- `velvet_bot/handlers/public_media_display.py:31` `handle_spoiler_aware_open`.
- `velvet_bot/handlers/public_media_display.py:96` `handle_like_and_subscription`.
- `velvet_bot/handlers/quality_ai.py:425` `handle_quality_ai_retry`.
- `velvet_bot/handlers/quality_center.py:168` `handle_quality_close`.
- `velvet_bot/handlers/quality_center.py:208` `handle_retry_scans`.
- `velvet_bot/handlers/quality_center.py:224` `handle_retry_broken`.
- `velvet_bot/handlers/quality_center.py:240` `handle_orphan_info`.
- `velvet_bot/handlers/quality_duplicates.py:153` `handle_duplicate_open`.
- `velvet_bot/handlers/quality_operations.py:341` `handle_quality_recent`.
- `velvet_bot/handlers/quality_operations.py:353` `handle_quality_retry_errors`.
- `velvet_bot/handlers/reference_comparison_help.py:140` `handle_reference_compare_help`.
- `velvet_bot/handlers/reference_management.py:383` `handle_reference_delete_callback`.

## Delegated wrappers

- `velvet_bot/handlers/admin_uncategorized.py:280` `handle_uncategorized_menu`.
- `velvet_bot/handlers/publication_center_safe.py:55` `safe_publication_callback`.
- `velvet_bot/handlers/quality_ai.py:407` `handle_quality_ai_accept`.
- `velvet_bot/handlers/quality_ai.py:416` `handle_quality_ai_fix`.

## Широкие исключения по файлам

- `velvet_bot/app/bootstrap.py`: 7.
- `velvet_bot/handlers/public_archive.py`: 5.
- `velvet_bot/error_center.py`: 4.
- `velvet_bot/handlers/media_browser.py`: 4.
- `velvet_bot/backup_service.py`: 2.
- `velvet_bot/domains/publication/service.py`: 2.
- `velvet_bot/handlers/admin_media_display.py`: 2.
- `velvet_bot/handlers/characters.py`: 2.
- `velvet_bot/handlers/guest_archive.py`: 2.
- `velvet_bot/handlers/quality_set_ai.py`: 2.
- `velvet_bot/handlers/velvet_ai_formatting.py`: 2.
- `velvet_bot/public_archive_display.py`: 2.
- `velvet_bot/services/media_save.py`: 2.
- `velvet_bot/services/system_health.py`: 2.
- `velvet_bot/workers/manager.py`: 2.
- `velvet_bot/ai_job_runtime.py`: 1.
- `velvet_bot/ai_quality.py`: 1.
- `velvet_bot/ai_vision.py`: 1.
- `velvet_bot/audit.py`: 1.
- `velvet_bot/backup_runtime.py`: 1.
- `velvet_bot/calibrated_ai_quality.py`: 1.
- `velvet_bot/discussion_analytics_middleware.py`: 1.
- `velvet_bot/domains/media_quality/service.py`: 1.
- `velvet_bot/handlers/archive.py`: 1.
- `velvet_bot/handlers/backup_center.py`: 1.
- `velvet_bot/handlers/channel_analytics.py`: 1.
- `velvet_bot/handlers/error_center.py`: 1.
- `velvet_bot/handlers/public_manager.py`: 1.
- `velvet_bot/handlers/publication_center.py`: 1.
- `velvet_bot/handlers/quality_duplicates.py`: 1.
- `velvet_bot/handlers/quality_operations.py`: 1.
- `velvet_bot/handlers/quality_sets.py`: 1.
- `velvet_bot/handlers/reference_comparison.py`: 1.
- `velvet_bot/handlers/reference_comparison_help.py`: 1.
- `velvet_bot/handlers/supervisor_console.py`: 1.
- `velvet_bot/handlers/velvet_ai.py`: 1.
- `velvet_bot/handlers/velvet_ai_visual.py`: 1.
- `velvet_bot/infrastructure/telegram/archive_previews.py`: 1.
- `velvet_bot/media_quality.py`: 1.
- `velvet_bot/presentation/telegram/public_notifications.py`: 1.
- `velvet_bot/public_notifications.py`: 1.
- `velvet_bot/publication_inbox_middleware.py`: 1.
- `velvet_bot/publication_worker.py`: 1.

## Следующий срез

- `velvet_bot/domains/publication/service.py`: классифицировать broad exceptions и сузить бизнес-ошибки без потери incident reporting.

## Правило обновления

Inventory проверяется AST-тестом. Тяжёлый reload должен выполняться после callback acknowledgment.
