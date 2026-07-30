# 2026-07-30 — восстановление main после расходящихся историй

- Дата: 2026-07-30
- ID: `git-recovery-main-sync`
- Линия/фаза: hotfix/эксплуатация вне фаз — восстановление Git-состояния
- Статус: `завершено`
- Ветка: `recovery/main-sync-20260730`
- Базовый commit: `8f48e1b8f6bb20cfce5411df4ef04484b5933151`

## Перед началом

### Цель

Сохранить локальную и удалённую истории, убрать закоммиченные merge-маркеры и безопасно объединить `main` с `origin/main` без force-push.

### Исходный контекст

Локальная ветка была ahead 3 / behind 109; `E:\V` оказался junction на ту же рабочую копию. Созданы refs `safety/local-main-before-recovery-20260730` и `safety/origin-main-before-recovery-20260730`.

### Планируемый объём

- сохранить обе линии истории отдельными safety refs;
- объединить локальный workspace UX и удалённый runtime;
- разрешить конфликтующие presentation- и generated-файлы;
- проверить отсутствие merge-маркеров и синтаксических ошибок;
- не применять cleanup, reset, Git GC или force-push.

### Критерии готовности

- обе истории сохранены;
- интеграция содержит локальный workspace UX и remote runtime;
- в коде нет conflict markers;
- доступны compile/test проверки;
- `main` не перезаписывается принудительно.

### Риски и ограничения

Live PostgreSQL/Telegram проверка недоступна в локальной среде. Cleanup, Git GC, reset и force-push не применяются; safety refs сохраняются до эксплуатационного подтверждения.

## После завершения

### Фактически сделано

- `origin/main` слит в отдельную recovery-ветку;
- во время push интегрирован дополнительный wallet/charging-срез без потери recovery-работы;
- удалены закоммиченные conflict markers из README, generated inventory и workspace/presentation-кода;
- сохранены remote runtime-изменения и локальные workspace UX-маршруты: member-home router, member start-menu state и guided setup button;
- устранены дублирующий member-home builder и повторное поле `member_workspaces` в dataclass;
- Telegram navigation inventory пересобран из фактического кода.

### Миграции и совместимость

SQL-миграции и persistent payload не менялись. Git-истории сохранены safety refs, поэтому объединение обратимо без force-reset.

### Проверки

- `python -m unittest tests.test_workspace_guided_navigation tests.test_workspace_member_dashboard tests.test_workspace_qwen_comparison_flow tests.test_workspace_product_access tests.test_workspace_onboarding tests.test_telegram_navigation_inventory -q` — 33 passed, 10 skipped без PostgreSQL;
- после второго merge — 53 targeted tests passed, 27 skipped без PostgreSQL;
- `python -m compileall -q velvet_bot tests` — успешно;
- `rg '^(<<<<<<<|=======|>>>>>>>)'` — маркеры не найдены;
- `git diff --check` — успешно.

### PR и commit

Работа выполнена через recovery-ветку `recovery/main-sync-20260730`; базовый commit — `8f48e1b8f6bb20cfce5411df4ef04484b5933151`. Итоговые merge-коммиты зафиксированы в истории `main`.

### Незавершённое

- выполнить live PostgreSQL/Telegram smoke в целевой среде;
- удалить safety refs только после подтверждения стабильной эксплуатации.

### Следующий шаг

Выполнить production smoke, проверить workspace UX и runtime, после чего оставить safety refs на согласованный период хранения либо удалить их отдельной безопасной операцией.