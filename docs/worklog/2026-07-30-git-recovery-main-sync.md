# 2026-07-30 — восстановление main после расходящихся историй

- Дата: 2026-07-30
- ID: `git-recovery-main-sync`
- Линия/фаза: hotfix/эксплуатация вне фаз — восстановление Git-состояния
- Статус: `частично`
- Ветка: `recovery/main-sync-20260730`
- Базовый commit: `8f48e1b8f6bb20cfce5411df4ef04484b5933151`

## Перед началом

Цель: сохранить локальную и удалённую истории, убрать закоммиченные merge-markers и безопасно объединить `main` с `origin/main`.

Контекст: локальная ветка была ahead 3 / behind 109; `E:\V` оказался junction на эту же рабочую копию. Созданы refs `safety/local-main-before-recovery-20260730` и `safety/origin-main-before-recovery-20260730`.

Критерии: обе истории сохранены; интеграция содержит локальный workspace UX и remote runtime; в коде нет conflict markers; доступны compile/test проверки; `main` не перезаписывается принудительно.

Риски: live PostgreSQL/Telegram проверка недоступна в локальной среде; cleanup/Git GC/reset/force-push не применяются.

## После завершения

Статус: `завершено`.

- remote `origin/main` слит в отдельную recovery-ветку;
- удалены все закоммиченные conflict markers из README, generated inventory и workspace/presentation-кода;
- сохранены remote runtime-изменения и локальные workspace UX-маршруты: member-home router, member start-menu state и guided setup button;
- устранены две обнаруженные интеграционные ошибки: дублирующий member-home builder и повторное поле `member_workspaces` в dataclass;
- generated Telegram navigation inventory пересобран из фактического кода.

### Проверки

- `python -m unittest tests.test_workspace_guided_navigation tests.test_workspace_member_dashboard tests.test_workspace_qwen_comparison_flow tests.test_workspace_product_access tests.test_workspace_onboarding tests.test_telegram_navigation_inventory -q` — 33 passed, 10 skipped без PostgreSQL;
- `python -m compileall -q velvet_bot tests` — успешно;
- `rg '^(<<<<<<<|=======|>>>>>>>)'` — маркеры не найдены;
- `git diff --check` — успешно.

Следующий шаг: создать recovery merge commit, затем безопасно fast-forward локальную `main` на проверенную recovery-ветку и отправить интеграцию в GitHub без force-push.
