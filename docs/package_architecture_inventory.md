# Package-wide architecture inventory

- Generated from: `working-tree`
- Production modules: **606**
- Production LOC: **131355**
- Root modules: **113**
- Active Router imports: **84**
- Repository modules: **35**
- Startup installer stages: **28**
- Registered package violations: **526**
- Registered exemptions: **526**

## Layers

- `application`: **14** modules
- `composition`: **54** modules
- `core`: **7** modules
- `domain`: **175** modules
- `infrastructure`: **17** modules
- `other`: **1** modules
- `presentation`: **213** modules
- `root`: **114** modules
- `service`: **8** modules
- `worker`: **3** modules

## Shared/private baseline

- private cross-module accesses: **136**
- blocking known private contracts: **0**
- exact / normalized / semantic duplicate groups: **55 / 92 / 9**
- private access fingerprint: `73739e68a7a463d23be24137bac72837de2a2e60f18633ba1ce3bb9a89a73376`

## Installer graph

1. `install_runtime_stability` from `velvet_bot.runtime_stability.install_runtime_stability`; patched symbols: `error_center.ErrorIncidentCenter.start`, `error_center._is_recoverable_aiogram_polling_record`, `workers_module.build_worker_manager`.
2. `install_channel_analytics_datetime_compat` from `velvet_bot.app.channel_analytics_datetime_compat.install_channel_analytics_datetime_compat`; patched symbols: `channel_analytics.parse_channel_post`.
3. `install_ai_model_routing` from `velvet_bot.infrastructure.ai_model_routing.install_ai_model_routing`; patched symbols: `VisionClient.__init__`, `VisionClient._read_json`.
4. `install_friendly_media_worker` from `velvet_bot.domains.media_generation.friendly_worker.install_friendly_media_worker`; patched symbols: none detected.
5. `install_grs_resilience` from `velvet_bot.app.grs_resilience.install_grs_resilience`; patched symbols: `KieClient.get_grs_credits`, `KieTaskQueueService.fail`, `KieTaskRecord.from_grs_api`.
6. `install_grs_campaign_retry` from `velvet_bot.app.grs_campaign_retry.install_grs_campaign_retry`; patched symbols: `KieClient._create_grs_task`, `KieTaskQueueService.fail`, `grs_resilience._provider_reason_text`.
7. `install_grs_speedups` from `velvet_bot.app.grs_speedups.install_grs_speedups`; patched symbols: `BaseKieGenerationWorker._upload_references`, `CampaignGrsGenerationWorker._notify_terminal_failure_best_effort`, `EconomyKieGenerationWorker._record_provider_result`, `FriendlyKieGenerationWorker._friendly_progress_text`, `FriendlyKieGenerationWorker._start_progress`, `KieClient.__init__`, `PeriodicWorkerSpec.__init__`.
8. `install_telegram_progress_resilience` from `velvet_bot.app.telegram_progress_resilience.install_telegram_progress_resilience`; patched symbols: `FriendlyKieGenerationWorker._publish_progress`, `grs_resilience._provider_reason_text`.
9. `install_auf_cancel_ui` from `velvet_bot.app.auf_cancel_ui_install.install_auf_cancel_ui`; patched symbols: `AITaskQueueService.enqueue`, `FriendlyKieGenerationWorker._publish_progress`, `FriendlyKieGenerationWorker._start_progress`.
10. `install_auf_runtime_dispatcher` from `velvet_bot.app.auf_runtime_install.install_auf_runtime_dispatcher`; patched symbols: none detected.
11. `install_auf_reconciliation` from `velvet_bot.app.auf_reconciliation_install.install_auf_reconciliation`; patched symbols: none detected.
12. `install_auf_workspace_ui` from `velvet_bot.app.auf_workspace_ui_install.install_auf_workspace_ui`; patched symbols: `workspace_ui.build_modules_keyboard`.
13. `install_auf_wallet_ui` from `velvet_bot.app.auf_wallet_ui_install.install_auf_wallet_ui`; patched symbols: none detected.
14. `install_auf_photo_ui` from `velvet_bot.app.auf_photo_ui_install.install_auf_photo_ui`; patched symbols: none detected.
15. `install_auf_reference_privacy` from `velvet_bot.app.auf_reference_privacy_install.install_auf_reference_privacy`; patched symbols: `photo_router._can_access_source`, `photo_router._input_text`, `photo_router._load_sources`, `photo_router._review_text`, `photo_router._source_keyboard`.
16. `install_auf_photo_ratio_callback_fix` from `velvet_bot.app.auf_photo_ratio_callback_fix.install_auf_photo_ratio_callback_fix`; patched symbols: `photo_router._ratio_keyboard`.
17. `install_auf_user_portal` from `velvet_bot.app.auf_user_portal_install.install_auf_user_portal`; patched symbols: `video_router.settings_text`, `wallet_router.wallet_keyboard`.
18. `install_auf_photo_model_modes` from `velvet_bot.app.auf_photo_model_modes.install_auf_photo_model_modes`; patched symbols: `KieClient._create_grs_task`, `KieClient.wait_for_task`, `KieGenerationRequest.to_input`, `KieModelCatalog.provider_model`, `KiePricing.estimate_usd`, `photo_router.AufPhotoForm`, `photo_router._PHOTO_MODELS`, `photo_router._final_keyboard`, `photo_router._input_keyboard`, `photo_router._model`, `photo_router._model_keyboard`, `photo_router._request`, `photo_router._resolution_keyboard`, `photo_router._review_keyboard`, `photo_router.handle_auf_photo_action`, `photo_router.handle_auf_photo_command`, `photo_router.handle_auf_photo_input`.
19. `install_auf_owner_pricing_ui` from `velvet_bot.app.auf_owner_pricing_ui_install.install_auf_owner_pricing_ui`; patched symbols: none detected.
20. `install_original_image_delivery_hotfix` from `velvet_bot.app.original_image_delivery_hotfix.install_original_image_delivery_hotfix`; patched symbols: `FileDeliveryKieGenerationWorker._send_image_and_document`, `FriendlyKieGenerationWorker._send_image_and_document`.
21. `install_original_video_delivery_hotfix` from `velvet_bot.app.original_video_delivery_hotfix.install_original_video_delivery_hotfix`; patched symbols: `FileDeliveryKieGenerationWorker._send_video_and_document`, `FriendlyKieGenerationWorker._send_video_and_document`.
22. `install_auf_result_delivery_recovery` from `velvet_bot.app.auf_result_delivery_recovery.install_auf_result_delivery_recovery`; patched symbols: none detected.
23. `install_auf_active_delivery_fix` from `velvet_bot.app.auf_active_delivery_fix.install_auf_active_delivery_fix`; patched symbols: none detected.
24. `install_auf_charged_queue` from `velvet_bot.app.auf_charged_queue_install.install_auf_charged_queue`; patched symbols: none detected.
25. `install_auf_generation_receipts` from `velvet_bot.app.auf_generation_receipt_install.install_auf_generation_receipts`; patched symbols: none detected.
26. `install_krita_remote_worker` from `velvet_bot.app.krita_remote_install.install_krita_remote_worker`; patched symbols: `bootstrap._close_application_resources`, `bootstrap.build_worker_manager`, `workers_module.build_worker_manager`.
27. `install_auf_grs_brand` from `velvet_bot.app.auf_grs_brand_install.install_auf_grs_brand`; patched symbols: `grs_resilience._sanitize_auf_text`, `grs_resilience._sanitize_meow_text`.
28. `install_auf_branding` from `velvet_bot.app.auf_branding.install_auf_branding`; patched symbols: `Bot.__call__`.

