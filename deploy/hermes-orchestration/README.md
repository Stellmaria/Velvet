# Hermes Coder Orchestration

Этот слой связывает Каэля с двумя изолированными coder-агентами:

- Velvet → `@velvet_private_coder_bot` → `Stellmaria/Velvet`;
- Max → `@romatic_max_coder_bot` → `Stellmaria/romatic_club_bot_max`.

Coder-агенты не получают Docker socket, systemd, production checkout, production `.env` или право управлять runtime.

## Архитектура

```text
Каэль
  └─ coderctl.py
      └─ tier_router.py:8878
          ├─ hermes-coder-velvet:8642
          └─ hermes-coder-max:8642
```

`coderctl.py` хранит ledger в `/opt/data/orchestration/tasks.json`. Router принимает только фиксированные проекты и schema-bound metadata. API coder-агентов доступен только во внутренней сети `hermes-agent-control`.

## Обязательная классификация до submit

Каэль обязан определить независимо друг от друга:

- `task_type`: `general`, `code`, `read_only`, `documentation`, `incident`;
- `complexity`: `small`, `standard`, `complex`;
- `risk`: `low`, `medium`, `high`, `critical`;
- `mutation_policy`: `read_only`, `workspace_write`, `isolated_pr_only`;
- `requested_tier`: `small`, `standard`, `complex`, `high_risk`.

Risk нельзя определять только длиной prompt или набором ключевых слов. Router валидирует согласованность, но не понижает и не переклассифицирует выбранный tier.

## Команды

Пример read-only small task:

```bash
python /opt/data/tools/coderctl.py submit velvet \
  --source owner-request \
  --task-type read_only \
  --complexity small \
  --risk low \
  --mutation-policy read_only \
  --tier small \
  --task "Проверь статус и подготовь краткую сводку без изменений"
```

Пример standard code task:

```bash
python /opt/data/tools/coderctl.py submit max \
  --source owner-request \
  --task-type code \
  --complexity standard \
  --risk medium \
  --mutation-policy workspace_write \
  --tier standard \
  --task "Исправь дефект, добавь regression test и открой PR"
```

Пример high-risk task:

```bash
python /opt/data/tools/coderctl.py submit velvet \
  --source owner-request \
  --task-type code \
  --complexity complex \
  --risk high \
  --mutation-policy isolated_pr_only \
  --tier high_risk \
  --task "Подготовь security migration только в изолированном workspace"
```

Контроль:

```bash
python /opt/data/tools/coderctl.py health all
python /opt/data/tools/coderctl.py status <task_id-or-run_id>
python /opt/data/tools/coderctl.py wait <task_id-or-run_id>
python /opt/data/tools/coderctl.py list --limit 20
python /opt/data/tools/coderctl.py stop <task_id-or-run_id>
python /opt/data/tools/coderctl.py pr velvet <pr-number>
python /opt/data/tools/coderctl.py pr max <pr-number>
```

## Ledger contract

Каждая запись сохраняет как минимум:

```text
task_type
requested_tier
risk
selected_primary_model
selected_provider_route
attempted_models
attempted_routes
actual_route
fallback_reason
mutation_started
```

Статус и wait обновляют эти поля из coder runner. Redaction скрывает token, secret, password, API key и Authorization values.

## Разрешённый цикл

1. Каэль получает запрос или очищенный incident.
2. Выполняет только необходимую read-only диагностику.
3. Выбирает project, task type, complexity, risk, mutation policy и tier.
4. `coderctl` сохраняет metadata и передаёт их в tier router.
5. Coder работает только в своём workspace, создаёт ветку, тесты и один PR.
6. Каэль ждёт terminal status и независимо проверяет ledger, diff, PR и CI.
7. Merge, production update, restart и rollback требуют отдельного явного разрешения владельца.

Для complex/high-risk Sol является primary model. Если Sol недоступна, provider Terra разрешена только как degraded isolated-PR route. Такой run обязан вернуть `review_required=true`; production privileges у него отсутствуют.

## Установка

До установки должны существовать отдельные coder secrets, operator credentials, internal network и production checkout на approved SHA.

```bash
cd /srv/velvet
sudo bash deploy/hermes-orchestration/install.sh
```

Installer:

1. подготавливает distinct credentials без печати значений;
2. устанавливает tier-aware `coderctl.py` и managed SOUL;
3. собирает coder и router images;
4. запускает preflight;
5. проверяет capabilities обоих проектов.

## Проверка после controlled rollout

```bash
cd /srv/velvet
sudo env HERMES_CODERS_ROOT=/srv/hermes-coders \
  python3 deploy/hermes-coders/runtime_smoke.py
sudo env HERMES_CODERS_ROOT=/srv/hermes-coders \
  python3 deploy/hermes-coders/tier_provider_smoke.py
sudo env HERMES_CODERS_ROOT=/srv/hermes-coders \
  python3 deploy/hermes-coders/router_smoke.py
```

Затем внутри основного Hermes:

```bash
python /opt/data/tools/coderctl.py health all
python /opt/data/tools/coderctl.py list --limit 5
```

Capabilities должны содержать безопасную `routes_by_tier` без env key names и secret values. Read-only Telegram handoff должен показывать requested tier и actual route.

## Автоматические инциденты

Incident watcher может автоматически передать только очищенную диагностику и подготовку PR. Для incident задаётся как минимум `task_type=incident`; при production/security поверхности используется `risk=high`, `mutation_policy=isolated_pr_only`, `requested_tier=high_risk`.

Автоматический merge или изменение production запрещены.

## Аварийная остановка

```bash
cd /srv/velvet/deploy/hermes-orchestration
HERMES_CODER_ROUTER_ENV_FILE=/srv/hermes-operator-control/coders.env \
  docker compose -f compose.yaml stop hermes-coder-router
```

Ledger, workspaces, coder data и secrets не удалять. `down -v` не использовать.
