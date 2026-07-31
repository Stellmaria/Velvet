# Гибридный AI-контур: PR A contracts/config

- Дата: 2026-07-31
- ID: #505
- Линия/фаза: Hybrid AI / PR A
- Статус: частично
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

- type check первого CI-запуска: success;
- первый test run выявил отсутствующий provider в `VisionRouteConfig`, исправлено;
- первый architecture run выявил рост `load_settings`, исправлено декомпозицией;
- первый project notes run выявил старый формат и статус worklog, исправлено;
- branch синхронизирована с актуальным `main`, generated inventory обновлён;
- повторный полный CI запущен после синхронизации.

### PR и commit

- PR: #506;
- рабочая ветка: `feat/505-hybrid-ai-contracts`;
- финальный commit фиксируется после зелёного CI.

### Незавершённое

- подтверждение полного CI после синхронизации с main;
- контейнеры `vision-gateway` и `vision-runtime`;
- Q8/Q4 benchmark на production VPS;
- локальный NSFW classifier и sensitive schema/prompt;
- Venice RP live enablement;
- Image-to-Prompt/Pose migration;
- production smoke и включение очереди.

### Следующий шаг

Довести PR #506 до зелёного состояния, затем открыть PR B с internal-only
`vision-gateway`, `vision-runtime`, pinned images/models и benchmark tooling.
