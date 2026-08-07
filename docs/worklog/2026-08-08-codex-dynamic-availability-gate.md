# Codex dynamic availability gate

- Дата: 2026-08-08
- ID: codex-dynamic-availability-gate-20260808
- Линия/фаза: Hermes Coder / unified subscription availability control
- Статус: завершено
- Ветка: fix/codex-dynamic-availability-gate
- Базовый commit: 328749227e26a8bfc8fc39447bf9782b9b040f2a

## Перед началом

### Цель

Объединить принятие решения о доступности ChatGPT Codex subscription для всех Hermes coder-потребителей и GPT Image 2 через динамический runtime-state вместо независимых cooldown/preflight решений.

### Исходный контекст

- GPT Image 2 имел отдельный live quota preflight перед каждым creative request;
- обычный coder provider-chain после quota/auth failure использовал локальный in-memory cooldown;
- Codex app-server уже предоставляет `used_percent`, `window_duration_mins`, `resets_at` и `rate_limit_reached_type` через `account/rateLimits/read`;
- Velvet и Max имеют отдельные `/opt/codex` auth homes и отдельные writable `/opt/codex-runs` volumes;
- пользовательский routing contract требует, чтобы Codex использовался первым только при динамическом `codex_available=true`;
- независимо от известного provider `resets_at` нужна тихая проверка каждые 5 часов, чтобы обнаруживать ранние сбросы недельной квоты.

### Планируемый объём

- добавить persisted per-project Codex availability state;
- сделать `codex_available` единственным разрешением на primary Codex route;
- хранить `codex_available_at` из реального provider `resets_at`;
- выполнять live probe при старте, каждые 5 часов и дополнительно при наступлении ожидаемого recovery time;
- не переносить обязательный пятичасовой cadence из-за ad-hoc/recovery refresh;
- немедленно блокировать Codex после explicit execution subscription failure;
- дать operator CLI для status/refresh/manual hold/clear без restart;
- подключить к одному gate обычный Kael/Velvet/Max coder provider-chain и GPT Image 2;
- удалить routing authority старого per-image live preflight и in-memory cooldown;
- сохранить split-key Byesu image boundary и high-resolution export contract.

### Планируемый контракт

- `codex_available` является динамическим runtime-флагом и единственным разрешением на попытку primary Codex route;
- `codex_available_at` хранит ожидаемое время восстановления из Codex `resets_at`, если оно известно;
- при `codex_available=false` coder-задачи и GPT Image 2 не запускают Codex и сразу используют настроенный fallback;
- явный `subscription_limit` немедленно переводит флаг в `false` и обновляет ожидаемое время восстановления;
- тихая live-проверка `account/rateLimits/read` выполняется при старте и затем каждые 5 часов независимо от известного `resets_at`;
- если `codex_available_at` наступает раньше следующего 5-часового цикла, выполняется дополнительная live-проверка в это время;
- ранний provider reset, обнаруженный очередной 5-часовой проверкой, немедленно возвращает `codex_available=true`;
- оператор может прочитать status, принудительно refresh, поставить manual hold до `auto`/явного времени и снять hold без рестарта контейнеров;
- состояние хранится отдельно для project auth context Velvet и Max.

### Риски и ограничения

- Codex provider может менять rate-limit schema; неизвестный формат не должен самовольно переводить неизвестное состояние в `true`;
- отдельные `/opt/codex` auth homes Velvet и Max не считаются одной subscription identity без отдельного доказательства;
- manual hold является операторским override и не должен автоматически превращаться в `available=true` только по истечении времени без live probe;
- periodic refresh не должен сдвигаться из-за дополнительных refresh у `resets_at`, иначе теряется обязательный пятичасовой контрольный ритм;
- persisted state изменяется отдельным process, поэтому background watcher перечитывает локальный state раз в минуту без provider request.

### Миграции и совместимость

- database migration не требуется;
- состояние хранится в существующем writable `/opt/codex-runs` volume каждого coder project;
- существующие Byesu credentials и split-key GPT Image 2 contract не меняются;
- существующий read-only rate-limit endpoint сохраняется;
- legacy filename `codex_image_limit_preflight.py` сохраняется ради runtime/release совместимости, но больше не выполняет live quota probe на каждый image request.

### Критерии готовности

- unit tests подтверждают persisted state, 5h cadence, ранний reset, manual hold/clear и fail-safe unknown startup;
- coder provider chain пропускает primary Codex при `codex_available=false`;
- GPT Image 2 использует тот же gate;
- explicit `subscription_limit` обновляет gate до недоступного до следующего запуска;
- operator CLI даёт status/refresh/hold/clear;
- protected CI зелёный перед merge.

## После завершения

### Фактически сделано

- добавлен `codex_availability.py` с атомарным JSON-state и file lock;
- startup state fail-closed относительно Codex: unknown означает `codex_available=false`;
- startup live probe выполняется синхронно до открытия HTTP server, поэтому persisted stale true не может использоваться до свежей проверки;
- неудачный startup probe сбрасывает persisted provider decision в `unknown/false`, а не сохраняет старое true;
- обязательный periodic provider probe настроен на `18000` секунд отдельно для Velvet и Max;
- ad-hoc refresh и recovery probe не изменяют `next_periodic_check_at`;
- `codex_available_at` вычисляется из latest blocking future `resets_at`;
- ранний weekly reset может быть обнаружен пятичасовым refresh до старого `resets_at`;
- explicit execution subscription failure делает persisted flag false до диагностического probe и не позволяет противоречивому snapshot сразу вернуть true;
- manual hold поддерживает `--until auto`, ISO-8601 и Unix epoch;
- manual clear снимает hold и выполняет live refresh вместо принудительного true;
- background watcher перечитывает только локальный state раз в минуту, чтобы замечать изменения другого process без лишних OpenAI probes;
- обычный provider-chain использует persisted gate через `_cooling_down`, а legacy in-memory cooldown больше не является authority;
- GPT Image 2 читает тот же manager gate и больше не делает отдельный live rate-limit request на каждую генерацию;
- image runtime env projection больше не переносит старые preflight flags;
- документация и env examples переведены на dynamic availability contract.

### Проверки

- добавлены `tests/test_codex_availability.py` и `tests/test_codex_availability_runtime_contract.py`;
- обновлены image preflight/runtime-env regression tests;
- regression покрывает fixed 5h cadence, ранний weekly reset, persisted manual hold, clear-with-live-refresh, explicit execution failure, stale true после неудачного startup probe и локальный state poll;
- на implementation head `aac63d1c2ec3a0d3e1c76f07804743536883e532` зелёные все 6 required checks: project notes contract, type check, tests, security supply chain, docker build и branch protection contract;
- Docker CI валидировал Compose и собрал изменённые Hermes Coder surfaces.

### PR и commit

- PR: #705 `Unify Codex routing behind dynamic availability state`;
- ветка: `fix/codex-dynamic-availability-gate`;
- базовый commit: `328749227e26a8bfc8fc39447bf9782b9b040f2a`;
- проверенный implementation head: `aac63d1c2ec3a0d3e1c76f07804743536883e532`;
- финальный documentation head и merge commit фиксируются GitHub после последнего protected CI.

### Незавершённое

- production rollout через штатный Velvet update + Hermes orchestration installer;
- live smoke persisted state и `18000`-секундного schedule metadata для Velvet и Max;
- live smoke coder route при фактическом `codex_available=true/false`;
- live GPT Image 2 smoke через тот же gate.

### Следующий шаг

Дождаться protected CI на финальном documentation head, выполнить exact-head merge PR #705, затем controlled production rollout и live routing smoke.
