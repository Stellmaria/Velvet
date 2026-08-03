# Codex GPT-5.6 для Hermes coder

Этот слой передаёт задачи Каэля двум изолированным coder runtime:

```text
Каэль
  -> coderctl.py
    -> hermes-coder-router
      -> hermes-coder-velvet  (Stellmaria/Velvet)
      -> hermes-coder-max     (Stellmaria/romatic_club_bot_max)
```

Codex runners не получают production Docker socket, systemd, production checkout, production `.env` или прямой доступ к production PostgreSQL networks. Каждый проект имеет отдельные workspace, `CODEX_HOME`, Runs API key, journal и GitHub token.

## Канонический routing contract

Каэль до делегирования явно определяет:

- `project`;
- `task_type`;
- `complexity`;
- `risk`;
- `mutation_policy`;
- `requested_tier`.

Значения передаются через `coderctl -> tier_router -> coder runner` без повторной классификации после fallback.

### Codex subscription

| Tier | Primary model | Допустимое infrastructure-only повышение |
|---|---|---|
| `small` | `gpt-5.6-luna` | Terra, затем Sol |
| `standard` | `gpt-5.6-terra` | Sol |
| `complex` | `gpt-5.6-sol` | нет |
| `high_risk` | `gpt-5.6-sol` | нет |

`Terra -> Luna` запрещён. Модель нельзя выбрать ниже модели, требуемой tier.

### Byesu provider route

| Tier/task type | Route |
|---|---|
| `small` general/read-only/docs | Luna, затем Terra только при capacity |
| `small` code | Mini, затем Terra только при capacity |
| `standard` | Terra |
| `complex` / `high_risk` | Terra как degraded route |

Для complex/high-risk Terra может только подготовить изменения, тесты и один PR в изолированном workspace. Ledger отмечает `review_required=true` и `degraded_provider_route=true`. Live production mutation запрещена.

`CODEX_PROVIDER_FALLBACK_MODELS` является каталогом моделей, а не общей цепочкой. Если production key не имеет доступа к Mini, permanent model-access error завершает small-code run fail-closed. Автоматическое продолжение на Terra допускается только для classified capacity failure.

## Политика повторов

Автоматическая смена модели разрешена только для классифицированных infrastructure failures:

- capacity / temporary unavailable;
- subscription auth;
- subscription quota.

Auth или quota блокирует всю credential group. Обычная ошибка задачи, теста или кода не запускает следующую модель.

После любого из событий автоматический повтор другой моделью запрещён:

- Git/file mutation;
- command execution;
- MCP/collaboration/dynamic tool call;
- иной execution event.

## Runs API и ledger

Tier-aware `POST /v1/runs` принимает:

```json
{
  "input": "...",
  "session_id": "...",
  "task_type": "code",
  "complexity": "standard",
  "risk": "medium",
  "mutation_policy": "workspace_write",
  "requested_tier": "standard"
}
```

Runner и orchestration ledger сохраняют:

- `task_type`;
- `requested_tier`;
- `risk`;
- `selected_primary_model`;
- `selected_provider_route`;
- `attempted_models`;
- `attempted_routes`;
- `actual_route`;
- `fallback_reason`;
- `mutation_started`.

`GET /v1/capabilities` публикует безопасную `routes_by_tier`. Имена env keys, tokens и secret values не публикуются.

## Граница прав моделей

Любая модель, включая Sol, может только:

- работать в изолированном workspace;
- читать и менять файлы репозитория;
- запускать тесты и static checks;
- создать ветку, commit, push и один PR.

Ни одна модель не может самостоятельно:

- merge;
- изменить production checkout;
- выполнить deploy, restart или rollback;
- использовать Docker socket или systemd;
- читать production `.env`.

## Подготовка и авторизация

После merge и обновления production checkout:

```bash
cd /srv/velvet
sudo bash deploy/hermes-coders/install-codex.sh
sudo bash deploy/hermes-coders/codex-login.sh velvet
sudo bash deploy/hermes-coders/codex-login.sh max
```

`auth.json` каждого проекта хранится отдельно с режимом `0600`. Его нельзя печатать, копировать в репозиторий или передавать между проектами.

## Controlled rollout

Rollout выполняется только на точный approved SHA после backup и с готовым rollback:

```bash
cd /srv/velvet
sudo env HERMES_CODERS_ROOT=/srv/hermes-coders \
  python3 deploy/hermes-coders/preflight.py

sudo systemctl restart hermes-coders.service
sudo systemctl restart hermes-coder-router.service

sudo env HERMES_CODERS_ROOT=/srv/hermes-coders \
  python3 deploy/hermes-coders/runtime_smoke.py
sudo env HERMES_CODERS_ROOT=/srv/hermes-coders \
  python3 deploy/hermes-coders/tier_provider_smoke.py
sudo env HERMES_CODERS_ROOT=/srv/hermes-coders \
  python3 deploy/hermes-coders/router_smoke.py
```

Дополнительно из основного Hermes:

```bash
python /opt/data/tools/coderctl.py health all
```

Read-only Telegram handoff должен показывать `requested_tier`, `selected_primary_model`, `actual_route` и отсутствие production privileges.

## Откат

Остановить coder backend без удаления данных:

```bash
cd /srv/velvet/deploy/hermes-coders
HERMES_CODERS_ROOT=/srv/hermes-coders \
  docker compose --profile velvet --profile max -f compose.yaml stop \
  hermes-coder-velvet hermes-coder-max
```

Затем вернуть production checkout к сохранённому approved SHA и повторить штатный installer. Каталоги `codex`, `codex-runs` и `workspaces/*-codex` до подтверждённого rollback не удалять.
