# Gap-аудит канонического ТЗ workspace

- Источник: `docs/requirements/workspace_product.md`
- Дата аудита: `2026-08-02`
- Родительская issue: `#430`
- Полностью подтверждено: **11** строк
- Подтверждено с follow-up или live-приёмкой: **6** строк

## Матрица

| ID | Раздел | Требование | Статус | Реализация | Тесты | Follow-up |
|---|---:|---|---|---|---|---|
| WSP-01 | 1 | Общая модель и tenant isolation | `verified` | `migrations/901_workspaces.sql`<br>`velvet_bot/domains/workspaces/service.py` | `tests/test_workspace_product_access.py`<br>`tests/test_workspace_taxonomy_catalog.py` | — |
| WSP-02 | 2 | Creation grants | `verified` | `migrations/903_workspace_product_access.sql`<br>`velvet_bot/domains/workspaces/product_service.py` | `tests/test_workspace_product_access.py` | — |
| WSP-03 | 3 | Экран /start | `verified` | `velvet_bot/workspace_ui.py`<br>`velvet_bot/presentation/telegram/routers/workspaces.py` | `tests/test_workspace_product_access.py`<br>`tests/test_workspace_member_dashboard.py` | — |
| WSP-04 | 4 | Приватность и публичность | `verified` | `velvet_bot/domains/workspaces/product_service.py`<br>`velvet_bot/domains/public_archive/visibility.py` | `tests/test_workspace_product_access.py`<br>`tests/test_workspace_media_controls.py` | — |
| WSP-05 | 5 | Выбор публичного workspace | `verified` | `velvet_bot/public_catalog.py`<br>`velvet_bot/presentation/telegram/routers/public_archive` | `tests/test_workspace_taxonomy_catalog.py`<br>`tests/test_workspace_product_access.py` | — |
| WSP-06 | 6 | Module policy is_allowed/is_enabled | `verified` | `velvet_bot/domains/workspaces/product_service.py`<br>`velvet_bot/core/access/policy.py` | `tests/test_workspace_product_access.py`<br>`tests/test_workspace_member_dashboard.py` | — |
| WSP-07 | 7 | Справка по модулям | `verified` | `velvet_bot/workspace_ui.py` | `tests/test_workspace_product_access.py`<br>`tests/test_workspace_guided_menu.py` | — |
| WSP-08 | 8 | Собственные категории | `verified` | `migrations/903_workspace_product_access.sql`<br>`velvet_bot/domains/workspaces/product_service.py` | `tests/test_workspace_product_access.py`<br>`tests/test_workspace_taxonomy_catalog.py` | — |
| WSP-09 | 9 | Собственные вселенные | `verified` | `migrations/903_workspace_product_access.sql`<br>`velvet_bot/domains/workspaces/product_service.py` | `tests/test_workspace_product_access.py`<br>`tests/test_workspace_character_inline_pickers.py` | — |
| WSP-10 | 10 | Собственные истории | `verified` | `migrations/903_workspace_product_access.sql`<br>`velvet_bot/domains/workspaces/character_management.py` | `tests/test_workspace_taxonomy_catalog.py`<br>`tests/test_workspace_character_inline_pickers.py` | — |
| WSP-11 | 11 | Шаблон вселенной КР | `verified` | `velvet_bot/domains/workspaces/product_service.py` | `tests/test_workspace_product_access.py` | — |
| WSP-12 | 12 | Управление пространством и onboarding | `verified_with_follow_up` | `velvet_bot/presentation/telegram/routers/workspace_onboarding.py`<br>`velvet_bot/presentation/telegram/routers/workspace_guided_actions.py` | `tests/test_workspace_onboarding.py`<br>`tests/test_workspace_onboarding_channel_bind.py`<br>`tests/test_workspace_guided_menu.py` | #410, #561 |
| WSP-13 | 13 | Роли и командный доступ | `verified_with_follow_up` | `velvet_bot/domains/workspaces/team_service.py`<br>`velvet_bot/presentation/telegram/routers/workspace_member_home.py` | `tests/test_workspace_team_watermark.py`<br>`tests/test_workspace_member_dashboard.py` | #410, #562 |
| WSP-14 | 14 | Текущий технический срез | `verified` | `docs/worklog/2026-07-21-workspace-access-start-modules-taxonomy.md`<br>`docs/worklog/2026-07-22-workspace-first-run-wizard.md` | `tests/test_workspace_product_access.py`<br>`tests/test_workspace_taxonomy_catalog.py` | — |
| WSP-15 | 15 | Workspace wiring старых экранов | `verified_with_follow_up` | `velvet_bot/presentation/telegram/routers/workspace_character_pickers.py`<br>`velvet_bot/domains/publication/validation_repository.py`<br>`velvet_bot/domains/workspaces/analytics_queries.py` | `tests/test_workspace_character_inline_pickers.py`<br>`tests/test_workspace_reference_library.py`<br>`tests/test_workspace_publication_queues.py`<br>`tests/test_workspace_analytics.py` | #417, #563 |
| WSP-16 | 16 | Медиа и скачивание | `verified_with_follow_up` | `velvet_bot/presentation/telegram/routers/workspace_owner_controls.py`<br>`velvet_bot/domains/public_archive/repository.py` | `tests/test_workspace_media_controls.py` | #426 |
| OPS-01 | ops | Живая приемка обязательного workspace пути | `live_follow_up` | `docs/worklog/2026-07-22-workspace-first-run-wizard.md`<br>`docs/worklog/2026-07-22-workspace-member-dashboard.md` | live | #410, #561, #562 |

## Вывод

Канонический workspace foundation и перечисленное в разделах 1–16 поведение присутствуют в текущем коде и regression suite. Старый раздел «Следующий этап» больше не является актуальным backlog: character taxonomy, references, publications, analytics и team routes уже workspace-scoped.

Оставшиеся действия разделены по типу, чтобы человеческая склонность называть всё одним словом «не готово» не испортила план:

- `#561` — live owner/onboarding/destinations smoke, bounded slice `#410`;
- `#562` — live role matrix и tenant callback isolation, bounded slice `#410`;
- `#563` — provider-neutral personal quality, bounded code slice `#417`;
- `#426` — video/animation subscriber notifications, существующий отдельный extension issue.

Эти follow-up не отменяют подтвержденные core contracts и не закрываются зелёным CI автоматически.
