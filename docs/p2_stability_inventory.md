# P2 stability inventory

AST-инвентаризация широких исключений и callback acknowledgment.

## Сводка

- broad exceptions raw: **70** в **43** файлах;
- approved orchestration boundaries: **7**;
- unresolved broad exceptions: **63** в **37** файлах;
- callback handlers: **97**;
- missing/late acknowledgment: **0**;
- guarded acknowledgment: **25**;
- delegated wrappers: **4**.

## Approved broad boundaries

- `velvet_bot/ai_job_runtime.py:55` `create`: compensate-created-ai-job.
- `velvet_bot/ai_quality.py:703` `process_once`: compensate-claimed-ai-quality.
- `velvet_bot/ai_vision.py:725` `process_once`: compensate-claimed-ai-profile.
- `velvet_bot/calibrated_ai_quality.py:111` `process_once`: compensate-claimed-calibrated-quality.
- `velvet_bot/domains/media_quality/service.py:90` `scan_target`: compensate-claimed-media-scan.
- `velvet_bot/domains/publication/service.py:68` `publish`: compensate-claimed-publication.
- `velvet_bot/domains/publication/service.py:89` `process_due_once`: isolate-scheduled-draft.

## Unresolved broad exceptions by file

- `velvet_bot/app/bootstrap.py`: 7.
- `velvet_bot/handlers/public_archive.py`: 5.
- `velvet_bot/error_center.py`: 4.
- `velvet_bot/handlers/media_browser.py`: 4.
- `velvet_bot/backup_service.py`: 2.
- `velvet_bot/handlers/admin_media_display.py`: 2.
- `velvet_bot/handlers/characters.py`: 2.
- `velvet_bot/handlers/guest_archive.py`: 2.
- `velvet_bot/handlers/quality_set_ai.py`: 2.
- `velvet_bot/handlers/velvet_ai_formatting.py`: 2.
- `velvet_bot/public_archive_display.py`: 2.
- `velvet_bot/services/media_save.py`: 2.
- `velvet_bot/services/system_health.py`: 2.
- `velvet_bot/workers/manager.py`: 2.
- `velvet_bot/audit.py`: 1.
- `velvet_bot/backup_runtime.py`: 1.
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

## Risky callbacks

- Нет. Callback late/missing baseline закрыт.

## Следующий срез

- `velvet_bot/app/bootstrap.py`: broad-exception triage shutdown/startup boundaries.

## Правило обновления

Approved boundary требует inline-маркер и отдельный поведенческий тест. Raw count не уменьшается от классификации; unresolved count отражает оставшийся долг.
