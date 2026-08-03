# Tier-aware маршрутизация моделей Каэля и coder-агентов

Дата: 2026-08-03
Issue: #576
Base production SHA: `ef5fc03c03b110652ce2ea79b12a37b2d0b9b3db`

## Причина

Production rollout PR #574/#575 технически восстановил Codex-first runtime, Byesu credentials, router lifecycle и smoke. Но provider runner использовал одну общую последовательность:

```text
gpt-5.4-mini -> gpt-5.6-terra -> gpt-5.6-luna
```

для любой задачи. Это нарушало целевую политику стоимости и качества:

- `standard` и `complex` начинались с Mini;
- после Terra был возможен downgrade на Luna;
- выбранная сложность не сохранялась явно в run ledger;
- Каэль и router не передавали `task_type`, `requested_tier`, `risk`, `mutation_policy`;
- capabilities не показывали routes по tier.

Фактический read-only `/v1/models` probe production Byesu-ключами показал одинаково для Velvet и Max:

- coder key видит `gpt-5.6-terra`;
- GPT Pro key видит `gpt-5.6-luna`;
- `gpt-5.6-sol` не видна;
- Mini остаётся первым дешёвым coder route и при model-unavailable/capacity может перейти на Terra.

## Каноническая политика

### Primary Codex subscription

```text
small      -> Luna -> Terra только при capacity
standard   -> Terra
complex    -> Sol -> Terra как degraded route
high_risk  -> Sol -> Terra как degraded route
```

### Byesu

```text
small general/read-only -> Luna -> Terra
small code              -> Mini -> Terra
standard                 -> Terra
complex/high_risk        -> Terra, degraded=true, review_required=true
```

Provider route не имеет права понижать `Terra -> Luna` после выбора standard/complex tier.

### Граница прав

Любая модель может:

- читать и менять файлы только в isolated `/workspace`;
- создать одну ветку;
- запустить тесты;
- сделать commit/push;
- открыть один PR.

Никакая модель, включая Sol, не может:

- merge;
- менять production checkout;
- делать deploy/restart/rollback;
- обращаться к Docker socket или systemd;
- читать production `.env` и secrets.

Terra может менять production-код в ветке и PR. Запрет относится к live production, а не к исходному коду.

## Реализация

- `codex_routed_runner.py`
  - введена структурированная `TaskClassification`;
  - explicit metadata имеет приоритет над эвристиками;
  - поддержаны tiers `small`, `standard`, `complex`, `high_risk`;
  - under-tier комбинации task type/risk/model отклоняются;
  - `read_only` отделён от сложности: high-risk review может быть read-only,
    но task type `read_only` не может получить workspace mutation;
  - capabilities публикуют tier mapping и запрет live mutation.

- `codex_provider_chain_runner.py`
  - provider catalog отделён от route order;
  - primary и provider routes строятся по tier/task type;
  - run ledger сохраняет task type, tier, risk, mutation policy, selected primary/provider routes, actual route, degradation и review requirement;
  - standard provider route использует только Terra;
  - complex/high-risk provider route использует Terra как degraded isolated-workspace path;
  - mutation/tool execution по-прежнему блокируют automatic retry;
  - read-only run, изменивший workspace, отклоняется;
  - capabilities безопасно публикуют `routes_by_tier` без env key и secret values.

- `coder_router.py`
  - принимает только фиксированные routing fields;
  - сохраняет metadata в schema-bound handoff;
  - передаёт metadata в Runs API;
  - старые клиенты получают conservative fallback, неизвестный code default идёт на standard.

- `coderctl.py`
  - добавлены `--task-type`, `--tier`, `--risk`, `--mutation-policy`;
  - defaults: `code/standard/medium/workspace_pr`;
  - under-tier запрос отклоняется до вызова router;
  - metadata и фактические routes сохраняются в orchestration ledger.

- `codex_delegate.py`
  - direct Telegram coder path принимает те же optional routing fields;
  - публичный отчёт показывает tier, selected/actual routes, degradation и
    safety flags без secrets.

- SOUL/AGENTS/README
  - закреплены права моделей и запрет самостоятельного live rollout;
  - закреплена обязанность Каэля выбирать tier до делегирования;
  - coder-контракты запрещают повторную классификацию и downgrade после handoff.

## Проверки

Локально до публикации:

- Python compile изменённых runner/router/coderctl/smoke: PASS;
- focused provider routing unit tests: PASS;
- focused router/coderctl/ledger tests: PASS;
- under-tier и model/tier mismatch rejection: PASS;
- small code capacity: Mini -> Terra, без Luna;
- standard/complex provider: Terra only;
- credential-group auth skip: PASS;
- capabilities secret boundary: PASS;
- live production mutation flags: false.

GitHub CI должен дополнительно выполнить полный test, type, Docker и security workflows.

## Rollout

Production не менять до:

1. merge approved PR на точный SHA;
2. зелёного полного CI;
3. backup runtime/systemd;
4. controlled fast-forward rollout;
5. `runtime_smoke.py`;
6. tier-aware `provider_chain_smoke.py`;
7. `router_smoke.py`;
8. `coderctl.py health all`;
9. read-only Telegram handoff с проверкой `requested_tier`, `selected_primary_route`, `selected_provider_route`, `actual_route`;
10. отдельного controlled fallback smoke без Git/file mutation.

Rollback возвращает предыдущий SHA и согласованный backup runtime/systemd.
