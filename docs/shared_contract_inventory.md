# Shared contract inventory

- Production Python files: **594**
- Functions inventoried: **3300**
- Private cross-module contracts: **177**
- Exact duplicate groups: **55**
- Normalized near-duplicate groups: **92**
- Semantic near-duplicate groups: **9**

## Contract ownership

| Family | Current owner | Target | Retirement | Status | Consumers |
| --- | --- | --- | --- | --- | ---: |
| safe edit/send fallback | `velvet_bot.presentation.telegram.shared.editing` | `velvet_bot.presentation.telegram.shared.editing` | #419 | canonical | 14 |
| pagination keyboards | `controller-local keyboard builders` | `velvet_bot.presentation.telegram.shared.navigation` | #419 | transitional | 0 |
| deletion helpers | `velvet_bot.presentation.telegram.message_deletion` | `velvet_bot.presentation.telegram.shared.deletion` | #419 | transitional | 0 |
| media download/preview/original delivery | `velvet_bot.domains.media_generation.file_delivery_worker` | `velvet_bot.domains.media_generation.delivery_pipeline` | #457 | transitional | 0 |
| callback navigation and back buttons | `controller-local keyboard builders` | `velvet_bot.presentation.telegram.shared.navigation` | #419 | transitional | 0 |
| owner/editor/member guards | `velvet_bot.core.access` | `velvet_bot.core.access` | #460 | canonical | 9 |
| worker compensation/reporting boilerplate | `velvet_bot.domains.media_generation.worker` | `velvet_bot.domains.media_generation.worker` | #457 | canonical | 4 |
| message chunking/HTML fallback | `controller-local long-message senders` | `velvet_bot.presentation.telegram.shared.text` | #419 | transitional | 0 |
| repeated progress-card updates | `velvet_bot.app.telegram_progress_resilience` | `velvet_bot.presentation.telegram.progress` | #455 | transitional | 0 |
| task payload/result mapping/formatting | `Auf portal and delivery recovery installers` | `velvet_bot.application.media_tasks.contracts` | #458 | inventory-only | 3 |
| provider/model labels | `router-local model dictionaries` | `velvet_bot.domains.media_generation.models` | #459 | inventory-only | 7 |
| state compatibility accessors | `Auf portal compatibility reads` | `velvet_bot.presentation.telegram.state_compatibility` | #438 | transitional | 1 |
| retry/backoff policies | `media workers and Auf delivery recovery` | `velvet_bot.presentation.telegram.shared.retry` | #457 | transitional | 2 |
| workspace task history/ownership queries | `velvet_bot.app.auf_user_portal_install` | `velvet_bot.application.workspace_tasks` | #458 | inventory-only | 3 |

## Known private contracts

- `velvet_bot.app.auf_user_portal_install._task_line` → `format_user_task_line`: **migrated**, retirement #458.
- `velvet_bot.app.auf_user_portal_install._load_user_tasks` → `load_user_tasks`: **migrated**, retirement #458.
- `velvet_bot.app.auf_user_portal_install._task_list_keyboard` → `build_user_task_list_keyboard`: **migrated**, retirement #458.
- `velvet_bot.app.auf_user_portal_install._MODEL_NAMES` → `MODEL_NAMES`: **migrated**, retirement #459.
- `velvet_bot.presentation.telegram.routers.workspace_auf_video._edit_or_answer` → `edit_or_answer`: **current-violation**, retirement #419.
- `velvet_bot.presentation.telegram.routers.workspace_auf_video_simple._validated_model` → `validated_model`: **migrated**, retirement #458.
- `velvet_bot.presentation.telegram.routers.workspace_auf_video._reference_from_data` → `reference_from_data`: **current-violation**, retirement #458.

## Current private accesses

