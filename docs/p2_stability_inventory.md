# P2 stability inventory

AST-инвентаризация широких исключений и callback acknowledgment.

## Сводка

- raw broad exceptions: **70** в **43** файлах;
- approved boundaries: **31**;
- unresolved broad exceptions: **39** в **25** файлах;
- callback handlers: **97**;
- late/missing callbacks: **0**;
- guarded callbacks: **25**;
- delegated callbacks: **4**.

## Approved broad boundaries

- `velvet_bot/ai_job_runtime.py:55` `create`: compensate-created-ai-job.
- `velvet_bot/ai_quality.py:703` `process_once`: compensate-claimed-ai-quality.
- `velvet_bot/ai_vision.py:725` `process_once`: compensate-claimed-ai-profile.
- `velvet_bot/app/bootstrap.py:85` `_close_application_resources`: isolate-worker-shutdown.
- `velvet_bot/app/bootstrap.py:91` `_close_application_resources`: best-effort-shutdown-audit.
- `velvet_bot/app/bootstrap.py:99` `_close_application_resources`: isolate-error-center-shutdown.
- `velvet_bot/app/bootstrap.py:105` `_close_application_resources`: isolate-bot-session-shutdown.
- `velvet_bot/app/bootstrap.py:110` `_close_application_resources`: isolate-database-shutdown.
- `velvet_bot/app/bootstrap.py:127` `_report_fatal_application_error`: preserve-original-fatal-error.
- `velvet_bot/app/bootstrap.py:266` `run_application`: report-fatal-application-error.
- `velvet_bot/audit.py:56` `send`: isolate-telegram-audit-sink.
- `velvet_bot/backup_runtime.py:163` `_create_dump_file`: cleanup-invalid-backup-artifacts.
- `velvet_bot/backup_service.py:529` `create_backup`: compensate-running-backup.
- `velvet_bot/backup_service.py:898` `run_backup_worker`: isolate-backup-worker-iteration.
- `velvet_bot/calibrated_ai_quality.py:111` `process_once`: compensate-claimed-calibrated-quality.
- `velvet_bot/discussion_analytics_middleware.py:36` `__call__`: isolate-discussion-analytics-ingest.
- `velvet_bot/domains/media_quality/service.py:90` `scan_target`: compensate-claimed-media-scan.
- `velvet_bot/domains/publication/service.py:68` `publish`: compensate-claimed-publication.
- `velvet_bot/domains/publication/service.py:89` `process_due_once`: isolate-scheduled-draft.
- `velvet_bot/error_center.py:99` `capture_log_record`: fallback-log-record-message.
- `velvet_bot/error_center.py:337` `_is_recoverable_aiogram_polling_record`: fallback-polling-record-message.
- `velvet_bot/error_center.py:364` `emit`: isolate-error-logging-handler.
- `velvet_bot/error_center.py:462` `_consume`: isolate-error-incident-item.
- `velvet_bot/handlers/admin_media_display.py:38` `build_admin_display_media`: fallback-admin-edit-preview.
- `velvet_bot/handlers/admin_media_display.py:88` `send_admin_archive_page`: fallback-admin-send-preview.
- `velvet_bot/handlers/archive.py:238` `handle_new_archive_topic_media`: report-topic-auto-archive-failure.
- `velvet_bot/handlers/backup_center.py:391` `handle_backup_callback`: report-backup-callback-failure.
- `velvet_bot/handlers/channel_analytics.py:166` `_capture_channel_post`: report-channel-ingest-failure.
- `velvet_bot/handlers/characters.py:57` `handle_create_character`: report-character-create-failure.
- `velvet_bot/handlers/characters.py:108` `handle_bind_character_topic`: report-character-topic-failure.
- `velvet_bot/handlers/error_center.py:56` `acknowledge_all_errors_callback`: best-effort-error-markup-cleanup.

## Unresolved broad exceptions by file

- `velvet_bot/handlers/public_archive.py`: 5.
- `velvet_bot/handlers/media_browser.py`: 4.
- `velvet_bot/handlers/guest_archive.py`: 2.
- `velvet_bot/handlers/quality_set_ai.py`: 2.
- `velvet_bot/handlers/velvet_ai_formatting.py`: 2.
- `velvet_bot/public_archive_display.py`: 2.
- `velvet_bot/services/media_save.py`: 2.
- `velvet_bot/services/system_health.py`: 2.
- `velvet_bot/workers/manager.py`: 2.
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

- `velvet_bot/handlers/guest_archive.py`.

## Правило обновления

Запустите `python scripts/update_p2_stability_inventory.py --label <phase> --schema-version <n>` после изменения broad catches или callback acknowledgment.
