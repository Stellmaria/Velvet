# 2026-07-28 — AI usage ledger, фаза 2

- Дата: 2026-07-28
- ID: ai-usage-ledger-phase2
- Линия/фаза: Линия B — Velvet AI / usage ledger
- Статус: `частично`
- Ветка: `agent/ai-usage-ledger-phase2`
- Базовый commit: `5ca8428df357905a2e3eb09a766af37f0a0a2ce3`

## Перед началом

### Цель

Превратить бюджетную policy первой фазы в транзакционный PostgreSQL-контур, который резервирует стоимость до AI-запроса, учитывает фактические токены и не допускает конкурентного превышения лимита.

### Исходный контекст

После слияния PR #348 в `main` уже существуют ТЗ, Decimal-based budget guard, аварийный резерв Hermes и безопасная эскалация crash-loop. Однако guard ещё не хранит usage в БД и не оборачивает реальные provider calls.

### Планируемый объём

- добавить миграцию `ai_usage_events`, `ai_runtime_state` и `ai_tasks`;
- реализовать атомарную резервацию бюджета под PostgreSQL row lock;
- учитывать активные резервации вместе с фактическими расходами;
- добавить pause/resume AI-контура;
- сохранять provider, model, operation, tokens, latency и стоимость;
- добавить единый request executor;
- проверить конкурирующие резервации на настоящем PostgreSQL.

### Критерии готовности

- два параллельных запроса не могут одновременно превысить остаток бюджета;
- обычные запросы не расходуют резерв Hermes;
- успешный запрос заменяет estimate на фактическую стоимость;
- ошибка и отмена закрывают резервацию;
- paused runtime блокирует новые запросы;
- stale reservations можно освободить;
- миграция, unit/integration tests, type check и Docker build проходят.

### Риски и ограничения

- конкретные provider clients пока не возвращают унифицированный usage;
- pricing registry и автоматический estimate будут отдельной фазой;
- фактическая стоимость может оказаться выше estimate, поэтому далее нужны post-request alerts;
- очередь `ai_tasks` в этой фазе получает схему, а worker/claim API будет подключён вместе с VL router.

## После завершения

### Фактически сделано

- добавлена миграция `z004_ai_usage_ledger.sql`;
- добавлены таблицы `ai_runtime_state`, `ai_usage_events` и `ai_tasks`;
- добавлен `AIUsageRepository` с атомарной резервацией под `FOR UPDATE`;
- при расчёте лимита учитываются фактические расходы и незавершённые reservations;
- реализованы complete, fail, cancel и очистка stale reservations;
- реализованы pause/resume и чтение runtime state;
- добавлены `AIUsageService`, `AIRequestExecutor` и `AIBudgetExceeded`;
- executor закрывает reservation при success, error и cancellation;
- добавлены PostgreSQL integration tests, включая конкурентные запросы.

### Миграции и совместимость

Добавлена новая неизменяемая миграция `migrations/z004_ai_usage_ledger.sql`. Существующие AI-клиенты продолжают работать как прежде, пока их явно не подключили к `AIRequestExecutor`. Новые таблицы не изменяют старые схемы и допускают безопасный rollback к коду предыдущей версии.

### Проверки

- добавлены integration tests реальной PostgreSQL-схемы;
- проверяется резерв Hermes, pause/resume и замена estimate фактическим usage;
- полный GitHub CI запускается после открытия PR;
- live-запросы к платным провайдерам не выполняются.

### PR и commit

- PR: будет создан после подготовки ветки
- Ветка: `agent/ai-usage-ledger-phase2`

### Незавершённое

- подключить RP client к executor и извлекать usage из API-ответов;
- добавить pricing registry для BYESU/RP/VL;
- реализовать task queue repository и worker claim;
- добавить Telegram-команды `/ai_budget`, `/ai_usage`, `/ai_pause`;
- добавить VL router и image cache.

### Следующий шаг

Подключить РП-клиент к usage executor, сохранять реальные токены из provider response, затем реализовать owner-команды бюджета и первый Flash → Pro → sensitive VL route.
