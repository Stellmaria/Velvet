# Issue #593: fail-closed coder delegation для Каэля

- Дата: 2026-08-04
- ID: `issue-593-2026-08-04`
- Линия/фаза: hotfix/эксплуатационная надёжность вне продуктовых фаз
- Статус: `частично`
- Ветка: `fix/593-fail-closed-kael-coder-delegation`
- Базовый commit: `e2eef3ec61147259ead1848cb7d6f21834d3ce66`

## Перед началом

### Цель

Закрыть подтверждённый обход central coder router основным Hermes-агентом Каэлем. Новая coder-задача должна запускаться только через typed tool и `coderctl.py`, а локальный fallback через `terminal`, `search_files`, code execution, Git, GitHub или `/opt/data/workspace/*` должен блокироваться до исполнения.

### Исходный контекст

После rollout PR #591 router, tier selection, isolated per-run workspace и terminal ledger работали для прямых canary Velvet и Max. Telegram-запрос к Каэлю ранее выполнился локально в main Hermes и не создал POST в router. Runtime inventory подтвердил:

- Hermes Agent `0.19.0`, image digest `sha256:f7b35053268f532f98955195c909f15a230470fbcbdacaa9fdecb95707dad04a`;
- user plugins из `$HERMES_HOME/plugins`;
- typed tool registration через `PluginContext.register_tool()`;
- блокирующий `pre_tool_call` в sequential и concurrent executor до реального вызова;
- основной Hermes имеет local terminal и writable `/opt/data`;
- `coderctl.py` уже использует strict enums, project allowlist и fail-closed router transport.

Дополнительная проверка закреплённого upstream выявила два существенных свойства:

- Telegram строит surface из статического toolset `hermes-telegram`; plugin tool из отдельного standalone toolset загрузился бы, но остался невидимым модели;
- registry добавляет plugin tools в platform surface, когда они зарегистрированы в том же `hermes-telegram` toolset.

### Улучшаемая существующая функция

Улучшается существующая функция Каэля как единого server control plane и координатора Velvet/Max coder-агентов. Изменение не добавляет новую предметную область.

### Планируемый объём

1. User plugin `kael-coder-control` с typed `coder_delegate`.
2. Strict schema для project/task type/complexity/risk/mutation policy/tier/task.
3. Adapter к `/opt/data/tools/coderctl.py` через argv и `shell=False`.
4. `pre_tool_call` policy, сохраняющая controller-команды и non-coder delegation, но блокирующая coder bypass.
5. Immutable boundary для controllers, plugin, config, identity, hooks, ledger, audit и process secrets.
6. JSONL audit без текста задачи и secrets.
7. Идемпотентная установка plugin и включение в runtime config.
8. Контрактные и unit-тесты.
9. После merge отдельный production reconcile и Telegram smoke.

### Критерии готовности

- invalid fields отклоняются до subprocess/router;
- router unavailable возвращает явную ошибку без local fallback;
- `coderctl.py submit` через terminal блокируется;
- `monitorctl.py`, `opsctl.py`, `reconcilectl.py`, `runctl.py` и non-submit coderctl operations остаются доступны;
- `delegate_task` для Квин и других non-coder агентов не блокируется;
- `coder_delegate` реально входит в Telegram tool surface;
- local repository/search/Git/GitHub/code tools блокируются и аудируются;
- model file tools не могут читать или менять config, identity, credentials, controllers, plugins, hooks, ledger, audit, process state и `/proc/*/environ`;
- plugin устанавливается с приватными правами и сохраняет существующие enabled plugins;
- CI проходит;
- live Telegram canary создаёт router POST и canonical ledger metadata.

### Риски и ограничения

- plugin API привязан к закреплённому Hermes Agent `0.19.0`; image digest остаётся обязательной частью rollout contract;
- слишком широкая terminal policy могла бы лишить Каэля server control, поэтому разрешены только существующие узкие controllers и их allowlisted actions;
- `process` сам не запускает команды, а управляет только процессами, ранее созданными через terminal; произвольный terminal блокируется, а rollout перезапускает основной Hermes;
- код и CI не означают production rollout;
- nested bwrap issue #594 не входит в этот срез;
- production restart/reconcile выполняется только после merge и отдельного разрешения.

