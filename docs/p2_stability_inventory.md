# P2 stability inventory

## Сводка

- raw: **70** / **43** files;
- approved: **18**;
- unresolved: **52** / **33** files;
- risky callbacks: **0**.

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
- `velvet_bot/domains/media_quality/service.py:90` `scan_target`: compensate-claimed-media-scan.
- `velvet_bot/domains/publication/service.py:68` `publish`: compensate-claimed-publication.
- `velvet_bot/domains/publication/service.py:89` `process_due_once`: isolate-scheduled-draft.

## Unresolved broad exceptions by file

- `velvet_bot/handlers/public_archive.py`: 5.
- `velvet_bot/error_center.py`: 4.
- `velvet_bot/handlers/media_browser.py`: 4.
- `velvet_bot/handlers/admin_media_display.py`: 2.
- `velvet_bot/handlers/characters.py`: 2.
- `velvet_bot/handlers/guest_archive.py`: 2.
- `velvet_bot/handlers/quality_set_ai.py`: 2.
- `velvet_bot/handlers/velvet_ai_formatting.py`: 2.
- `velvet_bot/public_archive_display.py`: 2.
- `velvet_bot/services/media_save.py`: 2.
- `velvet_bot/services/system_health.py`: 2.
- `velvet_bot/workers/manager.py`: 2.
- `velvet_bot/discussion_analytics_middleware.py`: 1.
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

- первый unresolved entry из актуального AST inventory.
