# Сессия: tier-aware маршрутизация Каэля и coder-агентов

- Дата: 2026-08-03
- ID: 2026-08-03-tier-aware-hermes-model-routing
- Линия/фаза: Hermes orchestration / coder runtime
- Статус: частично
- Issue: #576
- Ветка: `fix/issue-576-tier-aware-routing`
- Базовый commit: `d18ac30325ce4e435510135e6eecafdc82a594e8`

## Перед началом

### Цель

Заменить одну общую provider chain на устойчивую tier-aware политику, в которой Каэль отдельно выбирает тип задачи, сложность, риск, mutation policy и tier, а coder runtime сохраняет выбор до terminal result без автоматического downgrade.

### Исходный контекст

Production coder runtime, router, capabilities и health checks работали, но provider fallback перебирал общий порядок `Mini -> Terra -> Luna` для любой задачи. Выбранный первичным Codex route уровень сложности не сохранялся через orchestration. Это допускало недопустимый `Terra -> Luna` downgrade и не давало ledger полного объяснения фактического route.

На момент начала подтверждены:

- Byesu coder credential group имеет доступ к Terra;
- Byesu GPT Pro credential group имеет доступ к Luna;
- Sol недоступна provider keys и должна использоваться через Codex subscription;
- доступность Mini должна проверяться production smoke либо завершаться fail-closed.

### Планируемый объём

- ввести tiers `small`, `standard`, `complex`, `high_risk`;
- разделить `task_type`, `complexity`, `risk` и `mutation_policy`;
- передавать routing metadata через `coderctl -> tier router -> coder runner`;
- строить Codex и provider routes по immutable requested tier;
- запретить downgrade и cross-model retry после mutation/execution events;
- блокировать credential group при auth/quota;
- расширить run и orchestration ledger;
- публиковать безопасную `routes_by_tier`;
- синхронизировать Velvet и Max;
- обновить SOUL, CODEX/README, smokes и contract tests.

### Критерии готовности

- small general/read-only/docs выбирает Codex Luna и provider Luna;
- small code выбирает Codex Luna и provider Mini, Terra только после capacity;
- standard code выбирает Codex Terra и provider Terra;
- complex/high-risk выбирает Codex Sol;
- Sol unavailable допускает только degraded Terra в isolated PR workflow;
- `Terra -> Luna` отсутствует;
- auth/quota блокирует credential group;
- mutation/tool execution блокирует automatic retry;
- capabilities и ledger не раскрывают secrets;
- Velvet и Max имеют одинаковую политику;
- полный CI и required checks проходят;
- production не изменяется до merge и отдельного controlled rollout.

### Риски и ограничения

- production availability Mini нельзя доказать unit test; её проверяет `tier_provider_smoke.py` без вывода ключа;
- если Mini отсутствует, permanent model-access error обязан завершать run fail-closed;
- complex/high-risk provider Terra не эквивалентна Sol и требует `review_required=true`;
- изменение CLI intentionally требует явные routing flags и несовместимо со старым неявным submit;
- merge не является разрешением на production update, restart или reconcile.

## После завершения

### Фактически сделано

- добавлена schema-bound routing decision с отдельными task type, complexity, risk, mutation policy и requested tier;
- Codex routes закреплены как Luna / Terra / Sol по tier без downgrade;
- provider list превращён в каталог, из которого выбирается route по tier и task type;
- Mini model-access failure реализован fail-closed;
- capacity, auth и quota обрабатываются отдельно;
- retries после Git/file mutation и execution events запрещены;
- `coderctl.py`, tier router и Telegram delegate передают и сохраняют routing metadata;
- capabilities публикуют безопасную `routes_by_tier`;
- complex/high-risk Terra route помечается degraded и review-required;
- одинаковая runtime policy подключена для Velvet и Max;
- добавлены tier provider и router production smokes;
- обновлены SOUL Каэля, Velvet Coder, Max Coder и canonical документация.

### Миграции и совместимость

Database migrations отсутствуют. Изменение затрагивает Hermes orchestration API contract: `coderctl submit` теперь требует явные `--task-type`, `--complexity`, `--risk`, `--mutation-policy` и `--tier`. Legacy `provider_chain_smoke.py` сохранён как compatibility entrypoint к новому tier smoke.

### Проверки

Локальные contract tests добавлены для routing matrix, explicit directives, credential-group skip, capacity retry, no-downgrade, mutation/execution retry block, capabilities redaction, ledger persistence и Velvet/Max parity. Полный GitHub CI должен подтвердить syntax, typing, tests, Docker build, security и project notes на PR.

Production проверки после отдельного approved rollout:

- `runtime_smoke.py`;
- `tier_provider_smoke.py`;
- `router_smoke.py`;
- `coderctl.py health all`;
- read-only Telegram handoff с requested tier и actual route.

### PR и commit

- Issue: #576;
- ветка: `fix/issue-576-tier-aware-routing`;
- PR будет создан после завершения repository-side contract review;
- production SHA появится только после squash merge.

### Незавершённое

- открыть PR;
- дождаться полного required CI;
- исправить обнаруженные CI regression;
- выполнить независимую проверку diff;
- слить только полностью зелёный PR;
- controlled production rollout оставить отдельной разрешённой операцией.

### Следующий шаг

Открыть draft PR, получить полный CI, устранить failures и перевести PR в ready только после проверки всех acceptance contracts.