## После завершения

### Фактически сделано

- добавлен user plugin `kael-coder-control`;
- зарегистрирован typed tool `coder_delegate` в активном `hermes-telegram` toolset;
- handler вызывает фиксированный `/opt/data/tools/coderctl.py submit` через список argv, `shell=False`, bounded timeout и explicit error response;
- canonical response всегда содержит `requested_tier`, `selected_primary_model`, `actual_route`, `attempted_routes`, `mutation_started`, `production_privileges=false`;
- добавлены audit events classification, delegate invocation, router submit/result, rejected local tool и terminal failure;
- audit использует append-only open с `O_NOFOLLOW` и mode `0600`, не сохраняя текст задачи;
- local terminal ограничен существующими controller scripts и allowlisted actions, а `coderctl.py submit` через terminal запрещён;
- `search_files`, general code execution, direct Git/GitHub tools и coder workspace paths блокируются;
- direct и symlink-resolved file access к config, `AGENTS.md`, `SOUL.md`, context manifest, credentials, tools, plugins, hooks, orchestration ledger, audit, process checkpoint, `/proc`, `/run/secrets` и SSH secrets блокируется;
- non-coder `delegate_task` сохраняется;
- runtime config patcher идемпотентно добавляет `kael-coder-control` в `plugins.enabled`, не удаляя другие plugins;
- operator installer и entities reconcile устанавливают plugin и audit directory с ограниченными правами;
- AGENTS Каэля переведён с terminal submit на typed `coder_delegate`;
- открыт draft PR #596.

### Изменённые контракты

- `deploy/hermes-operator/plugins/kael-coder-control/*`;
- `deploy/hermes-coders/ensure_runtime_config.py`;
- `deploy/hermes-entities/reconcile.sh`;
- `deploy/hermes-operator/install.sh`;
- `deploy/hermes-operator/AGENTS.kael.md`;
- Hermes runtime `plugins.enabled` для profile `kael`.

### Миграции и совместимость

Миграций БД нет. Plugin использует официальный user-plugin seam Hermes Agent `0.19.0`. Coder router, coder containers, Queen/non-coder delegation и existing controller APIs не меняются.

### Проверки

На production checkout до переноса в GitHub выполнено:

```text
python3 -m py_compile deploy/hermes-operator/plugins/kael-coder-control/__init__.py tests/test_hermes_kael_coder_control.py
python3 -m unittest tests.test_hermes_kael_coder_control -v
Ran 13 tests ... OK
```

В PR добавлены дополнительные проверки:

- Telegram toolset exposure;
- strict typed schema и invalid fields;
- explicit router failure без fallback;
- controller action/project/target allowlist;
- blocked terminal/search/code/Git/GitHub/workspace access;
- immutable control plane, identity и process secret paths;
- symlink-resistant audit target;
- preserved Queen/non-coder delegation;
- runtime-config idempotency и сохранение existing plugins;
- operator/entities installation и shell syntax.

Полный CI PR #596 перезапускается на финальном head после hardening цикла.

### PR и commit

PR: #596 `Fail-closed Kael coder delegation`.

Commit: текущий head feature branch; итоговый SHA фиксируется после зелёного CI.

### Незавершённое

- финальный CI ещё не завершён;
- production plugin не установлен;
- Telegram read-only Velvet/Max smoke, router POST и terminal ledger не проверены;
- rollback smoke не выполнен.

### Следующий шаг

Дождаться полного зелёного CI PR #596 и провести итоговый review. PR остаётся draft. После отдельного разрешения на ready/merge и после merge выполнить только entities/operator reconcile для основного Hermes, пересоздать только `velvet-hermes-1` при необходимости и провести fail-closed Telegram canary без mutation.
