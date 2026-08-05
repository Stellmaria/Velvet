# Shared contract inventory

- Production Python files: **648**
- Functions inventoried: **3747**
- Registered private cross-module debt: **170**
- Blocking known private contracts: **0**
- Exact duplicate groups: **66**
- Normalized near-duplicate groups: **96**
- Semantic near-duplicate groups: **9**

## Contract ownership

| Family | Current owner | Target | Retirement | Status | Consumers |
| --- | --- | --- | --- | --- | ---: |
| safe edit/send fallback | `velvet_bot.presentation.telegram.shared.editing` | `velvet_bot.presentation.telegram.shared.editing` | #419 | canonical | 15 |
| pagination keyboards | `controller-local keyboard builders` | `velvet_bot.presentation.telegram.shared.navigation` | #419 | transitional | 0 |
| deletion helpers | `velvet_bot.presentation.telegram.message_deletion` | `velvet_bot.presentation.telegram.shared.deletion` | #419 | transitional | 0 |
| media download/preview/original delivery | `velvet_bot.domains.media_generation.file_delivery_worker` | `velvet_bot.domains.media_generation.delivery_pipeline` | #457 | transitional | 0 |
| callback navigation and back buttons | `controller-local keyboard builders` | `velvet_bot.presentation.telegram.shared.navigation` | #419 | transitional | 0 |
| owner/editor/member guards | `velvet_bot.core.access` | `velvet_bot.core.access` | #460 | canonical | 9 |
| worker compensation/reporting boilerplate | `velvet_bot.domains.media_generation.worker` | `velvet_bot.domains.media_generation.worker` | #457 | canonical | 2 |
| message chunking/HTML fallback | `controller-local long-message senders` | `velvet_bot.presentation.telegram.shared.text` | #419 | transitional | 0 |
| repeated progress-card updates | `velvet_bot.app.telegram_progress_resilience` | `velvet_bot.presentation.telegram.progress` | #455 | transitional | 0 |
| task payload/result mapping/formatting | `Auf portal and delivery recovery installers` | `velvet_bot.application.media_tasks.contracts` | #458 | inventory-only | 9 |
| provider/model labels | `router-local model dictionaries` | `velvet_bot.domains.media_generation.model_catalog` | #459 | inventory-only | 9 |
| state compatibility accessors | `Auf portal compatibility reads` | `velvet_bot.presentation.telegram.state_compatibility` | #438 | transitional | 1 |
| retry/backoff policies | `media workers and Auf delivery recovery` | `velvet_bot.presentation.telegram.shared.retry` | #457 | transitional | 3 |
| workspace task history/ownership queries | `velvet_bot.app.auf_user_portal_install` | `velvet_bot.application.workspace_tasks` | #458 | inventory-only | 5 |

## Known private contracts

- `velvet_bot.app.auf_user_portal_install._task_line` → `format_user_task_line`: **migrated**, retirement #458.
- `velvet_bot.app.auf_user_portal_install._load_user_tasks` → `load_user_tasks`: **migrated**, retirement #458.
- `velvet_bot.app.auf_user_portal_install._task_list_keyboard` → `build_user_task_list_keyboard`: **migrated**, retirement #458.
- `velvet_bot.app.auf_user_portal_install._MODEL_NAMES` → `MODEL_NAMES`: **migrated**, retirement #459.
- `velvet_bot.presentation.telegram.routers.workspace_auf_video._edit_or_answer` → `edit_or_answer`: **migrated**, retirement #419.
- `velvet_bot.presentation.telegram.routers.workspace_auf_video_simple._validated_model` → `validated_model`: **migrated**, retirement #458.
- `velvet_bot.presentation.telegram.routers.workspace_auf_video._reference_from_data` → `reference_from_data`: **migrated**, retirement #458.

## Registered transitional private accesses