## Violation baseline

- `database-acquire-outside-persistence`: **89**
- `domain-aiogram-import`: **19**
- `domain-layer-import`: **1**
- `dynamic-import`: **18**
- `foreign-assignment`: **38**
- `installed-sentinel`: **40**
- `installer-like-module`: **22**
- `method-assign-ignore`: **8**
- `monolithic-function`: **25**
- `monolithic-module-loc`: **17**
- `package-getattr-side-effect`: **19**
- `sql-outside-persistence`: **108**
- `type-ignore-usage`: **16**
- `typing-any-usage`: **106**

## Largest modules

- `velvet_bot/presentation/telegram/routers/workspace_owner_controls.py`: 2263 LOC, 40 functions, max function 474 lines, target `presentation`.
- `velvet_bot/app/auf_photo_model_modes.py`: 1782 LOC, 52 functions, max function 284 lines, target `composition`.
- `velvet_bot/presentation/telegram/routers/workspace_guided_actions.py`: 1773 LOC, 40 functions, max function 468 lines, target `presentation`.
- `velvet_bot/presentation/telegram/routers/workspace_auf.py`: 1427 LOC, 34 functions, max function 451 lines, target `presentation`.
- `velvet_bot/presentation/telegram/workspace_qwen.py`: 1236 LOC, 25 functions, max function 238 lines, target `presentation`.
- `velvet_bot/presentation/telegram/routers/workspace_auf_photo.py`: 1231 LOC, 38 functions, max function 248 lines, target `presentation`.
- `velvet_bot/presentation/telegram/routers/workspace_reference_library.py`: 1208 LOC, 26 functions, max function 170 lines, target `presentation`.
- `velvet_bot/presentation/telegram/routers/workspace_character_pickers.py`: 1152 LOC, 24 functions, max function 154 lines, target `presentation`.
- `velvet_bot/presentation/telegram/routers/workspace_auf_video.py`: 1102 LOC, 31 functions, max function 140 lines, target `presentation`.
- `velvet_bot/presentation/telegram/routers/workspace_auf_video_simple.py`: 1041 LOC, 37 functions, max function 169 lines, target `presentation`.
- `velvet_bot/presentation/telegram/routers/workspace_onboarding.py`: 1023 LOC, 31 functions, max function 222 lines, target `presentation`.
- `velvet_bot/domains/workspaces/character_management.py`: 1013 LOC, 24 functions, max function 117 lines, target `domain`.
- `velvet_bot/backup_service.py`: 900 LOC, 34 functions, max function 73 lines, target `application/<bounded-use-case>`.
- `velvet_bot/domains/workspaces/qwen_repository.py`: 898 LOC, 25 functions, max function 78 lines, target `domain`.
- `velvet_bot/media_sets.py`: 882 LOC, 20 functions, max function 115 lines, target `domains/<bounded-domain>`.
- `velvet_bot/domains/media_generation/models.py`: 858 LOC, 38 functions, max function 111 lines, target `domain`.
- `velvet_bot/presentation/telegram/routers/analytics_controllers/discussion_overrides.py`: 807 LOC, 11 functions, max function 333 lines, target `presentation`.
- `velvet_bot/ai_vision.py`: 774 LOC, 24 functions, max function 77 lines, target `domains/<bounded-domain>`.
- `velvet_bot/domains/telegram_storage/service.py`: 733 LOC, 23 functions, max function 109 lines, target `domain`.
- `velvet_bot/ai_quality.py`: 730 LOC, 22 functions, max function 82 lines, target `domains/<bounded-domain>`.

