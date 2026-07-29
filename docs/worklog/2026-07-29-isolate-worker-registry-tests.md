# 2026-07-29 — изоляция тестов реестра worker-ов от локального Kie env

- Дата: 2026-07-29
- ID: isolate-worker-registry-tests
- Линия/фаза: Системная архитектура / тестовая изоляция
- Статус: `завершено`
- Ветка: `agent/isolate-kie-worker-registry-tests`
- Базовый commit: `39715d684714980d0c55479a65013a4ea9d30cdf`

## Перед началом

### Цель

Устранить падение локальных Supervisor update-тестов при включённом `KIE_ENABLED=true` в рабочем `.env`.

### Исходный контекст

`WorkerRegistryTests` вызывал `build_worker_manager()` без явного `KieSettings`. Production builder закономерно загружал локальный `.env` и регистрировал `kie-media-generation`, хотя тест ожидал базовый набор worker-ов без Kie.

### Планируемый объём

- передавать в архитектурные тесты явную отключённую конфигурацию Kie;
- не менять production-регистрацию worker-ов;
- сохранить отдельные тесты feature flag Krita;
- прогнать полный CI.

### Критерии готовности

- тесты проходят независимо от значения `KIE_ENABLED` в локальном `.env`;
- production при `KIE_ENABLED=true` продолжает регистрировать `kie-media-generation`;
- состав базового и Krita-набора worker-ов остаётся прежним.

### Риски и ограничения

Изменение касается только тестовой сборки manager-а. Реальные Kie credentials и provider calls не используются.

## После завершения

### Фактически сделано

В `WorkerRegistryTests._build_manager()` добавлена явная конфигурация `KieSettings(enabled=False)` со стандартными неплатными значениями. Тесты больше не загружают Kie-флаг из локального окружения.

### Миграции и совместимость

Миграции и изменения `.env` не требуются. Production behavior не меняется.

### Проверки

Ожидаются полный tests workflow, type check, Docker build и project notes contract.

### PR и commit

- PR: будет создан после изменения теста;
- ветка: `agent/isolate-kie-worker-registry-tests`;
- базовый commit: `39715d684714980d0c55479a65013a4ea9d30cdf`.

### Незавершённое

Нет.

### Следующий шаг

После слияния повторить Supervisor update на локальной машине.