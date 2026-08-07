# Сессия: split Byesu credentials для Hermes image route

- Дата: 2026-08-07
- ID: `2026-08-07-hermes-dual-byesu-credentials`
- Линия/фаза: Hermes image routing / production remediation
- Статус: частично
- Ветка: `hotfix/hermes-dual-byesu-credentials`
- Базовый commit: `88326f61e42b97bdb4df56001436fcf46bb6cb2d`
- PR: pending

## Перед началом

### Цель

Разделить Byesu authentication для Hermes image route на два фактически существующих provider token group: Codex/GPT-5.6 credential для анализа и media/media-gen credential для `gpt-image-2`/`firefly-gpt-image-2`. Одновременно убрать generic `OPENAI_API_KEY` и `BYESU_HERMES_API_KEY` из credential fallback для Hermes, чтобы третий legacy/shared ключ не участвовал в этой цепочке.

### Исходный контекст

Production probes подтвердили, что Hermes-Codex token видит `gpt-5.6-sol`, `gpt-5.6-terra`, `gpt-5.6-luna`, но не image-модели. Отдельный Media Gen token видит `gpt-image-2` и `firefly-gpt-image-2`, но не GPT-5.6. Текущий `ByesuImageClient` использовал один `BYESU_HERMES_CODEX_API_KEY` и требовал обе группы capabilities одновременно, поэтому корректная provider-конфигурация была невозможна.

### Планируемый объём

- добавить `BYESU_HERMES_MEDIA_API_KEY` только для Velvet image runtime;
- оставить `BYESU_HERMES_CODEX_API_KEY` общей Hermes coder credential для GPT-5.6 provider routes;
- перед анализом проверять GPT-5.6 capability Codex token, а перед generation capability media token;
- image generation авторизовывать только media credential;
- не передавать media credential в Max и disposable Codex sandbox;
- исключить оба Byesu secrets из Codex shell environment policy;
- убрать generic operator aliases из canonical Hermes credential sync;
- сохранить существующий Codex-first, limit-preflight, one-generation и fail-closed contracts.

### Критерии готовности

- protected CI проходит на exact PR head;
- runtime import/mount graph содержит новый credential module;
- regression tests доказывают split capability checks и media authorization;
- canonical secret sync ротирует Codex и Media credentials независимо;
- Max не получает media credential;
- generic `OPENAI_API_KEY`/`BYESU_HERMES_API_KEY` не могут заменить explicit Hermes credentials;
- production activation выполняется отдельно только после read-only `/v1/models` проверки обоих реальных токенов.

### Риски и ограничения

Изменение не включает значения production secrets. Media credential остаётся доступен процессу Velvet coder, поскольку именно этот процесс вызывает Byesu image endpoint; disposable Codex execution получает только route-scoped allowlist и media key туда не передаётся. Existing generic `BYESU_API_KEY` основного Velvet application не удаляется автоматически: он используется отдельным application configuration contract и должен быть признан ненужным отдельной production-проверкой до revoke.

## После завершения

### Фактически сделано

Добавлен runtime patch `byesu_image_credentials.py`, который сохраняет Codex credential для `/responses`, проверяет analysis и media model catalogs раздельно и временно переключает client authorization на media credential только на вызове image generation. Новый module установлен перед существующими image fallback/routing patches и добавлен в Compose/runtime source graph.

Canonical `install.sh` теперь принимает только explicit `BYESU_HERMES_CODEX_API_KEY` и `BYESU_HERMES_MEDIA_API_KEY`; generic aliases больше не участвуют. Media secret записывается только в `velvet.env`, а stale media secret из `max.env` удаляется при следующем canonical sync. Codex shell policies исключают новый media secret.

### Миграции и совместимость

SQL/application migrations отсутствуют. Для production operator env требуется добавить `BYESU_HERMES_MEDIA_API_KEY`; существующий `BYESU_HERMES_CODEX_API_KEY` остаётся тем же semantic contract. Старые конфигурации без media key продолжают работать при выключенном image route, но попытка фактического Byesu image route fail closed при создании image client. Generic Hermes/OpenAI aliases больше не являются migration fallback.

### Проверки

Добавлены regression tests для раздельных capabilities, media authorization и independent credential rotation/scoping. Protected CI и production activation ещё не завершены на момент создания worklog.

### PR и commit

- Ветка: `hotfix/hermes-dual-byesu-credentials`.
- База: `88326f61e42b97bdb4df56001436fcf46bb6cb2d`.
- PR: pending.
- Финальный head/merge commit: pending.

### Незавершённое

- открыть PR и пройти protected CI;
- при необходимости адаптировать contract tests, найденные CI;
- merge только на current/up-to-date main без обхода branch protection;
- fast-forward production checkout;
- безопасно записать Codex и Media token values только на production host;
- обновить Codex shell config, выполнить canonical installer и factual runtime verification;
- отдельно доказать, используется ли legacy/general Byesu key основным Velvet application, до его revoke в Byesu Console.

### Следующий шаг

Открыть PR, дождаться полного protected CI на точном head и только после merge переходить к production secret rotation и activation.
