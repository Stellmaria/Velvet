# 2026-08-02 — Маршрутизация Codex Luna/Terra/Sol

- Дата: `2026-08-02`
- ID: `hermes-codex-model-routing`
- Статус: `реализовано в ветке`
- Ветка: `infra/hermes-codex-56-runner`

## Цель

Не отправлять все Hermes coder-задачи в одну модель после перехода на ChatGPT-authenticated Codex CLI.

## Реализация

Добавлен отдельный `codex_routed_runner.py`, который сохраняет исходный Runs API и выбирает модель до передачи задания в базовый runner:

```text
маленькая правка / README / docs / rename -> gpt-5.6-luna
обычная разработка                       -> gpt-5.6-terra
архитектура / migration / security       -> gpt-5.6-sol
```

Явная директива имеет приоритет:

```text
/model luna
/model terra
/model sol
```

Поддерживаются русские алиасы `луна`, `терра`, `сол`.

После выбора базовый runner сохраняет fallback только для ошибок доступности, лимита или capacity:

```text
Luna  -> Terra -> Sol
Terra -> Sol -> Luna
Sol   -> Terra -> Luna
```

## Изоляция изменений

Главный `hermes-coder-router` не изменён. Его task, PR, CI и GitHub verification contracts остаются прежними. Compose запускает routed entrypoint внутри тех же project-isolated Codex containers.

## Проверки

Добавлен `tests/test_hermes_codex_routing.py`:

- явный выбор модели;
- Luna для простой документации;
- Terra для обычной разработки;
- Sol для архитектуры и security;
- сохранение явно переданного model;
- проверка routed entrypoint в Dockerfile и Compose.

Целевой локальный набор после добавления маршрутизации: `24 tests, OK`.
