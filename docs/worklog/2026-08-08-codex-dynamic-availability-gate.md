# Codex dynamic availability gate

- Дата: 2026-08-08
- Статус: в работе

## Перед началом

### Цель

Объединить принятие решения о доступности ChatGPT Codex subscription для всех Hermes coder-потребителей и GPT Image 2 через динамический runtime-state вместо независимых cooldown/preflight решений.

### Планируемый контракт

- `codex_available` является динамическим runtime-флагом и единственным разрешением на попытку primary Codex route;
- `codex_available_at` хранит ожидаемое время восстановления из Codex `resets_at`, если оно известно;
- при `codex_available=false` coder-задачи и GPT Image 2 не запускают Codex и сразу используют настроенный fallback;
- явный `subscription_limit` немедленно переводит флаг в `false` и обновляет ожидаемое время восстановления;
- тихая live-проверка `account/rateLimits/read` выполняется при старте и затем не реже одного раза каждые 5 часов независимо от известного `resets_at`;
- если `codex_available_at` наступает раньше следующего 5-часового цикла, выполняется дополнительная live-проверка в это время;
- ранний provider reset, обнаруженный очередной 5-часовой проверкой, немедленно возвращает `codex_available=true`;
- оператор может прочитать status, принудительно refresh, поставить manual hold до `auto`/явного времени и снять hold без рестарта контейнеров;
- состояние хранится отдельно для project auth context Velvet и Max.

### Риски и ограничения

- Codex provider может менять rate-limit schema; неизвестный формат не должен самовольно переводить неизвестное состояние в `true`;
- отдельные `/opt/codex` auth homes Velvet и Max не считаются одной subscription identity без отдельного доказательства;
- manual hold является операторским override и не должен автоматически превращаться в `available=true` только по истечении времени без live probe;
- periodic refresh не должен сдвигаться из-за дополнительных refresh у `resets_at`, иначе теряется обязательный пятичасовой контрольный ритм.

### Миграции и совместимость

- database migration не требуется;
- состояние хранится в существующем writable `/opt/codex-runs` volume каждого coder project;
- существующие Byesu credentials и split-key GPT Image 2 contract не меняются;
- существующий read-only rate-limit endpoint сохраняется.

### Критерии готовности

- unit tests подтверждают persisted state, 5h cadence, ранний reset, manual hold/clear и fail-safe unknown startup;
- coder provider chain пропускает primary Codex при `codex_available=false`;
- GPT Image 2 использует тот же gate;
- explicit `subscription_limit` обновляет gate до недоступного до запуска fallback;
- router и owner CLI дают status/refresh/hold/clear;
- protected CI зелёный перед merge.

## После завершения

### Фактически сделано

В работе.

### Проверки

В работе.

### PR и commit

В работе.

### Незавершённое

Реализация и production rollout.

### Следующий шаг

Реализовать gate и regression coverage, открыть PR и дождаться protected CI.
