# P2 stability inventory

AST-инвентаризация широких исключений и callback acknowledgment.

## Сводка

- raw broad exceptions: **76** в **45** файлах;
- approved boundaries: **76**;
- unresolved broad exceptions: **0** в **0** файлах;
- callback handlers: **98**;
- late/missing callbacks: **0**;
- guarded callbacks: **25**;
- delegated callbacks: **4**.

## Approved broad boundaries

- `velvet_bot/ai_job_runtime.py:55` `create`: compensate-created-ai-job.
- `velvet_bot/ai_quality.py:703` `process_once`: compensate-claimed-ai-quality.
- `velvet_bot/ai_vision.py:725` `process_once`: compensate-claimed-ai-profile.
- `velvet_bot/app/bootstrap.py:87` `_close_application_resources`: isolate-worker-shutdown.
- `velvet_bot/app/bootstrap.py:93` `_close_application_resources`: best-effort-shutdown-audit.
- `velvet_bot/app/bootstrap.py:101` `_close_application_resources`: isolate-error-center-shutdown.
- `velvet_bot/app/bootstrap.py:110` `_close_application_resources`: isolate-bot-session-shutdown.
- `velvet_bot/app/bootstrap.py:115` `_close_application_resources`: isolate-database-shutdown.
- `velvet_bot/app/bootstrap.py:132` `_report_fatal_application_error`: preserve-original-fatal-error.
- `velvet_bot/app/bootstrap.py:282` `run_application`: report-fatal-application-error.
- `velvet_bot/audit.py:56` `send`: isolate-telegram-audit-sink.
- `velvet_bot/backup_runtime.py:163` `_create_dump_file`: cleanup-invalid-backup-artifacts.
- `velvet_bot/backup_service.py:529` `create_backup`: compensate-running-backup.
- `velvet_bot/backup_service.py:898` `run_backup_worker`: isolate-backup-worker-iteration.
- `velvet_bot/calibrated_ai_quality.py:111` `process_once`: compensate-claimed-calibrated-quality.
- `velvet_bot/discussion_analytics_middleware.py:36` `__call__`: isolate-discussion-analytics-ingest.
- `velvet_bot/domains/media_quality/service.py:90` `scan_target`: compensate-claimed-media-scan.
- `velvet_bot/domains/publication/service.py:68` `publish`: compensate-claimed-publication.
- `velvet_bot/domains/publication/service.py:89` `process_due_once`: isolate-scheduled-draft.
- `velvet_bot/domains/telegram_storage/service.py:114` `run`: isolate-telegram-storage-operation.
- `velvet_bot/domains/telegram_storage/service.py:166` `_upload_candidate`: isolate-telegram-storage-operation.
- `velvet_bot/domains/telegram_storage/service.py:282` `_migrate_watermarks`: isolate-telegram-storage-operation.
- `velvet_bot/domains/telegram_storage/service.py:463` `_migrate_backups`: isolate-telegram-storage-operation.
- `velvet_bot/domains/telegram_storage/service.py:610` `_migrate_codex`: isolate-telegram-storage-operation.
- `velvet_bot/domains/telegram_storage/uploader.py:187` `upload`: isolate-telegram-storage-operation.
- `velvet_bot/error_center.py:99` `capture_log_record`: fallback-log-record-message.
- `velvet_bot/error_center.py:337` `_is_recoverable_aiogram_polling_record`: fallback-polling-record-message.
- `velvet_bot/error_center.py:364` `emit`: isolate-error-logging-handler.
- `velvet_bot/error_center.py:462` `_consume`: isolate-error-incident-item.
- `velvet_bot/infrastructure/telegram/archive_previews.py:84` `resolve`: fallback-full-quality-archive-preview.
- `velvet_bot/media_quality.py:103` `run_media_quality_worker`: isolate-media-quality-worker-iteration.
- `velvet_bot/presentation/telegram/public_notifications.py:80` `process_once`: isolate-public-notification-delivery.
- `velvet_bot/presentation/telegram/routers/analytics_controllers/channel.py:166` `_capture_channel_post`: report-channel-ingest-failure.
- `velvet_bot/presentation/telegram/routers/archive/guest.py:155` `_archive_guest_media`: report-guest-topic-delivery-failure.
- `velvet_bot/presentation/telegram/routers/archive/guest.py:250` `handle_guest_archive`: report-guest-request-failure.
- `velvet_bot/presentation/telegram/routers/archive/save.py:345` `handle_new_archive_topic_media`: report-topic-auto-archive-failure.
- `velvet_bot/presentation/telegram/routers/archive_and_public_controllers/admin_media_display.py:38` `build_admin_display_media`: fallback-admin-edit-preview.
- `velvet_bot/presentation/telegram/routers/archive_and_public_controllers/admin_media_display.py:88` `send_admin_archive_page`: fallback-admin-send-preview.
- `velvet_bot/presentation/telegram/routers/archive_and_public_controllers/media_browser.py:69` `_build_display_input_media`: fallback-full-size-preview.
- `velvet_bot/presentation/telegram/routers/archive_and_public_controllers/media_browser.py:103` `_send_archive_page`: fallback-document-preview.
- `velvet_bot/presentation/telegram/routers/archive_and_public_controllers/media_browser.py:290` `handle_archive_media_callback`: report-archive-load-failure.
- `velvet_bot/presentation/telegram/routers/archive_and_public_controllers/media_browser.py:356` `handle_archive_media_callback`: report-archive-delete-failure.
- `velvet_bot/presentation/telegram/routers/characters/profiles.py:62` `handle_create_character`: report-character-create-failure.
- `velvet_bot/presentation/telegram/routers/characters/profiles.py:115` `handle_bind_character_topic`: report-character-topic-failure.
- `velvet_bot/presentation/telegram/routers/core_operations_controllers/error_center.py:56` `acknowledge_all_errors_callback`: best-effort-error-markup-cleanup.
- `velvet_bot/presentation/telegram/routers/public_archive/manager.py:163` `handle_public_manager`: report-manager-download-failure.
- `velvet_bot/presentation/telegram/routers/public_archive/media_display.py:115` `_prepare_media`: report-public-media-prepare-failure.
- `velvet_bot/presentation/telegram/routers/public_archive/media_display.py:242` `handle_spoiler_aware_open`: preserve-public-open-on-metric-failure.
- `velvet_bot/presentation/telegram/routers/public_archive/media_display.py:328` `_apply_engagement`: report-public-engagement-write-failure.
- `velvet_bot/presentation/telegram/routers/public_archive/media_display.py:351` `_apply_engagement`: preserve-engagement-on-ui-refresh-failure.
- `velvet_bot/presentation/telegram/routers/public_archive/media_display.py:433` `handle_public_download`: report-public-download-failure.
- `velvet_bot/presentation/telegram/routers/publication/center.py:569` `handle_publication_callback`: report-publication-failure.
- `velvet_bot/presentation/telegram/routers/quality_operations_controllers/backup_center.py:391` `handle_backup_callback`: report-backup-callback-failure.
- `velvet_bot/presentation/telegram/routers/quality_operations_controllers/quality_operations.py:335` `handle_quality_upload_reply`: compensate-manual-quality-job.
- `velvet_bot/presentation/telegram/routers/quality_operations_controllers/quality_set_ai.py:476` `handle_set_analyze`: compensate-set-analysis-callback-job.
- `velvet_bot/presentation/telegram/routers/quality_operations_controllers/quality_set_ai.py:569` `handle_set_analysis_command`: compensate-set-analysis-command-job.
- `velvet_bot/presentation/telegram/routers/quality_operations_controllers/velvet_ai.py:340` `handle_prompt_check_reply`: compensate-prompt-result-job.
- `velvet_bot/presentation/telegram/routers/quality_operations_controllers/velvet_ai_formatting.py:287` `handle_formatting_reply`: compensate-velvet-formatting-job.
- `velvet_bot/presentation/telegram/routers/quality_operations_controllers/velvet_ai_visual.py:315` `handle_visual_analysis_reply`: compensate-palette-composition-job.
- `velvet_bot/presentation/telegram/routers/references/comparison.py:282` `handle_reference_comparison`: report-reference-comparison-failure.
- `velvet_bot/presentation/telegram/routers/references/comparison_help.py:255` `handle_reference_comparison_reply`: compensate-reference-comparison-form-job.
- `velvet_bot/presentation/telegram/routers/supervisor/console.py:174` `_watch_console_operation`: isolate-supervisor-console-watcher.
- `velvet_bot/presentation/telegram/storage_center.py:127` `_run_manual_migration`: isolate-telegram-storage-operation.
- `velvet_bot/presentation/telegram/storage_center.py:294` `handle_storage_startup.runner`: isolate-telegram-storage-operation.
- `velvet_bot/public_archive_display.py:128` `build_viewer_input_media`: fallback-viewer-edit-preview.
- `velvet_bot/public_archive_display.py:195` `send_viewer_archive_page`: fallback-viewer-send-preview.
- `velvet_bot/public_notifications.py:60` `run_public_notification_worker`: isolate-public-notification-worker-iteration.
- `velvet_bot/publication_inbox_middleware.py:60` `_capture`: best-effort-publication-inbox-capture.
- `velvet_bot/publication_worker.py:65` `run_publication_worker`: isolate-publication-worker-iteration.
- `velvet_bot/services/diagnostic_bundle.py:75` `emit`: isolate-diagnostic-log-buffer.
- `velvet_bot/services/media_save.py:41` `save_media_from_message`: report-media-save-failure.
- `velvet_bot/services/media_save.py:229` `_place_in_topic`: isolate-media-topic-delivery.
- `velvet_bot/services/system_health.py:126` `check`: isolate-database-health-probe.
- `velvet_bot/services/system_health.py:138` `check`: isolate-telegram-health-probe.
- `velvet_bot/workers/manager.py:182` `_execute_once`: isolate-worker-iteration-failure.
- `velvet_bot/workers/manager.py:219` `_run_periodic`: isolate-worker-loop-failure.

## Unresolved broad exceptions by file


## Следующий срез

- Нет.

## Правило обновления

Запустите `python scripts/update_p2_stability_inventory.py --label <phase> --schema-version <n>` после изменения broad catches или callback acknowledgment.
