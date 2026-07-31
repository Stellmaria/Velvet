# Гибридный AI-контур: PR A contracts/config

- Дата: 2026-07-31
- ID: #505
- Линия/фаза: Hybrid AI / PR A
- Статус: завершено
- Ветка: `feat/505-hybrid-ai-contracts`
- Базовый commit: `d955a6e8e71609b83b4324c9ba5dc04e73debeed`

## Перед началом

### Цель

Подготовить runtime и server preflight к trusted internal VL provider без возврата
старого `provider=ollama` в production-архитектуру.

### Исходный контекст

Production VPS уже запущен, но `AI_VISION_ENABLED=false`. Текущий preflight
разрешал только billable cloud VL и намеренно запрещал Ollama. Issue #505 меняет
целевую архитектуру на local-first VL через внутренний gateway при сохранении
облачного Pro fallback.

### Планируемый объём

- добавить provider `local_openai_compatible`;
- разрешить пустой API key только trusted internal route;
- ограничить endpoint Compose hostname `vision-gateway`;
- задать нулевую monetary pricing для локального inference;
- сохранить usage, latency и outcome в существующем ledger;
- добавить server/runtime contracts и выключенный env-шаблон.

### Критерии готовности

- local provider нельзя направить на public или loopback endpoint;
- cloud provider по-прежнему требует key и положительную pricing;
- local route проходит без API key и с нулевой стоимостью;
- старый `provider=ollama` не возвращается в production contract;
- unit tests, type check, architecture contracts и Docker build зелёные.

### Риски и ограничения

Этот срез не поднимает inference-контейнеры и не включает Vision в production.
Неправильное наследование route-level base URL может создать SSRF или случайно
отправить sensitive-контент внешнему провайдеру, поэтому provider override обязан
иметь собственный endpoint.

## После завершения

### Фактически сделано

- добавлен `local_openai_compatible`;
- internal endpoint ограничен `vision-gateway`;
- public domains, loopback, credentials, query и fragment отклоняются;
- локальные FLASH/SENSITIVE получают monetary pricing `0`;
- zero-cost запросы продолжают проходить через AI usage executor;
- cloud-маршруты сохраняют key/pricing guards;
- server preflight создаёт `${VELVET_DATA_DIR}/vision`;
- добавлены runtime и preflight contract tests;
- добавлен `.env.vision-local.example`, оставленный выключенным до PR B.

### Миграции и совместимость

Миграции PostgreSQL отсутствуют. Существующие cloud-конфигурации продолжают
работать без изменений. Legacy `ollama` остаётся допустимым только в старых
runtime типах и продолжает блокироваться server preflight.

### Проверки

- test shards и fast architecture preflight: success;
- type check: success;
- project notes contract: success;
- Docker/Compose, Velvet, Supervisor proxy, Krita и Hermes Coder builds: success;
- branch синхронизирована с актуальным `main`;
- generated package architecture inventory и exemptions синхронизированы.

### PR и commit

- PR: #506;
- рабочая ветка: `feat/505-hybrid-ai-contracts`;
- проверенный head до финальной записи worklog: `87b9889280c009233c2a9a2e50e275167e887a91`.

### Незавершённое

- контейнеры `vision-gateway` и `vision-runtime`;
- Q8/Q4 benchmark на production VPS;
- локальный NSFW classifier и sensitive schema/prompt;
- Venice RP live enablement;
- Image-to-Prompt/Pose migration;
- production smoke и включение очереди.

### Следующий шаг

После слияния PR #506 открыть PR B с internal-only `vision-gateway`,
`vision-runtime`, pinned images/models и benchmark tooling.
