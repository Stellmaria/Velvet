# 2026-07-28 — учёт расходов РП, фаза 3A

- Дата: 2026-07-28
- ID: roleplay-usage-metering-phase3a
- Линия/фаза: Линия B — Velvet AI / RP usage metering
- Статус: `частично`
- Ветка: `agent/roleplay-usage-metering`
- Базовый commit: `80a1d4cb724736d5028c855bacf61f74e1f93560`

## Перед началом

### Цель

Подключить реальные запросы ролевой модели к транзакционному AI budget executor, чтобы стоимость резервировалась до обращения к провайдеру, а фактические токены и расходы сохранялись в PostgreSQL.

### Исходный контекст

После фаз 1 и 2 в `main` уже существовали budget policy, `ai_usage_events`, атомарные reservations и `AIRequestExecutor`. Ролевой клиент продолжал обращаться к Responses API и Chat Completions напрямую, поэтому дневной и месячный лимиты ещё не защищали реальные РП-запросы.

### Планируемый объём

- добавить конфигурируемую цену входных и выходных токенов;
- запрещать запуск включённой модели без известной цены;
- извлекать usage из Responses API и OpenAI-compatible Chat Completions;
- резервировать максимальную оценочную стоимость до provider call;
- сохранять фактические токены, стоимость и признак provider-reported usage;
- использовать консервативную оценку, если endpoint не вернул usage;
- учитывать primary и fallback как отдельные оплачиваемые вызовы;
- добавить unit tests и env-пример.

### Критерии готовности

- РП-запрос не отправляется провайдеру при отказе budget guard;
- primary и fallback используют собственные цены;
- provider usage сохраняется в `ai_usage_events`;
- отсутствие usage не превращает стоимость в ноль;
- выключенный AI-контур сохраняет прежнее поведение;
- существующие tests, type check, Docker build и project notes contract проходят.

### Риски и ограничения

- реальные model ID и цены подтверждаются только живым API-тестом;
- разные OpenAI-compatible endpoints могут возвращать usage в отличающемся формате;
- provider error может не содержать токены уже принятого запроса;
- этот срез не подключает VL и не добавляет Telegram-команды владельца.

## После завершения

### Фактически сделано

- добавлен `AITokenPricing` с точностью PostgreSQL `NUMERIC(14,4)`;
- добавлены env-параметры цены за 1 млн input/output токенов;
- `TextRoleplayClient` резервирует стоимость через `AIRequestExecutor`;
- Responses API читает `input_tokens` и `output_tokens`;
- Chat Completions читает `prompt_tokens` и `completion_tokens`;
- при отсутствии usage применяются консервативные оценки по размеру текста;
- user ID и chat ID сохраняются вместе с reservation;
- metadata результата дописывается в существующий ledger event;
- primary и fallback используют общий usage service, но создают отдельные reservations;
- добавлены тесты pricing и metered roleplay client;
- обновлён generated Telegram navigation inventory после добавления Python-модуля.

### Миграции и совместимость

Новые миграции отсутствуют: используется таблица `ai_usage_events` из `z004_ai_usage_ledger.sql`. Проверка цены выполняется только при `AI_TEXT_ENABLED=true`. При выключенной текстовой модели запуск бота не требует новых переменных. Для primary необходимо задать `AI_TEXT_INPUT_RUB_PER_1M` и/или `AI_TEXT_OUTPUT_RUB_PER_1M`; для включённого fallback используются отдельные `AI_TEXT_FALLBACK_*` цены.

### Проверки

- GitHub Actions `tests` run `#2068`: успешно, 1459 тестов;
- GitHub Actions `type check` run `#721`: успешно;
- GitHub Actions `docker build` run `#1447`: успешно;
- GitHub Actions `project notes contract` run `#1308`: успешно;
- первый `tests` run `#2067` обнаружил только устаревшее число Python-файлов в generated inventory; inventory обновлён, повторный прогон зелёный;
- live-запросы к платным провайдерам намеренно не выполнялись.

### PR и commit

- PR: `#350`;
- Ветка: `agent/roleplay-usage-metering`;
- проверенный кодовый head до финальной синхронизации worklog: `8b2cab30807033b097ccbc20fab2158d15f14757`.

### Незавершённое

- post-request warning в Telegram;
- owner-команды `/ai_budget`, `/ai_usage`, `/ai_pause`, `/ai_resume`;
- подключение VL-клиентов к executor;
- pricing registry для нескольких проверенных моделей;
- учёт оплаченных токенов при provider error, если endpoint начнёт возвращать usage в ошибке.

### Следующий шаг

Добавить owner-команды бюджета и расходов, затем подключить Flash → Pro → sensitive VL router к тому же executor и pricing registry.