- `velvet_bot/app/auf_active_delivery_fix.py:230` `recovery._redeliver_user_task` (module-attribute, media download/preview/original delivery).
- `velvet_bot/app/auf_active_delivery_fix.py:231` `recovery._redeliver_user_task` (assignment, media download/preview/original delivery).
- `velvet_bot/app/auf_active_delivery_fix.py:232` `recovery._task_delivery_buttons` (assignment, media download/preview/original delivery).
- `velvet_bot/app/auf_active_delivery_fix.py:235` `recovery._deliver_record_with_recovery` (module-attribute, media download/preview/original delivery).
- `velvet_bot/app/auf_cancel_ui_install.py:91` `FriendlyKieGenerationWorker._start_progress` (module-attribute, repeated progress-card updates).
- `velvet_bot/app/auf_cancel_ui_install.py:92` `FriendlyKieGenerationWorker._publish_progress` (module-attribute, repeated progress-card updates).
- `velvet_bot/app/auf_cancel_ui_install.py:151` `FriendlyKieGenerationWorker._start_progress` (assignment, repeated progress-card updates).
- `velvet_bot/app/auf_cancel_ui_install.py:152` `FriendlyKieGenerationWorker._publish_progress` (assignment, repeated progress-card updates).
- `velvet_bot/app/auf_grs_brand_install.py:68` `FriendlyKieGenerationWorker._friendly_progress_text` (module-attribute, repeated progress-card updates).
- `velvet_bot/app/auf_grs_brand_install.py:131` `grs_resilience.ResilientFriendlyKieGenerationWorker._friendly_progress_text` (assignment, repeated progress-card updates).
- `velvet_bot/app/auf_grs_brand_install.py:134` `BaseKieGenerationWorker._deliver_best_effort` (assignment, media download/preview/original delivery).
- `velvet_bot/app/auf_grs_brand_install.py:135` `grs_resilience.ResilientFriendlyKieGenerationWorker._deliver_best_effort` (assignment, media download/preview/original delivery).
- `velvet_bot/app/auf_grs_brand_install.py:138` `CampaignGrsGenerationWorker._deliver_best_effort` (assignment, media download/preview/original delivery).
- `velvet_bot/app/auf_photo_ratio_callback_fix.py:111` `photo_router._ratio_keyboard` (assignment, state compatibility accessors).
- `velvet_bot/app/auf_photo_ui_install.py:41` `photo_router._final_keyboard` (module-attribute, state compatibility accessors).
- `velvet_bot/app/auf_photo_ui_install.py:102` `photo_router._edit_or_answer` (module-attribute, safe edit/send fallback).
- `velvet_bot/app/auf_photo_ui_install.py:114` `photo_router._truncate` (module-attribute, state compatibility accessors).
- `velvet_bot/app/auf_photo_ui_install.py:151` `photo_router._budget_block_reason` (module-attribute, state compatibility accessors).
- `velvet_bot/app/auf_photo_ui_install.py:179` `photo_router._edit_or_answer` (module-attribute, safe edit/send fallback).
- `velvet_bot/app/auf_photo_ui_install.py:238` `controller._require_auf_callback` (module-attribute, callback navigation and back buttons).
- `velvet_bot/app/auf_photo_ui_install.py:248` `photo_router._model` (module-attribute, state compatibility accessors).
- `velvet_bot/app/auf_photo_ui_install.py:289` `controller._require_auf_message` (module-attribute, owner/editor/member guards).
- `velvet_bot/app/auf_photo_ui_install.py:311` `controller._require_auf_message` (module-attribute, owner/editor/member guards).
- `velvet_bot/app/grs_campaign_retry.py:15` `from velvet_bot.domains.media_generation.worker import _ProgressMessage` (direct-import, repeated progress-card updates).
- `velvet_bot/app/grs_campaign_retry.py:45` `KieClient._create_grs_task` (module-attribute, other repeated implementation).
- `velvet_bot/app/grs_campaign_retry.py:116` `grs_resilience._ORIGINAL_QUEUE_FAIL` (module-attribute, media download/preview/original delivery).
- `velvet_bot/app/grs_campaign_retry.py:233` `grs_resilience._format_credits` (module-attribute, other repeated implementation).
- `velvet_bot/app/grs_campaign_retry.py:272` `KieClient._create_grs_task` (assignment, other repeated implementation).
- `velvet_bot/app/grs_resilience.py:25` `from velvet_bot.domains.media_generation.worker import _ProgressMessage` (direct-import, repeated progress-card updates).
- `velvet_bot/app/grs_resilience.py:580` `workspace_auf._edit_or_answer` (module-attribute, safe edit/send fallback).
- `velvet_bot/app/grs_resilience.py:598` `workspace_auf._edit_or_answer` (assignment, safe edit/send fallback).
- `velvet_bot/app/grs_resilience.py:606` `workspace_auf_grs._edit_or_answer` (assignment, safe edit/send fallback).
- `velvet_bot/app/grs_speedups.py:19` `from velvet_bot.domains.media_generation.economy_worker import _reference_url_failure` (direct-import, other repeated implementation).
- `velvet_bot/app/grs_speedups.py:28` `from velvet_bot.domains.media_generation.worker import _ProgressMessage` (direct-import, repeated progress-card updates).
- `velvet_bot/app/grs_speedups.py:41` `FriendlyKieGenerationWorker._friendly_progress_text` (module-attribute, repeated progress-card updates).
- `velvet_bot/app/grs_speedups.py:42` `EconomyKieGenerationWorker._record_provider_result` (module-attribute, other repeated implementation).
- `velvet_bot/app/grs_speedups.py:340` `FriendlyKieGenerationWorker._start_progress` (assignment, repeated progress-card updates).
- `velvet_bot/app/grs_speedups.py:343` `FriendlyKieGenerationWorker._friendly_progress_text` (assignment, repeated progress-card updates).
- `velvet_bot/app/grs_speedups.py:346` `BaseKieGenerationWorker._upload_references` (assignment, other repeated implementation).
- `velvet_bot/app/grs_speedups.py:349` `EconomyKieGenerationWorker._record_provider_result` (assignment, other repeated implementation).
- `velvet_bot/app/original_image_delivery_hotfix.py:115` `FileDeliveryKieGenerationWorker._send_image_and_document` (assignment, media download/preview/original delivery).
- `velvet_bot/app/original_image_delivery_hotfix.py:118` `FriendlyKieGenerationWorker._send_image_and_document` (assignment, other repeated implementation).
- `velvet_bot/app/original_video_delivery_hotfix.py:117` `FileDeliveryKieGenerationWorker._send_video_and_document` (assignment, media download/preview/original delivery).
- `velvet_bot/app/original_video_delivery_hotfix.py:120` `FriendlyKieGenerationWorker._send_video_and_document` (assignment, other repeated implementation).
- `velvet_bot/app/telegram_progress_resilience.py:20` `from velvet_bot.domains.media_generation.worker import _ProgressMessage` (direct-import, repeated progress-card updates).
- `velvet_bot/app/telegram_progress_resilience.py:24` `grs_campaign_retry._provider_reason_without_model_chatter` (module-attribute, retry/backoff policies).
- `velvet_bot/app/telegram_progress_resilience.py:118` `FriendlyKieGenerationWorker._publish_progress` (assignment, repeated progress-card updates).
- `velvet_bot/domains/auf_runtime/cancellable_worker.py:8` `from velvet_bot.domains.media_generation.worker import _ProgressMessage` (direct-import, repeated progress-card updates).
- `velvet_bot/domains/auf_runtime/queue.py:7` `from velvet_bot.domains.ai_usage.tasks import _task_from_row` (direct-import, other repeated implementation).
- `velvet_bot/domains/auf_wallet/purchase.py:18` `from velvet_bot.domains.auf_wallet.store import _ensure_wallet` (direct-import, state compatibility accessors).
- `velvet_bot/domains/auf_wallet/purchase.py:18` `from velvet_bot.domains.auf_wallet.store import _wallet_from_row` (direct-import, state compatibility accessors).
- `velvet_bot/domains/media_generation/economy_worker.py:35` `from velvet_bot.domains.media_generation.worker import _ProgressMessage` (direct-import, repeated progress-card updates).
- `velvet_bot/domains/media_generation/economy_worker.py:35` `from velvet_bot.domains.media_generation.worker import _provider_progress` (direct-import, repeated progress-card updates).
- `velvet_bot/domains/media_generation/economy_worker.py:35` `from velvet_bot.domains.media_generation.worker import _request_from_task` (direct-import, other repeated implementation).
- `velvet_bot/domains/meow_wallet/store.py:2` `from velvet_bot.domains.auf_wallet.store import _ensure_wallet` (direct-import, state compatibility accessors).
- `velvet_bot/domains/meow_wallet/store.py:2` `from velvet_bot.domains.auf_wallet.store import _wallet_from_row` (direct-import, state compatibility accessors).
- `velvet_bot/infrastructure/ai/__init__.py:12` `from velvet_bot.infrastructure.ai.kie import _build_wan_27_input` (direct-import, other repeated implementation).
- `velvet_bot/presentation/telegram/quality_rework_entry.py:9` `from velvet_bot.presentation.telegram.routers.quality_operations_controllers.quality_rework import _list_keyboard` (direct-import, other repeated implementation).
- `velvet_bot/presentation/telegram/routers/analytics_controllers/management_aliases.py:21` `from velvet_bot.presentation.telegram.routers.analytics_controllers.management_common import _edit` (direct-import, other repeated implementation).
- `velvet_bot/presentation/telegram/routers/analytics_controllers/management_publications.py:18` `from velvet_bot.presentation.telegram.routers.analytics_controllers.management_common import _edit` (direct-import, other repeated implementation).
- `velvet_bot/presentation/telegram/routers/analytics_controllers/management_tags.py:16` `from velvet_bot.presentation.telegram.routers.analytics_controllers.management_common import _edit` (direct-import, other repeated implementation).
- `velvet_bot/presentation/telegram/routers/characters/kr_profile_overrides.py:19` `from velvet_bot.presentation.telegram.routers.characters.rename import _keyboard_with_rename` (direct-import, other repeated implementation).
- `velvet_bot/presentation/telegram/routers/characters/rename.py:23` `from velvet_bot.presentation.telegram.routers.characters.directory import _category_keyboard` (direct-import, other repeated implementation).
- `velvet_bot/presentation/telegram/routers/characters/rename.py:23` `from velvet_bot.presentation.telegram.routers.characters.directory import _profile_keyboard` (direct-import, other repeated implementation).
- `velvet_bot/presentation/telegram/routers/core_operations_controllers/workspace_watermark_draft_controller.py:75` `core_watermark._build_service` (module-attribute, other repeated implementation).
- `velvet_bot/presentation/telegram/routers/core_operations_controllers/workspace_watermark_draft_controller.py:118` `core_watermark._build_service` (module-attribute, other repeated implementation).
- `velvet_bot/presentation/telegram/routers/core_operations_controllers/workspace_watermark_draft_controller.py:123` `core_watermark._require_job_workspace` (module-attribute, owner/editor/member guards).
- `velvet_bot/presentation/telegram/routers/core_operations_controllers/workspace_watermark_draft_controller.py:142` `core_watermark._safe_edit` (module-attribute, safe edit/send fallback).
- `velvet_bot/presentation/telegram/routers/core_operations_controllers/workspace_watermark_draft_controller.py:204` `core_watermark._safe_edit` (module-attribute, safe edit/send fallback).
- `velvet_bot/presentation/telegram/routers/core_operations_controllers/workspace_watermark_draft_controller.py:222` `core_watermark._build_service` (module-attribute, other repeated implementation).
- `velvet_bot/presentation/telegram/routers/core_operations_controllers/workspace_watermark_draft_controller.py:229` `core_watermark._require_job_workspace` (module-attribute, owner/editor/member guards).
- `velvet_bot/presentation/telegram/routers/quality_operations_controllers/quality_ai_preview.py:89` `quality_ai_module._report_keyboard` (module-attribute, other repeated implementation).
- `velvet_bot/presentation/telegram/routers/quality_operations_controllers/quality_ai_preview.py:114` `quality_ai_module._report_keyboard` (assignment, other repeated implementation).
- `velvet_bot/presentation/telegram/routers/quality_operations_controllers/quality_ai_preview.py:115` `quality_ai_module._send_preview` (assignment, media download/preview/original delivery).
- `velvet_bot/presentation/telegram/routers/quality_operations_controllers/quality_set_ai.py:25` `from velvet_bot.domains.media_sets.ai_repository import _load_set` (direct-import, other repeated implementation).
- `velvet_bot/presentation/telegram/routers/quality_operations_controllers/velvet_ai_pose.py:21` `from velvet_bot.presentation.telegram.routers.quality_operations_controllers.velvet_ai_image_prompt import _comparison_models` (direct-import, other repeated implementation).
- `velvet_bot/presentation/telegram/routers/quality_operations_controllers/velvet_ai_pose.py:21` `from velvet_bot.presentation.telegram.routers.quality_operations_controllers.velvet_ai_image_prompt import _split_preformatted` (direct-import, other repeated implementation).
- `velvet_bot/presentation/telegram/routers/supervisor/codex.py:19` `from velvet_bot.presentation.telegram.supervisor.views import _codex_keyboard` (direct-import, other repeated implementation).
- `velvet_bot/presentation/telegram/routers/supervisor/codex.py:19` `from velvet_bot.presentation.telegram.supervisor.views import _confirm_keyboard` (direct-import, other repeated implementation).
- `velvet_bot/presentation/telegram/routers/supervisor/codex.py:19` `from velvet_bot.presentation.telegram.supervisor.views import _main_keyboard` (direct-import, other repeated implementation).
- `velvet_bot/presentation/telegram/routers/supervisor/codex.py:19` `from velvet_bot.presentation.telegram.supervisor.views import _safe_edit` (direct-import, safe edit/send fallback).
- `velvet_bot/presentation/telegram/routers/supervisor/codex.py:19` `from velvet_bot.presentation.telegram.supervisor.views import _task_keyboard` (direct-import, other repeated implementation).
- `velvet_bot/presentation/telegram/routers/supervisor/codex.py:19` `from velvet_bot.presentation.telegram.supervisor.views import _task_text` (direct-import, other repeated implementation).
- `velvet_bot/presentation/telegram/routers/supervisor/codex.py:19` `from velvet_bot.presentation.telegram.supervisor.views import _tasks_text` (direct-import, other repeated implementation).
- `velvet_bot/presentation/telegram/routers/supervisor/console.py:29` `from velvet_bot.presentation.telegram.supervisor.views import _main_keyboard` (direct-import, other repeated implementation).
- `velvet_bot/presentation/telegram/routers/supervisor/console.py:29` `from velvet_bot.presentation.telegram.supervisor.views import _safe_edit` (direct-import, safe edit/send fallback).
- `velvet_bot/presentation/telegram/routers/supervisor/control.py:34` `from velvet_bot.presentation.telegram.supervisor.views import _accepted_keyboard` (direct-import, other repeated implementation).
- `velvet_bot/presentation/telegram/routers/supervisor/control.py:34` `from velvet_bot.presentation.telegram.supervisor.views import _bot_keyboard` (direct-import, other repeated implementation).
- `velvet_bot/presentation/telegram/routers/supervisor/control.py:34` `from velvet_bot.presentation.telegram.supervisor.views import _codex_keyboard` (direct-import, other repeated implementation).
- `velvet_bot/presentation/telegram/routers/supervisor/control.py:34` `from velvet_bot.presentation.telegram.supervisor.views import _confirm_keyboard` (direct-import, other repeated implementation).
- `velvet_bot/presentation/telegram/routers/supervisor/control.py:34` `from velvet_bot.presentation.telegram.supervisor.views import _git_keyboard` (direct-import, other repeated implementation).
- `velvet_bot/presentation/telegram/routers/supervisor/control.py:34` `from velvet_bot.presentation.telegram.supervisor.views import _logs_keyboard` (direct-import, other repeated implementation).
- `velvet_bot/presentation/telegram/routers/supervisor/control.py:34` `from velvet_bot.presentation.telegram.supervisor.views import _main_keyboard` (direct-import, other repeated implementation).
- `velvet_bot/presentation/telegram/routers/supervisor/control.py:34` `from velvet_bot.presentation.telegram.supervisor.views import _safe_edit` (direct-import, safe edit/send fallback).
- `velvet_bot/presentation/telegram/routers/supervisor/control.py:34` `from velvet_bot.presentation.telegram.supervisor.views import _task_keyboard` (direct-import, other repeated implementation).
- `velvet_bot/presentation/telegram/routers/supervisor/control.py:34` `from velvet_bot.presentation.telegram.supervisor.views import _task_status_label` (direct-import, other repeated implementation).
- `velvet_bot/presentation/telegram/routers/supervisor/control.py:34` `from velvet_bot.presentation.telegram.supervisor.views import _task_text` (direct-import, other repeated implementation).
- `velvet_bot/presentation/telegram/routers/supervisor/control.py:34` `from velvet_bot.presentation.telegram.supervisor.views import _tasks_text` (direct-import, other repeated implementation).
- `velvet_bot/presentation/telegram/routers/supervisor/git.py:9` `from velvet_bot.presentation.telegram.supervisor.views import _confirm_keyboard` (direct-import, other repeated implementation).
- `velvet_bot/presentation/telegram/routers/supervisor/git.py:9` `from velvet_bot.presentation.telegram.supervisor.views import _git_keyboard` (direct-import, other repeated implementation).
- `velvet_bot/presentation/telegram/routers/supervisor/git.py:9` `from velvet_bot.presentation.telegram.supervisor.views import _safe_edit` (direct-import, safe edit/send fallback).
- `velvet_bot/presentation/telegram/routers/supervisor/logs.py:11` `from velvet_bot.presentation.telegram.supervisor.views import _logs_keyboard` (direct-import, other repeated implementation).
- `velvet_bot/presentation/telegram/routers/supervisor/logs.py:11` `from velvet_bot.presentation.telegram.supervisor.views import _safe_edit` (direct-import, safe edit/send fallback).
- `velvet_bot/presentation/telegram/routers/supervisor/process.py:8` `from velvet_bot.presentation.telegram.supervisor.views import _confirm_keyboard` (direct-import, other repeated implementation).
- `velvet_bot/presentation/telegram/routers/supervisor/process.py:8` `from velvet_bot.presentation.telegram.supervisor.views import _safe_edit` (direct-import, safe edit/send fallback).
- `velvet_bot/presentation/telegram/routers/supervisor/self_control.py:13` `from velvet_bot.presentation.telegram.supervisor.views import _confirm_keyboard` (direct-import, other repeated implementation).
- `velvet_bot/presentation/telegram/routers/supervisor/self_control.py:13` `from velvet_bot.presentation.telegram.supervisor.views import _safe_edit` (direct-import, safe edit/send fallback).
- `velvet_bot/presentation/telegram/routers/supervisor/status.py:12` `from velvet_bot.presentation.telegram.supervisor.views import _bot_keyboard` (direct-import, other repeated implementation).
- `velvet_bot/presentation/telegram/routers/supervisor/status.py:12` `from velvet_bot.presentation.telegram.supervisor.views import _main_keyboard` (direct-import, other repeated implementation).
- `velvet_bot/presentation/telegram/routers/supervisor/status.py:12` `from velvet_bot.presentation.telegram.supervisor.views import _safe_edit` (direct-import, safe edit/send fallback).
- `velvet_bot/presentation/telegram/routers/workspace_analytics_characters.py:16` `from velvet_bot.presentation.telegram.routers.analytics_controllers.channel import _character_lines` (direct-import, other repeated implementation).
- `velvet_bot/presentation/telegram/routers/workspace_analytics_characters.py:19` `from velvet_bot.presentation.telegram.routers.analytics_controllers.dashboard import _rank_lines` (direct-import, other repeated implementation).
- `velvet_bot/presentation/telegram/routers/workspace_auf_grs.py:11` `from velvet_bot.presentation.telegram.routers.workspace_auf import _callback` (direct-import, callback navigation and back buttons).
- `velvet_bot/presentation/telegram/routers/workspace_auf_grs.py:11` `from velvet_bot.presentation.telegram.routers.workspace_auf import _edit_or_answer` (direct-import, safe edit/send fallback).
- `velvet_bot/presentation/telegram/routers/workspace_auf_photo.py:29` `from velvet_bot.presentation.telegram.routers.workspace_auf import _budget_block_reason` (direct-import, other repeated implementation).
- `velvet_bot/presentation/telegram/routers/workspace_auf_photo.py:29` `from velvet_bot.presentation.telegram.routers.workspace_auf import _callback` (direct-import, callback navigation and back buttons).
- `velvet_bot/presentation/telegram/routers/workspace_auf_photo.py:29` `from velvet_bot.presentation.telegram.routers.workspace_auf import _edit_or_answer` (direct-import, safe edit/send fallback).
- `velvet_bot/presentation/telegram/routers/workspace_auf_photo.py:29` `from velvet_bot.presentation.telegram.routers.workspace_auf import _format_rub` (direct-import, other repeated implementation).
- `velvet_bot/presentation/telegram/routers/workspace_auf_photo.py:29` `from velvet_bot.presentation.telegram.routers.workspace_auf import _format_usd` (direct-import, other repeated implementation).
- `velvet_bot/presentation/telegram/routers/workspace_auf_photo_adjustments.py:7` `from velvet_bot.presentation.telegram.routers.workspace_auf import _callback` (direct-import, callback navigation and back buttons).
- `velvet_bot/presentation/telegram/routers/workspace_auf_photo_adjustments.py:7` `from velvet_bot.presentation.telegram.routers.workspace_auf import _edit_or_answer` (direct-import, safe edit/send fallback).
- `velvet_bot/presentation/telegram/routers/workspace_auf_photo_adjustments.py:14` `photo_router._edit_references_keyboard` (module-attribute, state compatibility accessors).
- `velvet_bot/presentation/telegram/routers/workspace_auf_photo_adjustments.py:44` `photo_router._edit_references_keyboard` (assignment, state compatibility accessors).
- `velvet_bot/presentation/telegram/routers/workspace_auf_photo_adjustments.py:53` `photo_router._references` (module-attribute, state compatibility accessors).
- `velvet_bot/presentation/telegram/routers/workspace_auf_photo_adjustments.py:53` `photo_router._state_value` (module-attribute, state compatibility accessors).
- `velvet_bot/presentation/telegram/routers/workspace_auf_photo_adjustments.py:58` `photo_router._save_references` (module-attribute, state compatibility accessors).
- `velvet_bot/presentation/telegram/routers/workspace_auf_video_simple.py:25` `from velvet_bot.presentation.telegram.routers.workspace_auf_video import _callback` (direct-import, callback navigation and back buttons).
- `velvet_bot/presentation/telegram/routers/workspace_auf_video_simple.py:25` `from velvet_bot.presentation.telegram.routers.workspace_auf_video import _format_rub` (direct-import, state compatibility accessors).
- `velvet_bot/presentation/telegram/routers/workspace_auf_video_simple.py:25` `from velvet_bot.presentation.telegram.routers.workspace_auf_video import _format_usd` (direct-import, state compatibility accessors).
- `velvet_bot/presentation/telegram/routers/workspace_auf_video_simple.py:269` `legacy._truncate` (module-attribute, state compatibility accessors).
- `velvet_bot/presentation/telegram/routers/workspace_auf_video_simple.py:303` `legacy._edit_or_answer` (module-attribute, safe edit/send fallback).
- `velvet_bot/presentation/telegram/routers/workspace_auf_video_simple.py:329` `legacy._reference_from_message` (module-attribute, state compatibility accessors).
- `velvet_bot/presentation/telegram/routers/workspace_auf_video_simple.py:394` `legacy._reference_from_data` (module-attribute, state compatibility accessors).
- `velvet_bot/presentation/telegram/routers/workspace_auf_video_simple.py:491` `legacy._edit_or_answer` (module-attribute, safe edit/send fallback).
- `velvet_bot/presentation/telegram/routers/workspace_auf_video_simple.py:516` `legacy._edit_or_answer` (module-attribute, safe edit/send fallback).
- `velvet_bot/presentation/telegram/routers/workspace_auf_video_simple.py:528` `legacy._edit_or_answer` (module-attribute, safe edit/send fallback).
- `velvet_bot/presentation/telegram/routers/workspace_auf_video_simple.py:582` `legacy._edit_or_answer` (module-attribute, safe edit/send fallback).
- `velvet_bot/presentation/telegram/routers/workspace_auf_video_simple.py:595` `legacy._reference_from_data` (module-attribute, state compatibility accessors).
- `velvet_bot/presentation/telegram/routers/workspace_auf_video_simple.py:599` `legacy._edit_or_answer` (module-attribute, safe edit/send fallback).
- `velvet_bot/presentation/telegram/routers/workspace_auf_video_simple.py:626` `legacy._reference_from_data` (module-attribute, state compatibility accessors).
- `velvet_bot/presentation/telegram/routers/workspace_auf_video_simple.py:667` `legacy._edit_or_answer` (module-attribute, safe edit/send fallback).
- `velvet_bot/presentation/telegram/routers/workspace_auf_video_simple.py:678` `legacy._reference_from_data` (module-attribute, state compatibility accessors).
- `velvet_bot/presentation/telegram/routers/workspace_auf_video_simple.py:679` `legacy._reference_from_data` (module-attribute, state compatibility accessors).
- `velvet_bot/presentation/telegram/routers/workspace_auf_video_simple.py:700` `legacy._edit_or_answer` (module-attribute, safe edit/send fallback).
- `velvet_bot/presentation/telegram/routers/workspace_auf_video_simple.py:717` `legacy._reference_from_data` (module-attribute, state compatibility accessors).
- `velvet_bot/presentation/telegram/routers/workspace_auf_video_simple.py:718` `legacy._reference_from_data` (module-attribute, state compatibility accessors).
- `velvet_bot/presentation/telegram/routers/workspace_auf_video_simple.py:746` `legacy._budget_block_reason` (module-attribute, state compatibility accessors).
- `velvet_bot/presentation/telegram/routers/workspace_auf_video_simple.py:782` `legacy._edit_or_answer` (module-attribute, safe edit/send fallback).
- `velvet_bot/presentation/telegram/routers/workspace_auf_video_simple.py:850` `legacy._reference_from_data` (module-attribute, state compatibility accessors).
- `velvet_bot/presentation/telegram/routers/workspace_auf_video_simple.py:856` `legacy._reference_from_data` (module-attribute, state compatibility accessors).
- `velvet_bot/presentation/telegram/routers/workspace_guided_actions.py:50` `from velvet_bot.presentation.telegram.routers.workspace_onboarding import _intro_keyboard` (direct-import, other repeated implementation).
- `velvet_bot/presentation/telegram/routers/workspace_publications.py:22` `from velvet_bot.presentation.telegram.routers.publication.center import _center_keyboard` (direct-import, other repeated implementation).
- `velvet_bot/presentation/telegram/routers/workspace_publications.py:22` `from velvet_bot.presentation.telegram.routers.publication.center import _draft_keyboard` (direct-import, other repeated implementation).
- `velvet_bot/presentation/telegram/routers/workspace_reference_buttons.py:25` `from velvet_bot.presentation.telegram.routers.workspace_owner_controls import _load_reference_characters` (direct-import, other repeated implementation).
- `velvet_bot/presentation/telegram/routers/workspace_reference_buttons.py:25` `from velvet_bot.presentation.telegram.routers.workspace_owner_controls import _reference_dashboard_keyboard` (direct-import, other repeated implementation).
- `velvet_bot/presentation/telegram/routers/workspace_reference_buttons.py:25` `from velvet_bot.presentation.telegram.routers.workspace_owner_controls import _require_personal_module` (direct-import, owner/editor/member guards).
- `velvet_bot/presentation/telegram/routers/workspace_reference_library.py:46` `from velvet_bot.presentation.telegram.routers.references.comparison import _format_report` (direct-import, other repeated implementation).
- `velvet_bot/presentation/telegram/routers/workspace_reference_library.py:46` `from velvet_bot.presentation.telegram.routers.references.comparison import _result_file` (direct-import, other repeated implementation).
- `velvet_bot/presentation/telegram/routers/workspace_watermark.py:31` `from velvet_bot.presentation.telegram.routers.core_operations_controllers.watermark import _build_service` (direct-import, other repeated implementation).
- `velvet_bot/presentation/telegram/routers/workspace_watermark.py:39` `from velvet_bot.presentation.telegram.routers.workspace_owner_controls import _require_personal_module` (direct-import, owner/editor/member guards).
- `velvet_bot/presentation/telegram/routers/workspace_watermark_archive_only.py:22` `owner_controls._DOWNLOAD_AUDIENCE_ACTIONS` (module-attribute, other repeated implementation).
- `velvet_bot/presentation/telegram/routers/workspace_watermark_archive_only.py:23` `owner_controls._DOWNLOAD_VARIANT_ACTIONS` (module-attribute, other repeated implementation).
- `velvet_bot/presentation/telegram/routers/workspace_watermark_archive_only.py:62` `owner_controls._require_personal_module` (module-attribute, owner/editor/member guards).
- `velvet_bot/presentation/telegram/routers/workspace_watermark_archive_only.py:87` `owner_controls._require_personal_module` (module-attribute, owner/editor/member guards).
- `velvet_bot/presentation/telegram/routers/workspace_watermark_archive_only.py:207` `owner_controls._show_media_settings` (module-attribute, other repeated implementation).
- `velvet_bot/presentation/telegram/routers/workspace_watermark_archive_only.py:259` `owner_controls._DOWNLOAD_AUDIENCE_ACTIONS` (module-attribute, other repeated implementation).
- `velvet_bot/presentation/telegram/routers/workspace_watermark_archive_only.py:263` `owner_controls._DOWNLOAD_VARIANT_ACTIONS` (module-attribute, other repeated implementation).
- `velvet_bot/presentation/telegram/routers/workspace_watermark_archive_only.py:277` `owner_controls._show_media_settings` (module-attribute, other repeated implementation).
- `velvet_bot/presentation/telegram/routers/workspace_watermark_archive_only.py:294` `owner_controls._show_media_settings` (module-attribute, other repeated implementation).
- `velvet_bot/presentation/telegram/save_mode_runtime.py:136` `legacy_save._batch_save_keyboard` (module-attribute, other repeated implementation).
- `velvet_bot/presentation/telegram/save_mode_runtime.py:189` `legacy_save._require_workspace_save_access` (module-attribute, owner/editor/member guards).
- `velvet_bot/presentation/telegram/save_mode_runtime.py:262` `legacy_save._batch_save_keyboard` (module-attribute, other repeated implementation).
- `velvet_bot/presentation/telegram/workspace_qwen.py:386` `workspace_owner_controls._archive_callback` (module-attribute, callback navigation and back buttons).
- `velvet_bot/presentation/telegram/workspace_ui_adjustments.py:119` `workspace_owner_controls._archive_callback` (module-attribute, callback navigation and back buttons).
- `velvet_bot/presentation/telegram/workspace_ui_adjustments.py:217` `workspace_owner_controls._archive_callback` (module-attribute, callback navigation and back buttons).
- `velvet_bot/presentation/telegram/workspace_ui_adjustments.py:239` `workspace_character_pickers._card_keyboard` (assignment, other repeated implementation).
- `velvet_bot/presentation/telegram/workspace_ui_adjustments.py:257` `workspace_character_pickers._card_keyboard` (module-attribute, other repeated implementation).

## Semantic near-duplicate families

- **media download/preview/original delivery**: 24 functions; shared transport/domain signals despite different names and literals.
- **pagination keyboards**: 74 functions; shared transport/domain signals despite different names and literals.
- **provider/model labels**: 42 functions; shared transport/domain signals despite different names and literals.
- **repeated progress-card updates**: 6 functions; shared transport/domain signals despite different names and literals.
- **retry/backoff policies**: 6 functions; shared transport/domain signals despite different names and literals.
- **safe edit/send fallback**: 59 functions; shared transport/domain signals despite different names and literals.
- **state compatibility accessors**: 5 functions; shared transport/domain signals despite different names and literals.
- **task payload/result mapping/formatting**: 21 functions; shared transport/domain signals despite different names and literals.
- **workspace task history/ownership queries**: 14 functions; shared transport/domain signals despite different names and literals.
