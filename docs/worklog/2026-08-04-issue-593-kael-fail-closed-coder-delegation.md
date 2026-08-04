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

### Улучшаемая существующая функция

Улучшается существующая функция Каэля как единого server control plane и координатора Velvet/Max coder-агентов. Изменение не добавляет новую предметную область.

### Планируемый объём

1. User plugin `kael-coder-control` с typed `coder_delegate`.
2. Strict schema для project/task type/complexity/risk/mutation policy/tier/task.
3. Adapter к `/opt/data/tools/coderctl.py` через argv и `shell=False`.
4. `pre_tool_call` policy, сохраняющая controller-команды и non-coder delegation, но блокирующая coder bypass.
5. JSONL audit без текста задачи и secrets.
6. Идемпотентная установка plugin и включение в runtime config.
7. Контрактные и unit-тесты.
8. После merge отдельный production reconcile и Telegram smoke.

### Критерии готовности

- invalid fields отклоняются до subprocess/router;
- router unavailable возвращает явную ошибку без local fallback;
- `coderctl.py submit` через terminal блокируется;
- `monitorctl.py`, `opsctl.py`, `reconcilectl.py`, `runctl.py` и read-only coderctl operations остаются доступны;
- `delegate_task` для Квин и других non-coder агентов не блокируется;
- local repository/search/Git/GitHub/code tools блокируются и аудируются;
- plugin устанавливается с приватными правами и сохраняет существующие enabled plugins;
- CI проходит;
- live Telegram canary создаёт router POST и canonical ledger metadata.

### Риски и ограничения

- plugin API привязан к закреплённому Hermes Agent `0.19.0`; image digest остаётся обязательной частью rollout contract;
- слишком широкая terminal policy могла бы лишить Каэля server control, поэтому разрешены только существующие узкие controllers;
- код и CI не означают production rollout;
- nested bwrap issue #594 не входит в этот срез;
- production restart/reconcile выполняется только после merge и отдельного разрешения.

## После завершения

### Фактически сделано

- добавлен user plugin `kael-coder-control`;
- зарегистрирован typed tool `coder_delegate`;
- handler вызывает `coderctl.py submit` через список argv, `shell=False`, bounded timeout и explicit error response;
- canonical response всегда содержит `requested_tier`, `selected_primary_model`, `actual_route`, `attempted_routes`, `mutation_started`, `production_privileges=false`;
- добавлены audit events classification, delegate invocation, router submit/result, rejected local tool и terminal failure;
- local terminal ограничен существующими controller scripts, а `coderctl.py submit` через terminal запрещён;
- `search_files`, general code execution, direct Git/GitHub tools и coder workspace paths блокируются;
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

После формирования PR добавлены runtime-config, deployment contract и shell syntax tests. Полный CI PR #596 ещё требуется.

### PR и commit

PR: #596 `Fail-closed Kael coder delegation`.

Commit: текущий head feature branch; итоговый SHA фиксируется после CI-fix цикла.

### Незавершённое

- CI ещё не завершён;
- production plugin не установлен;
- Telegram read-only Velvet/Max smoke, router POST и terminal ledger не проверены;
- rollback smoke не выполнен.

### Следующий шаг

Проверить и исправить CI PR #596, провести review и перевести PR из draft после завершения обязательных проверок. После merge выполнить только entities/operator reconcile для основного Hermes, пересоздать только `velvet-hermes-1` при необходимости и провести fail-closed Telegram canary без mutation.
