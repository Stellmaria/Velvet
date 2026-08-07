# P2 stability inventory

AST-инвентаризация широких исключений и callback acknowledgment.

## Сводка

- raw broad exceptions: **111** в **61** файлах;
- approved boundaries: **111**;
- unresolved broad exceptions: **0** в **0** файлах;
- callback handlers: **132**;
- late/missing callbacks: **0**;
- guarded callbacks: **44**;
- delegated callbacks: **11**.

## Approved broad boundaries

- `velvet_bot/ai_job_runtime.py:55` `create`: compensate-created-ai-job.
- `velvet_bot/ai_quality.py:716` `process_once`: compensate-claimed-ai-quality.
- `velvet_bot/ai_vision.py:744` `process_once`: compensate-claimed-ai-profile.
- `velvet_bot/app/bootstrap.py:90` `_close_application_resources`: isolate-worker-shutdown.
- `velvet_bot/app/bootstrap.py:96` `_close_application_resources`: best-effort-shutdown-audit.
- `velvet_bot/app/bootstrap.py:104` `_close_application_resources`: isolate-error-center-shutdown.
- `velvet_bot/app/bootstrap.py:113` `_close_application_resources`: isolate-bot-session-shutdown.
- `velvet_bot/app/bootstrap.py:118` `_close_application_resources`: isolate-database-shutdown.
- `velvet_bot/app/bootstrap.py:135` `_report_fatal_application_error`: preserve-original-fatal-error.
- `velvet_bot/app/bootstrap.py:308` `run_application`: report-fatal-application-error.
- `velvet_bot/app/workspace_owner_generation_hotfix.py:73` `_owner_aware_bot_call`: default-to-protected-media.
- `velvet_bot/application/media_delivery_deliver.py:70` `execute`: compensate-claimed-media-delivery.
- `velvet_bot/application/media_delivery_deliver.py:262` `_download`: classify-media-download-failure.
- `velvet_bot/application/media_delivery_deliver.py:336` `_send_channel`: classify-telegram-channel-failure.
- `velvet_bot/application/media_delivery_deliver.py:377` `_send_direct_preview`: classify-direct-preview-failure.
- `velvet_bot/application/media_delivery_deliver.py:415` `_notify`: classify-delivery-notification-failure.
- `velvet_bot/application/media_delivery_deliver.py:453` `_compensate_claim`: preserve-lease-recovery-on-compensation-failure.
- `velvet_bot/application/media_delivery_resolve.py:122` `execute`: compensate-claimed-result-resolution.
- `velvet_bot/application/media_delivery_resolve.py:172` `_finish_claim`: preserve-resolution-lease-recovery.
- `velvet_bot/application/storage_librarian.py:298` `process_once`: report-is-nonfatal.
- `velvet_bot/application/storage_librarian.py:321` `process_once`: failure-report-is-nonfatal.
- `velvet_bot/application/storage_librarian.py:331` `process_once`: isolate-storage-librarian-job.
- `velvet_bot/application/storage_librarian.py:340` `process_once`: failure-report-is-nonfatal.
- `velvet_bot/audit.py:56` `send`: isolate-telegram-audit-sink.
- `velvet_bot/backup_runtime.py:163` `_create_dump_file`: cleanup-invalid-backup-artifacts.
- `velvet_bot/backup_service.py:529` `create_backup`: compensate-running-backup.
- `velvet_bot/backup_service.py:898` `run_backup_worker`: isolate-backup-worker-iteration.
- `velvet_bot/calibrated_ai_quality.py:121` `process_once`: compensate-claimed-calibrated-quality.
- `velvet_bot/discussion_analytics_middleware.py:36` `__call__`: isolate-discussion-analytics-ingest.
- `velvet_bot/domains/codex_image.py:538` `process_once`: isolate-codex-image-task-failure.
- `velvet_bot/domains/media_generation/friendly_worker.py:150` `_recover_durable_delivery`: isolate-durable-recovery-tick.
- `velvet_bot/domains/media_generation/task_queue.py:204` `complete`: isolate-post-completion-delivery.
- `velvet_bot/domains/media_generation/task_queue.py:299` `_record_submission_best_effort`: isolate-provider-submission-registration.
- `velvet_bot/domains/media_generation/task_queue.py:340` `_record_success_best_effort`: isolate-provider-success-registration.
- `velvet_bot/domains/media_quality/service.py:90` `scan_target`: compensate-claimed-media-scan.
- `velvet_bot/domains/publication/service.py:126` `publish`: compensate-claimed-publication.
- `velvet_bot/domains/publication/service.py:167` `process_due_once`: isolate-scheduled-draft.
- `velvet_bot/domains/telegram_storage/service.py:114` `run`: isolate-telegram-storage-operation.
- `velvet_bot/domains/telegram_storage/service.py:166` `_upload_candidate`: isolate-telegram-storage-operation.
- `velvet_bot/domains/telegram_storage/service.py:282` `_migrate_watermarks`: isolate-telegram-storage-operation.
- `velvet_bot/domains/telegram_storage/service.py:469` `_migrate_backups`: isolate-telegram-storage-operation.
- `velvet_bot/domains/telegram_storage/service.py:616` `_migrate_codex`: isolate-telegram-storage-operation.
- `velvet_bot/domains/telegram_storage/uploader.py:229` `upload`: isolate-telegram-storage-operation.
- `velvet_bot/domains/workspaces/character_topics.py:135` `ensure_character_archive_topic`: cleanup-orphan-character-topic.
- `velvet_bot/domains/workspaces/watermark_assets.py:226` `store`: cleanup-new-logo-after-db-failure.
- `velvet_bot/error_center.py:99` `capture_log_record`: fallback-log-record-message.
- `velvet_bot/error_center.py:396` `_is_recoverable_aiogram_polling_record`: fallback-polling-record-message.
- `velvet_bot/error_center.py:423` `emit`: isolate-error-logging-handler.
- `velvet_bot/error_center.py:552` `_consume`: isolate-error-incident-item.
- `velvet_bot/error_center.py:564` `_process`: preserve-critical-immediate-path.
- `velvet_bot/error_center.py:581` `_process`: fallback-immediate-under-aggregate-pressure.
- `velvet_bot/error_center.py:621` `_flush_one`: restore-pending-after-batch-failure.
- `velvet_bot/error_center.py:646` `flush_pending`: retry-next-aggregate-flush.
- `velvet_bot/infrastructure/media_delivery_runtime.py:188` `redeliver_owned_task`: report-redelivery-failure.
- `velvet_bot/infrastructure/telegram/archive_previews.py:84` `resolve`: fallback-full-quality-archive-preview.
- `velvet_bot/media_quality.py:103` `run_media_quality_worker`: isolate-media-quality-worker-iteration.
- `velvet_bot/presentation/telegram/public_notifications.py:92` `deliver`: isolate-public-notification-delivery.
- `velvet_bot/presentation/telegram/routers/analytics_controllers/channel.py:166` `_capture_channel_post`: report-channel-ingest-failure.
- `velvet_bot/presentation/telegram/routers/archive/guest.py:155` `_archive_guest_media`: report-guest-topic-delivery-failure.
- `velvet_bot/presentation/telegram/routers/archive/guest.py:250` `handle_guest_archive`: report-guest-request-failure.
- `velvet_bot/presentation/telegram/routers/archive/save.py:595` `handle_new_archive_topic_media`: report-topic-auto-archive-failure.
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
- `velvet_bot/presentation/telegram/routers/public_archive/media_display.py:164` `_prepare_media`: report-public-media-prepare-failure.
- `velvet_bot/presentation/telegram/routers/public_archive/media_display.py:315` `handle_spoiler_aware_open`: preserve-public-open-on-metric-failure.
- `velvet_bot/presentation/telegram/routers/public_archive/media_display.py:382` `handle_spoiler_aware_open`: preserve-navigation-on-owner-review-failure.
- `velvet_bot/presentation/telegram/routers/public_archive/media_display.py:428` `_apply_engagement`: report-public-engagement-write-failure.
- `velvet_bot/presentation/telegram/routers/public_archive/media_display.py:461` `_apply_engagement`: preserve-engagement-on-ui-refresh-failure.
- `velvet_bot/presentation/telegram/routers/public_archive/media_display.py:577` `handle_public_download`: report-public-download-failure.
- `velvet_bot/presentation/telegram/routers/publication/center.py:587` `handle_publication_callback`: report-publication-failure.
- `velvet_bot/presentation/telegram/routers/quality_operations_controllers/backup_center.py:393` `handle_backup_callback`: report-backup-callback-failure.
- `velvet_bot/presentation/telegram/routers/quality_operations_controllers/quality_operations.py:322` `handle_quality_upload_reply`: compensate-manual-quality-job.
- `velvet_bot/presentation/telegram/routers/quality_operations_controllers/quality_set_ai.py:478` `handle_set_analyze`: compensate-set-analysis-callback-job.
- `velvet_bot/presentation/telegram/routers/quality_operations_controllers/quality_set_ai.py:571` `handle_set_analysis_command`: compensate-set-analysis-command-job.
- `velvet_bot/presentation/telegram/routers/quality_operations_controllers/velvet_ai.py:351` `handle_prompt_check_reply`: compensate-prompt-result-job.
- `velvet_bot/presentation/telegram/routers/quality_operations_controllers/velvet_ai_formatting.py:287` `handle_formatting_reply`: compensate-velvet-formatting-job.
- `velvet_bot/presentation/telegram/routers/quality_operations_controllers/velvet_ai_image_prompt.py:297` `handle_image_prompt_reply`: compare-model-partial.
- `velvet_bot/presentation/telegram/routers/quality_operations_controllers/velvet_ai_image_prompt.py:355` `handle_image_prompt_reply`: compensate-image-prompt-job.
- `velvet_bot/presentation/telegram/routers/quality_operations_controllers/velvet_ai_visual.py:315` `handle_visual_analysis_reply`: compensate-palette-composition-job.
- `velvet_bot/presentation/telegram/routers/references/comparison.py:272` `handle_reference_comparison`: report-reference-comparison-failure.
- `velvet_bot/presentation/telegram/routers/references/comparison_help.py:255` `handle_reference_comparison_reply`: compensate-reference-comparison-form-job.
- `velvet_bot/presentation/telegram/routers/supervisor/console.py:175` `_watch_console_operation`: isolate-supervisor-console-watcher.
- `velvet_bot/presentation/telegram/routers/workspace_analytics.py:132` `_ingest`: report-workspace-analytics-ingest-failure.
- `velvet_bot/presentation/telegram/routers/workspace_publications.py:460` `_handle_workspace_publication_callback`: report-workspace-publication-failure.
- `velvet_bot/presentation/telegram/routers/workspace_reference_library.py:1170` `_compare_workspace_reference_result`: report-workspace-reference-comparison.
- `velvet_bot/presentation/telegram/storage_center.py:137` `_run_manual_migration`: isolate-telegram-storage-operation.
- `velvet_bot/presentation/telegram/storage_center.py:345` `handle_storage_startup.runner`: isolate-telegram-storage-operation.
- `velvet_bot/presentation/telegram/workspace_qwen.py:1105` `handle_workspace_qwen_prompt_image`: workspace-qwen-prompt-result.
- `velvet_bot/presentation/telegram/workspace_qwen.py:1190` `handle_workspace_qwen_visual_image`: workspace-qwen-visual.
- `velvet_bot/public_archive_display.py:144` `build_viewer_input_media`: fallback-viewer-edit-preview.
- `velvet_bot/public_archive_display.py:217` `send_viewer_archive_page`: fallback-viewer-send-preview.
- `velvet_bot/public_notifications.py:60` `run_public_notification_worker`: isolate-public-notification-worker-iteration.
- `velvet_bot/publication_inbox_middleware.py:60` `_capture`: best-effort-publication-inbox-capture.
- `velvet_bot/publication_worker.py:65` `run_publication_worker`: isolate-publication-worker-iteration.
- `velvet_bot/services/diagnostic_bundle.py:76` `emit`: isolate-diagnostic-log-buffer.
- `velvet_bot/services/media_save.py:55` `save_media_from_message`: report-media-save-failure.
- `velvet_bot/services/media_save.py:261` `_place_in_topic`: isolate-media-topic-delivery.
- `velvet_bot/services/system_health.py:126` `check`: isolate-database-health-probe.
- `velvet_bot/services/system_health.py:138` `check`: isolate-telegram-health-probe.
- `velvet_bot/services/workspace_qwen_quality.py:106` `_download_target`: workspace-qwen-file-fallback.
- `velvet_bot/services/workspace_qwen_quality.py:170` `process_once`: compensate-workspace-qwen-check.
- `velvet_bot/workers/manager.py:260` `_execute_once_with_result`: isolate-worker-iteration-failure.
- `velvet_bot/workers/manager.py:352` `_run_periodic`: isolate-worker-loop-failure.

## Unresolved broad exceptions by file


## Следующий срез

- Нет.

## Правило обновления

Запустите `python scripts/update_p2_stability_inventory.py --label <phase> --schema-version <n>` после изменения broad catches или callback acknowledgment.
