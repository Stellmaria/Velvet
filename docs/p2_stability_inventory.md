# P2 stability inventory

AST-инвентаризация широких исключений и callback acknowledgment.

## Сводка

- raw broad exceptions: **67** в **41** файлах;
- approved boundaries: **52**;
- unresolved broad exceptions: **15** в **11** файлах;
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
- `velvet_bot/handlers/guest_archive.py:153` `_archive_guest_media`: report-guest-topic-delivery-failure.
- `velvet_bot/handlers/guest_archive.py:248` `handle_guest_archive`: report-guest-request-failure.
- `velvet_bot/handlers/media_browser.py:66` `_build_display_input_media`: fallback-full-size-preview.
- `velvet_bot/handlers/media_browser.py:100` `_send_archive_page`: fallback-document-preview.
- `velvet_bot/handlers/media_browser.py:284` `handle_archive_media_callback`: report-archive-load-failure.
- `velvet_bot/handlers/media_browser.py:350` `handle_archive_media_callback`: report-archive-delete-failure.
- `velvet_bot/handlers/public_archive.py:70` `_build_public_input_media`: fallback-public-edit-preview.
- `velvet_bot/handlers/public_archive.py:115` `_send_public_archive_page`: fallback-public-send-preview.
- `velvet_bot/handlers/public_archive.py:535` `handle_public_archive_callback`: report-public-like-failure.
- `velvet_bot/handlers/public_archive.py:577` `handle_public_archive_callback`: report-public-subscription-failure.
- `velvet_bot/handlers/public_archive.py:620` `handle_public_archive_callback`: report-public-download-failure.
- `velvet_bot/handlers/public_manager.py:174` `handle_public_manager`: report-manager-download-failure.
- `velvet_bot/handlers/publication_center.py:569` `handle_publication_callback`: report-publication-failure.
- `velvet_bot/handlers/quality_operations.py:335` `handle_quality_upload_reply`: compensate-manual-quality-job.
- `velvet_bot/handlers/quality_set_ai.py:476` `handle_set_analyze`: compensate-set-analysis-callback-job.
- `velvet_bot/handlers/quality_set_ai.py:569` `handle_set_analysis_command`: compensate-set-analysis-command-job.
- `velvet_bot/handlers/reference_comparison.py:280` `handle_reference_comparison`: report-reference-comparison-failure.
- `velvet_bot/handlers/reference_comparison_help.py:253` `handle_reference_comparison_reply`: compensate-reference-comparison-form-job.
- `velvet_bot/handlers/supervisor_console.py:174` `_watch_console_operation`: isolate-supervisor-console-watcher.
- `velvet_bot/handlers/velvet_ai.py:340` `handle_prompt_check_reply`: compensate-prompt-result-job.
- `velvet_bot/handlers/velvet_ai_formatting.py:287` `handle_formatting_reply`: compensate-velvet-formatting-job.

## Unresolved broad exceptions by file

- `velvet_bot/public_archive_display.py`: 2.
- `velvet_bot/services/media_save.py`: 2.
- `velvet_bot/services/system_health.py`: 2.
- `velvet_bot/workers/manager.py`: 2.
- `velvet_bot/handlers/velvet_ai_visual.py`: 1.
- `velvet_bot/infrastructure/telegram/archive_previews.py`: 1.
- `velvet_bot/media_quality.py`: 1.
- `velvet_bot/presentation/telegram/public_notifications.py`: 1.
- `velvet_bot/public_notifications.py`: 1.
- `velvet_bot/publication_inbox_middleware.py`: 1.
- `velvet_bot/publication_worker.py`: 1.

## Следующий срез

- `velvet_bot/handlers/velvet_ai_visual.py`.

## Правило обновления

Запустите `python scripts/update_p2_stability_inventory.py --label <phase> --schema-version <n>` после изменения broad catches или callback acknowledgment.