- `velvet_bot/app/auf_cancel_ui_install.py:91` `FriendlyKieGenerationWorker._start_progress` (module-attribute, repeated progress-card updates).
- `velvet_bot/app/auf_cancel_ui_install.py:92` `FriendlyKieGenerationWorker._publish_progress` (module-attribute, repeated progress-card updates).
- `velvet_bot/app/auf_cancel_ui_install.py:151` `FriendlyKieGenerationWorker._start_progress` (assignment, repeated progress-card updates).
- `velvet_bot/app/auf_cancel_ui_install.py:152` `FriendlyKieGenerationWorker._publish_progress` (assignment, repeated progress-card updates).
- `velvet_bot/app/auf_generation_price_privacy_install.py:35` `photo_ui.photo_router._final_keyboard` (module-attribute, state compatibility accessors).
- `velvet_bot/app/auf_generation_price_privacy_install.py:170` `photo_ui._state_value` (module-attribute, state compatibility accessors).
- `velvet_bot/app/auf_generation_price_privacy_install.py:228` `photo_ui.photo_router._truncate` (module-attribute, state compatibility accessors).
- `velvet_bot/app/auf_generation_price_privacy_install.py:274` `portal._video_request_from_state` (module-attribute, state compatibility accessors).
- `velvet_bot/app/auf_generation_receipt_install.py:412` `active._load_provider_urls` (module-attribute, media download/preview/original delivery).
- `velvet_bot/app/auf_margin_dashboard_install.py:23` `wallet_ui._wallet_keyboard` (module-attribute, state compatibility accessors).
- `velvet_bot/app/auf_margin_dashboard_install.py:49` `wallet_ui._callback` (module-attribute, callback navigation and back buttons).
- `velvet_bot/app/auf_margin_dashboard_install.py:88` `wallet_ui._callback` (module-attribute, callback navigation and back buttons).
- `velvet_bot/app/auf_margin_dashboard_install.py:113` `wallet_ui._wallet_keyboard` (assignment, state compatibility accessors).
- `velvet_bot/app/auf_owner_cost_privacy_install/__init__.py:1` `from velvet_bot.app.auf_owner_cost_privacy import _progress_text_for_user` (direct-import, repeated progress-card updates).
- `velvet_bot/app/auf_owner_pricing_ui_install.py:28` `photo_ui.photo_router._final_keyboard` (module-attribute, state compatibility accessors).
- `velvet_bot/app/auf_owner_pricing_ui_install.py:147` `photo_ui._state_value` (module-attribute, state compatibility accessors).
- `velvet_bot/app/auf_owner_pricing_ui_install.py:222` `photo_ui.photo_router._truncate` (module-attribute, state compatibility accessors).
- `velvet_bot/app/auf_owner_pricing_ui_install.py:254` `portal._video_request_from_state` (module-attribute, state compatibility accessors).
- `velvet_bot/app/auf_owner_pricing_ui_install.py:355` `wallet_router._entry_line` (module-attribute, state compatibility accessors).
- `velvet_bot/app/auf_owner_pricing_ui_install.py:367` `wallet_router._invoice_line` (module-attribute, state compatibility accessors).
- `velvet_bot/app/auf_owner_pricing_ui_install.py:405` `wallet_router._wallet_keyboard` (module-attribute, state compatibility accessors).
- `velvet_bot/app/auf_owner_pricing_ui_install.py:544` `wallet_router._render_wallet` (assignment, state compatibility accessors).
- `velvet_bot/app/auf_photo_model_modes.py:34` `from velvet_bot.presentation.telegram.routers.workspace_auf import _budget_block_reason` (direct-import, other repeated implementation).
- `velvet_bot/app/auf_photo_model_modes.py:109` `photo_router._state_value` (module-attribute, state compatibility accessors).
- `velvet_bot/app/auf_photo_model_modes.py:113` `photo_router._references` (module-attribute, state compatibility accessors).
- `velvet_bot/app/auf_photo_model_modes.py:385` `photo_router._truncate` (module-attribute, state compatibility accessors).
- `velvet_bot/app/auf_photo_model_modes.py:649` `photo_router._ratio_keyboard` (module-attribute, state compatibility accessors).
- `velvet_bot/app/auf_photo_model_modes.py:842` `photo_router._truncate` (module-attribute, state compatibility accessors).
- `velvet_bot/app/auf_photo_model_modes.py:853` `photo_ui._final_keyboard` (module-attribute, state compatibility accessors).
- `velvet_bot/app/auf_photo_model_modes.py:943` `photo_router._load_character_reference_rows` (module-attribute, state compatibility accessors).
- `velvet_bot/app/auf_photo_model_modes.py:978` `photo_router._save_references` (module-attribute, state compatibility accessors).
- `velvet_bot/app/auf_photo_model_modes.py:1094` `photo_router._save_references` (module-attribute, state compatibility accessors).
- `velvet_bot/app/auf_photo_model_modes.py:1103` `photo_router._save_references` (module-attribute, state compatibility accessors).
- `velvet_bot/app/auf_photo_model_modes.py:1111` `photo_router._load_sources` (module-attribute, state compatibility accessors).
- `velvet_bot/app/auf_photo_model_modes.py:1122` `photo_router._source_keyboard` (module-attribute, state compatibility accessors).
- `velvet_bot/app/auf_photo_model_modes.py:1135` `photo_router._load_characters` (module-attribute, state compatibility accessors).
- `velvet_bot/app/auf_photo_model_modes.py:1147` `photo_router._character_keyboard` (module-attribute, state compatibility accessors).
- `velvet_bot/app/auf_photo_model_modes.py:1395` `photo_router._save_references` (module-attribute, state compatibility accessors).
- `velvet_bot/app/auf_photo_model_modes.py:1423` `photo_router._load_sources` (module-attribute, state compatibility accessors).
- `velvet_bot/app/auf_photo_model_modes.py:1434` `photo_router._source_keyboard` (module-attribute, state compatibility accessors).
- `velvet_bot/app/auf_photo_model_modes.py:1437` `photo_router._load_sources` (module-attribute, state compatibility accessors).
- `velvet_bot/app/auf_photo_model_modes.py:1535` `getattr(pricing, '_original_model_first_quote')` (getattr, media download/preview/original delivery).
- `velvet_bot/app/auf_photo_model_modes.py:1682` `photo_router._PHOTO_MODELS` (assignment, state compatibility accessors).
- `velvet_bot/app/auf_photo_model_modes.py:1683` `photo_router._model` (assignment, state compatibility accessors).
- `velvet_bot/app/auf_photo_model_modes.py:1684` `photo_router._model_keyboard` (assignment, state compatibility accessors).
- `velvet_bot/app/auf_photo_model_modes.py:1685` `photo_router._input_keyboard` (assignment, state compatibility accessors).
- `velvet_bot/app/auf_photo_model_modes.py:1686` `photo_router._review_keyboard` (assignment, state compatibility accessors).
- `velvet_bot/app/auf_photo_model_modes.py:1687` `photo_router._resolution_keyboard` (assignment, state compatibility accessors).
- `velvet_bot/app/auf_photo_model_modes.py:1688` `photo_router._final_keyboard` (assignment, state compatibility accessors).
- `velvet_bot/app/auf_photo_model_modes.py:1705` `KieClient._create_grs_task` (assignment, other repeated implementation).
- `velvet_bot/app/auf_photo_ratio_callback_fix.py:111` `photo_router._ratio_keyboard` (assignment, state compatibility accessors).
- `velvet_bot/app/auf_photo_ui_install.py:42` `photo_router._final_keyboard` (module-attribute, state compatibility accessors).
- `velvet_bot/app/auf_photo_ui_install.py:115` `photo_router._truncate` (module-attribute, state compatibility accessors).
- `velvet_bot/app/auf_photo_ui_install.py:152` `photo_router._budget_block_reason` (module-attribute, state compatibility accessors).
- `velvet_bot/app/auf_photo_ui_install.py:239` `controller._require_auf_callback` (module-attribute, callback navigation and back buttons).
- `velvet_bot/app/auf_photo_ui_install.py:249` `photo_router._model` (module-attribute, state compatibility accessors).
- `velvet_bot/app/auf_photo_ui_install.py:290` `controller._require_auf_message` (module-attribute, owner/editor/member guards).
- `velvet_bot/app/auf_photo_ui_install.py:312` `controller._require_auf_message` (module-attribute, owner/editor/member guards).
- `velvet_bot/app/auf_reference_privacy_install.py:120` `photo_router._truncate` (module-attribute, state compatibility accessors).
- `velvet_bot/app/auf_reference_privacy_install.py:129` `photo_router._load_sources` (assignment, state compatibility accessors).
- `velvet_bot/app/auf_reference_privacy_install.py:131` `photo_router._source_keyboard` (assignment, state compatibility accessors).
- `velvet_bot/app/auf_wallet_currency_ui.py:246` `legacy._entry_line` (module-attribute, state compatibility accessors).
- `velvet_bot/app/original_image_delivery_hotfix.py:115` `FileDeliveryKieGenerationWorker._send_image_and_document` (assignment, media download/preview/original delivery).
- `velvet_bot/app/original_image_delivery_hotfix.py:118` `FriendlyKieGenerationWorker._send_image_and_document` (assignment, other repeated implementation).
- `velvet_bot/app/original_video_delivery_hotfix.py:117` `FileDeliveryKieGenerationWorker._send_video_and_document` (assignment, media download/preview/original delivery).
- `velvet_bot/app/original_video_delivery_hotfix.py:120` `FriendlyKieGenerationWorker._send_video_and_document` (assignment, other repeated implementation).
- `velvet_bot/app/telegram_progress_resilience.py:19` `from velvet_bot.domains.media_generation.worker import _ProgressMessage` (direct-import, repeated progress-card updates).
- `velvet_bot/app/telegram_progress_resilience.py:116` `FriendlyKieGenerationWorker._publish_progress` (assignment, repeated progress-card updates).
- `velvet_bot/app/workspace_owner_generation_hotfix.py:132` `photo_modes._model` (module-attribute, state compatibility accessors).
- `velvet_bot/app/workspace_owner_generation_hotfix.py:132` `photo_modes._state_value` (module-attribute, state compatibility accessors).
- `velvet_bot/domains/auf_runtime/cancellable_worker.py:8` `from velvet_bot.domains.media_generation.worker import _ProgressMessage` (direct-import, repeated progress-card updates).
- `velvet_bot/domains/auf_runtime/queue.py:7` `from velvet_bot.domains.ai_usage.tasks import _task_from_row` (direct-import, other repeated implementation).
- `velvet_bot/domains/auf_wallet/purchase.py:19` `from velvet_bot.domains.auf_wallet.store import _ensure_wallet` (direct-import, state compatibility accessors).
- `velvet_bot/domains/auf_wallet/purchase.py:19` `from velvet_bot.domains.auf_wallet.store import _wallet_from_row` (direct-import, state compatibility accessors).
- `velvet_bot/domains/media_generation/economy_worker.py:35` `from velvet_bot.domains.media_generation.worker import _ProgressMessage` (direct-import, repeated progress-card updates).
- `velvet_bot/domains/media_generation/economy_worker.py:35` `from velvet_bot.domains.media_generation.worker import _provider_progress` (direct-import, repeated progress-card updates).
- `velvet_bot/domains/media_generation/economy_worker.py:35` `from velvet_bot.domains.media_generation.worker import _request_from_task` (direct-import, other repeated implementation).
- `velvet_bot/domains/meow_wallet/store.py:2` `from velvet_bot.domains.auf_wallet.store import _ensure_wallet` (direct-import, state compatibility accessors).
- `velvet_bot/domains/meow_wallet/store.py:2` `from velvet_bot.domains.auf_wallet.store import _wallet_from_row` (direct-import, state compatibility accessors).
- `velvet_bot/infrastructure/ai/__init__.py:20` `from velvet_bot.infrastructure.ai.kie import _build_wan_27_input` (direct-import, other repeated implementation).
- `velvet_bot/infrastructure/media_delivery_repository_backfill.py:8` `from velvet_bot.infrastructure.media_delivery_repository_helpers import _VIDEO_MODELS` (direct-import, media download/preview/original delivery).
- `velvet_bot/infrastructure/media_delivery_repository_record.py:8` `from velvet_bot.infrastructure.media_delivery_repository_helpers import _VIDEO_MODELS` (direct-import, media download/preview/original delivery).
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
- `velvet_bot/presentation/telegram/routers/supervisor/codex.py:20` `from velvet_bot.presentation.telegram.supervisor.views import _codex_keyboard` (direct-import, other repeated implementation).
- `velvet_bot/presentation/telegram/routers/supervisor/codex.py:20` `from velvet_bot.presentation.telegram.supervisor.views import _confirm_keyboard` (direct-import, other repeated implementation).
- `velvet_bot/presentation/telegram/routers/supervisor/codex.py:20` `from velvet_bot.presentation.telegram.supervisor.views import _main_keyboard` (direct-import, other repeated implementation).
- `velvet_bot/presentation/telegram/routers/supervisor/codex.py:20` `from velvet_bot.presentation.telegram.supervisor.views import _task_keyboard` (direct-import, other repeated implementation).
- `velvet_bot/presentation/telegram/routers/supervisor/codex.py:20` `from velvet_bot.presentation.telegram.supervisor.views import _task_text` (direct-import, other repeated implementation).
- `velvet_bot/presentation/telegram/routers/supervisor/codex.py:20` `from velvet_bot.presentation.telegram.supervisor.views import _tasks_text` (direct-import, other repeated implementation).
- `velvet_bot/presentation/telegram/routers/supervisor/console.py:30` `from velvet_bot.presentation.telegram.supervisor.views import _main_keyboard` (direct-import, other repeated implementation).
- `velvet_bot/presentation/telegram/routers/supervisor/control.py:34` `from velvet_bot.presentation.telegram.supervisor.views import _accepted_keyboard` (direct-import, other repeated implementation).
- `velvet_bot/presentation/telegram/routers/supervisor/control.py:34` `from velvet_bot.presentation.telegram.supervisor.views import _bot_keyboard` (direct-import, other repeated implementation).
- `velvet_bot/presentation/telegram/routers/supervisor/control.py:34` `from velvet_bot.presentation.telegram.supervisor.views import _codex_keyboard` (direct-import, other repeated implementation).
- `velvet_bot/presentation/telegram/routers/supervisor/control.py:34` `from velvet_bot.presentation.telegram.supervisor.views import _confirm_keyboard` (direct-import, other repeated implementation).
- `velvet_bot/presentation/telegram/routers/supervisor/control.py:34` `from velvet_bot.presentation.telegram.supervisor.views import _git_keyboard` (direct-import, other repeated implementation).
- `velvet_bot/presentation/telegram/routers/supervisor/control.py:34` `from velvet_bot.presentation.telegram.supervisor.views import _logs_keyboard` (direct-import, other repeated implementation).
- `velvet_bot/presentation/telegram/routers/supervisor/control.py:34` `from velvet_bot.presentation.telegram.supervisor.views import _main_keyboard` (direct-import, other repeated implementation).
- `velvet_bot/presentation/telegram/routers/supervisor/control.py:34` `from velvet_bot.presentation.telegram.supervisor.views import _task_keyboard` (direct-import, other repeated implementation).
- `velvet_bot/presentation/telegram/routers/supervisor/control.py:34` `from velvet_bot.presentation.telegram.supervisor.views import _task_status_label` (direct-import, other repeated implementation).
- `velvet_bot/presentation/telegram/routers/supervisor/control.py:34` `from velvet_bot.presentation.telegram.supervisor.views import _task_text` (direct-import, other repeated implementation).
- `velvet_bot/presentation/telegram/routers/supervisor/control.py:34` `from velvet_bot.presentation.telegram.supervisor.views import _tasks_text` (direct-import, other repeated implementation).
- `velvet_bot/presentation/telegram/routers/supervisor/git.py:10` `from velvet_bot.presentation.telegram.supervisor.views import _confirm_keyboard` (direct-import, other repeated implementation).
- `velvet_bot/presentation/telegram/routers/supervisor/git.py:10` `from velvet_bot.presentation.telegram.supervisor.views import _git_keyboard` (direct-import, other repeated implementation).
- `velvet_bot/presentation/telegram/routers/supervisor/logs.py:12` `from velvet_bot.presentation.telegram.supervisor.views import _logs_keyboard` (direct-import, other repeated implementation).
- `velvet_bot/presentation/telegram/routers/supervisor/process.py:14` `from velvet_bot.presentation.telegram.supervisor.views import _confirm_keyboard` (direct-import, other repeated implementation).
- `velvet_bot/presentation/telegram/routers/supervisor/self_control.py:14` `from velvet_bot.presentation.telegram.supervisor.views import _confirm_keyboard` (direct-import, other repeated implementation).
- `velvet_bot/presentation/telegram/routers/supervisor/status.py:13` `from velvet_bot.presentation.telegram.supervisor.views import _bot_keyboard` (direct-import, other repeated implementation).
- `velvet_bot/presentation/telegram/routers/supervisor/status.py:13` `from velvet_bot.presentation.telegram.supervisor.views import _main_keyboard` (direct-import, other repeated implementation).
- `velvet_bot/presentation/telegram/routers/workspace_analytics_characters.py:16` `from velvet_bot.presentation.telegram.routers.analytics_controllers.channel import _character_lines` (direct-import, other repeated implementation).
- `velvet_bot/presentation/telegram/routers/workspace_analytics_characters.py:19` `from velvet_bot.presentation.telegram.routers.analytics_controllers.dashboard import _rank_lines` (direct-import, other repeated implementation).
- `velvet_bot/presentation/telegram/routers/workspace_auf_grs.py:12` `from velvet_bot.presentation.telegram.routers.workspace_auf import _callback` (direct-import, callback navigation and back buttons).
- `velvet_bot/presentation/telegram/routers/workspace_auf_photo.py:30` `from velvet_bot.presentation.telegram.routers.workspace_auf import _budget_block_reason` (direct-import, other repeated implementation).
- `velvet_bot/presentation/telegram/routers/workspace_auf_photo.py:30` `from velvet_bot.presentation.telegram.routers.workspace_auf import _callback` (direct-import, callback navigation and back buttons).
- `velvet_bot/presentation/telegram/routers/workspace_auf_photo.py:30` `from velvet_bot.presentation.telegram.routers.workspace_auf import _format_rub` (direct-import, other repeated implementation).
- `velvet_bot/presentation/telegram/routers/workspace_auf_photo.py:30` `from velvet_bot.presentation.telegram.routers.workspace_auf import _format_usd` (direct-import, other repeated implementation).
- `velvet_bot/presentation/telegram/routers/workspace_auf_photo_adjustments.py:8` `from velvet_bot.presentation.telegram.routers.workspace_auf import _callback` (direct-import, callback navigation and back buttons).
- `velvet_bot/presentation/telegram/routers/workspace_auf_photo_adjustments.py:14` `photo_router._edit_references_keyboard` (module-attribute, state compatibility accessors).
- `velvet_bot/presentation/telegram/routers/workspace_auf_photo_adjustments.py:44` `photo_router._edit_references_keyboard` (assignment, state compatibility accessors).
- `velvet_bot/presentation/telegram/routers/workspace_auf_photo_adjustments.py:53` `photo_router._references` (module-attribute, state compatibility accessors).
- `velvet_bot/presentation/telegram/routers/workspace_auf_photo_adjustments.py:53` `photo_router._state_value` (module-attribute, state compatibility accessors).
- `velvet_bot/presentation/telegram/routers/workspace_auf_photo_adjustments.py:58` `photo_router._save_references` (module-attribute, state compatibility accessors).
- `velvet_bot/presentation/telegram/routers/workspace_auf_video_simple.py:269` `legacy._truncate` (module-attribute, state compatibility accessors).
- `velvet_bot/presentation/telegram/routers/workspace_auf_video_simple.py:329` `legacy._reference_from_message` (module-attribute, state compatibility accessors).
- `velvet_bot/presentation/telegram/routers/workspace_auf_video_simple.py:746` `legacy._budget_block_reason` (module-attribute, state compatibility accessors).
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

- **media download/preview/original delivery**: 25 functions; shared transport/domain signals despite different names and literals.
- **pagination keyboards**: 76 functions; shared transport/domain signals despite different names and literals.
- **provider/model labels**: 62 functions; shared transport/domain signals despite different names and literals.
- **repeated progress-card updates**: 5 functions; shared transport/domain signals despite different names and literals.
- **retry/backoff policies**: 6 functions; shared transport/domain signals despite different names and literals.
- **safe edit/send fallback**: 59 functions; shared transport/domain signals despite different names and literals.
- **state compatibility accessors**: 3 functions; shared transport/domain signals despite different names and literals.
- **task payload/result mapping/formatting**: 26 functions; shared transport/domain signals despite different names and literals.
- **workspace task history/ownership queries**: 16 functions; shared transport/domain signals despite different names and literals.