## Compatibility components

- `ai-quality-schema`: owner `runtime-compatibility`, replacement Explicit composition registration or removal regression., expiry Retire after consumers migrate under #420/#455.
- `set-consistency-dashboard`: owner `runtime-compatibility`, replacement Explicit composition registration or removal regression., expiry Retire after consumers migrate under #420/#455.
- `quality-calibration-dashboard`: owner `runtime-compatibility`, replacement Explicit composition registration or removal regression., expiry Retire after consumers migrate under #420/#455.
- `media-set-actions`: owner `runtime-compatibility`, replacement Explicit composition registration or removal regression., expiry Retire after consumers migrate under #420/#455.
- `media-set-ai-discovery`: owner `runtime-compatibility`, replacement Explicit composition registration or removal regression., expiry Retire after consumers migrate under #420/#455.
- `media-set-ui`: owner `runtime-compatibility`, replacement Explicit composition registration or removal regression., expiry Retire after consumers migrate under #420/#455.
- `owner-menu-navigation`: owner `runtime-compatibility`, replacement Explicit composition registration or removal regression., expiry Retire after consumers migrate under #420/#455.
- `quality-calibration-report-ui`: owner `runtime-compatibility`, replacement Explicit composition registration or removal regression., expiry Retire after consumers migrate under #420/#455.

## Gate contract

Every observed file/category fingerprint must have one versioned exemption with owner, reason, consumers, replacement, removal condition, regression test and issue reference. New or stale fingerprints fail CI. Shared-private and root-module fingerprints must match the reviewed baseline.
