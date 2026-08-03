# Сессия: tier-aware маршрутизация моделей Каэля и coder-агентов

- Дата: 2026-08-03
- ID: 2026-08-03-tier-aware-hermes-model-routing
- Линия/фаза: Hermes coder orchestration / model routing
- Статус: частично
- Ветка: fix/tier-aware-hermes-model-routing
- Базовый commit: ef5fc03c03b110652ce2ea79b12a37b2d0b9b3db

## Перед началом

### Цель

Закрепить для Каэля и изолированных coder-агентов явную маршрутизацию по типу задачи, сложности и риску. Сохранить Codex subscription первым маршрутом, использовать Byesu только как fail-closed fallback и запретить бессмысленное расходование дорогих моделей или downgrade ниже выбранного tier.

### Исходный контекст

Production rollout PR #574/#575 восстановил Codex-first runtime, Byesu credentials, router lifecycle и server smoke. При этом provider runner применял одну общую последовательность `gpt-5.4-mini -> gpt-5.6-terra -> gpt-5.6-luna` к любой задаче.

Это приводило к четырём проблемам:

- standard и complex задачи начинались с Mini;
- после Terra был возможен downgrade на Luna;
- выбранная сложность не сохранялась явно в run ledger;
- Каэль и router не передавали `task_type`, `requested_tier`, `risk`, `mutation_policy`.

Read-only `/v1/models` probe production Byesu-ключами подтвердил одинаково для Velvet и Max: coder credential видит Terra, GPT Pro credential видит Luna, Sol не видна. Доступность Mini требуется подтвердить отдельным live probe перед rollout.

### Планируемый объём

- ввести tiers `small`, `standard`, `complex`, `high_risk`;
- разделить `task_type`, `requested_tier`, `risk` и `mutation_policy`;
- передавать выбранную политику через `coderctl -> coder-router -> Runs API`;
- построить primary/provider routes по tier;
- запретить under-tier запросы и downgrade `Terra -> Luna`;
- сохранить selected/attempted/actual routes и degradation в ledger;
- обновить capabilities, smoke, tests, SOUL, AGENTS, skills и README;
- не менять production до полного CI, отдельного разрешения владельца и controlled rollout.

### Критерии готовности

- small, standard, complex и high_risk получают предсказуемые primary routes;
- provider fallback зависит от tier и task type;
- standard provider route использует только Terra;
- complex/high_risk fallback на Terra помечается `degraded_execution=true` и `review_required=true`;
- mutation или tool execution блокируют автоматический retry;
- ни одна модель не получает live production privileges;
- одинаковые contracts и tests действуют для Velvet и Max;
- полный required CI проходит на актуальном main.

### Риски и ограничения

- Sol недоступна production Byesu token groups, поэтому complex/high_risk provider fallback не равен primary Sol по мощности;
- Mini ещё не подтверждена отдельным production probe;
- эвристика по тексту остаётся compatibility path, канонический orchestration обязан передавать structured metadata явно;
- merge, deployment, restart, rollback и production update не входят в этот PR и требуют отдельного разрешения;
- при любом failed smoke controlled rollout обязан выполнить rollback.

## После завершения

### Фактически сделано

Каноническая primary policy:

```text
small      -> Luna -> Terra только при capacity
standard   -> Terra
complex    -> Sol -> Terra как degraded route
high_risk  -> Sol -> Terra как degraded route
```

Каноническая Byesu policy:

```text
small general/read-only -> Luna -> Terra
small code              -> Mini -> Terra
standard                 -> Terra
complex/high_risk        -> Terra, degraded=true, review_required=true
```

В `codex_routed_runner.py` добавлена структурированная `TaskClassification`. Explicit metadata имеет приоритет над эвристиками; under-tier комбинации task type, risk, tier и model отклоняются. `read_only` отделён от сложности, но task type `read_only` не может получить workspace mutation.

В `codex_provider_chain_runner.py` provider catalog отделён от route order. Primary и provider routes строятся по tier/task type; ledger сохраняет task type, tier, risk, mutation policy, selected primary/provider routes, attempted routes, actual route, degradation и review requirement. Mutation/tool execution по-прежнему блокируют automatic retry.

В `coder_router.py` добавлены фиксированные routing fields, schema-bound handoff и forwarding metadata в Runs API. В `coderctl.py` добавлены `--task-type`, `--tier`, `--risk`, `--mutation-policy`; conservative defaults равны `code/standard/medium/workspace_pr`.

В `codex_delegate.py` direct Telegram coder path принимает те же routing fields и возвращает безопасный публичный отчёт без secrets.

SOUL, AGENTS, brain-vault skills и orchestration README закрепляют модельную политику и границу прав: Mini, Luna, Terra и Sol могут менять код только в isolated workspace, запускать тесты, создавать branch/commit/push/PR. Ни одна модель не может самостоятельно делать merge, deploy, restart, rollback, менять production checkout, использовать Docker socket/systemd или читать production secrets.

### Миграции и совместимость

Изменения базы данных отсутствуют. Runs API расширен optional routing fields; старые клиенты получают conservative standard route. Existing project isolation, token separation, read-only DB proxies и fail-closed mutation guard сохраняются.

Production runtime этим PR не изменяется. После merge потребуется controlled update coder/router runtime и entity reconcile Каэля.

### Проверки

Локально до публикации:

- Python compile изменённых runner/router/coderctl/smoke: PASS;
- focused provider routing tests: 12 PASS;
- focused router/coderctl tests: 16 PASS;
- under-tier и model/tier mismatch rejection: PASS;
- small code capacity route `Mini -> Terra`, без Luna: PASS;
- standard/complex provider route Terra only: PASS;
- credential-group auth skip: PASS;
- capabilities secret boundary: PASS;
- live production mutation flags: false.

GitHub CI на актуальном head запущен. Project notes contract первоначально выявил неправильный формат worklog; файл приведён к обязательному шаблону этой правкой.

### PR и commit

- Issue: #576;
- PR: #577 `Закрепить tier-aware маршрутизацию моделей Каэля и coder-агентов`;
- ветка: `fix/tier-aware-hermes-model-routing`;
- актуальная база PR: `d18ac30325ce4e435510135e6eecafdc82a594e8`;
- production SHA до merge: `ef5fc03c03b110652ce2ea79b12a37b2d0b9b3db`.

### Незавершённое

- дождаться полного tests/type/Docker/security/branch-protection CI;
- исправить обнаруженные CI failures, если они появятся;
- подтвердить Mini отдельным read-only production `/v1/models` probe;
- после полного зелёного CI получить отдельное разрешение владельца на merge;
- после merge подготовить backup и controlled rollout;
- выполнить runtime, tier-aware provider, router, coderctl и Telegram smoke;
- обновить QA runbook фактическим rollout SHA и результатами.

### Следующий шаг

Повторно запустить required CI на исправленном worklog, устранить все failures и не менять production до полного зелёного набора проверок и отдельного controlled rollout.
