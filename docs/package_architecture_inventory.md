# Package-wide architecture inventory

- Generated from: `p1-package-architecture-baseline`
- Production modules: **605**
- Production LOC: **129015**
- Root modules: **113**
- Active Router imports: **84**
- Repository modules: **35**
- Startup installer stages: **0**
- Registered package violations: **516**
- Registered exemptions: **516**

## Layers

- `application`: **14** modules
- `composition`: **53** modules
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


## Violation baseline

- `database-acquire-outside-persistence`: **88**
- `domain-aiogram-import`: **19**
- `domain-layer-import`: **1**
- `dynamic-import`: **17**
- `foreign-assignment`: **37**
- `installed-sentinel`: **39**
- `installer-like-module`: **22**
- `method-assign-ignore`: **7**
- `monolithic-function`: **24**
- `monolithic-module-loc`: **16**
- `package-getattr-side-effect`: **19**
- `sql-outside-persistence`: **107**
- `type-ignore-usage`: **15**
- `typing-any-usage`: **105**

## Largest modules

- `velvet_bot/presentation/telegram/routers/workspace_owner_controls.py`: 2263 LOC, 40 functions, max function 474 lines, target `presentation`.
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
- `velvet_bot/presentation/telegram/routers/workspace_taxonomy_admin.py`: 718 LOC, 20 functions, max function 115 lines, target `presentation`.

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
