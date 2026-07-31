# Гибридный AI-контур: PR A contracts/config

Связано с issue #505.

## Цель среза

Подготовить runtime и server-preflight к trusted internal VL provider без возврата
старого `provider=ollama` в production-архитектуру.

## Изменения

- добавлен provider `local_openai_compatible`;
- internal provider разрешает пустой API key;
- endpoint ограничен Compose hostname `vision-gateway`;
- public domains, loopback, credentials, query и fragment отклоняются;
- локальные FLASH/SENSITIVE маршруты получают monetary pricing `0`;
- zero-cost запросы продолжают проходить через существующий AI usage executor;
- cloud-маршруты по-прежнему требуют key и положительную pricing;
- route-level смена provider требует собственного base URL;
- server preflight создаёт persistent directory `${VELVET_DATA_DIR}/vision`;
- добавлен отдельный env-шаблон, который остаётся выключенным до PR B.

## Границы

Этот срез не добавляет inference-контейнеры, classifier, sensitive prompt,
Venice RP или production enablement. Следующий срез PR B должен добавить
`vision-gateway`, `vision-runtime`, pinned images/models, healthchecks и benchmark.

## Проверки

Добавлены unit/contract tests для runtime settings, zero-cost route pricing и
server preflight. Фактический CI и Docker build фиксируются в PR после запуска
GitHub Actions.
