# Сессия: маршрутизация Codex Luna, Terra и Sol

- Дата: 2026-08-02
- ID: 2026-08-02-hermes-codex-model-routing
- Линия/фаза: server operations / Hermes model routing
- Статус: частично
- Ветка: infra/hermes-codex-56-runner
- Базовый commit: 0ad3e39e0607c55dc06fe4bdbb90ca3fdcaa779a

## Перед началом

### Цель

Распределять Hermes coder-задачи между `gpt-5.6-luna`, `gpt-5.6-terra` и `gpt-5.6-sol`, а не отправлять все задания в одну модель после перехода на ChatGPT-authenticated Codex CLI.

### Исходный контекст

Базовый Hermes coder config использовал цепочку Byesu `mini -> terra -> luna`. После перехода на Codex требовалось добавить Sol, использовать точные Codex model IDs и сохранить возможность явного выбора модели без изменения основного `hermes-coder-router`.

### Планируемый объём

- добавить ограниченный allowlist Luna, Terra и Sol;
- выбрать Terra как обычную модель;
- направлять мелкие документационные задачи в Luna;
- направлять архитектуру, security и крупные миграции в Sol;
- поддержать явные директивы `/model`;
- оставить fallback только для ошибок модели, rate limit или capacity;
- покрыть маршрутизацию отдельными тестами.

### Критерии готовности

- никакая модель вне allowlist не запускается;
- явный выбор пользователя имеет приоритет над эвристикой;
- обычные задачи используют Terra;
- небольшие docs/rename задачи используют Luna;
- архитектурные и security задачи используют Sol;
- fallback не скрывает обычные ошибки выполнения;
- routed entrypoint используется Compose services;
- CI проекта проходит.

### Риски и ограничения

- keyword routing является детерминированной эвристикой, а не semantic classifier;
- слишком широкие ключевые слова могут необоснованно выбрать Sol;
- fallback между моделями не должен повторять задачи при обычной ошибке кода;
- фактическая доступность моделей подтверждается только после device login и live smoke.

## После завершения

### Фактически сделано

- добавлен `codex_routed_runner.py`;
- реализованы явные директивы `/model luna`, `/model terra`, `/model sol`;
- добавлены русские формы `модель: луна`, `модель: терра`, `модель: сол`;
- Luna выбирается для небольших README/docs/rename задач;
- Terra остаётся моделью обычной разработки;
- Sol выбирается для архитектуры, migrations, security и крупных рефакторингов;
- реализованы fallback-цепочки:
  - `Luna -> Terra -> Sol`;
  - `Terra -> Sol -> Luna`;
  - `Sol -> Terra -> Luna`;
- исходный `hermes-coder-router` не изменён;
- routed entrypoint подключён внутри project-isolated Codex containers.

### Миграции и совместимость

Изменений публичного Runs API нет. Поле `model`, переданное явно, сохраняется. Задания без модели получают детерминированный выбор перед передачей базовому runner. Существующий router, ledger и PR/CI verification продолжают работать без новой схемы payload.

### Проверки

- `tests/test_hermes_codex_routing.py` проверяет явный выбор, Luna, Terra, Sol и сохранение переданной модели;
- contract-тесты проверяют routed entrypoint в Dockerfile и Compose;
- локальный целевой набор: `24 tests, OK`;
- первый полный CI PR #547 выявил отдельные проблемы regression-теста runtime smoke и формата worklog, не ошибку model routing;
- актуальный полный CI должен пройти после публикации исправлений;
- live model capabilities проверяются после device login на VPS.

### PR и commit

- PR: #547 `Перевести Hermes coder на Codex GPT-5.6`;
- ветка: `infra/hermes-codex-56-runner`;
- commits: routing implementation и последующие CI-fixes в этой ветке.

### Незавершённое

- получить зелёный полный CI;
- слить PR #547;
- выполнить server-side device login;
- подтвердить capabilities для Luna, Terra и Sol;
- выполнить тестовые задачи с автоматическим и явным выбором модели.

### Следующий шаг

После зелёного CI слить PR, установить runner на VPS и проверить одну Luna-, одну Terra- и одну Sol-задачу через главный Hermes.
