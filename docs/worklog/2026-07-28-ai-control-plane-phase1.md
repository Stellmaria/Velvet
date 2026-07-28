# 2026-07-28 — AI control plane, фаза 1

- Дата: 2026-07-28
- ID: ai-control-plane-phase1
- Линия/фаза: Линия B — Velvet AI / control plane
- Статус: `частично`
- Ветка: `agent/ai-control-plane-phase1`
- Базовый commit: `14ab83a8e73b7e86037af4399c766a8b1eda22ab`

## Перед началом

### Цель

Начать реализацию каскадного AI-контура с оплатой только по факту использования, жёсткими бюджетными ограничениями и безопасной эскалацией повторных падений в Hermes.

### Исходный контекст

В `main` уже существовали облачные настройки VL/RP, Docker-профиль Hermes, Supervisor, диагностические логи и Codex-контур. Не хватало единого ТЗ, бюджетной policy и рабочего безопасного пути, по которому повторный crash-loop автоматически передаётся Hermes без выдачи ему production-секретов и неограниченных полномочий.

### Планируемый объём

- зафиксировать целевую архитектуру VL, RP, Hermes, Codex и serverless GPU;
- добавить дневной, месячный и per-request budget guard;
- сохранить отдельный аварийный резерв Hermes;
- подключить официальный Hermes Runs API;
- очищать incident payload от токенов, паролей и DSN;
- эскалировать повторные падения, не блокируя monitor loop;
- включить внутренний Hermes API только на loopback VPS;
- добавить unit tests и серверные env-примеры.

### Критерии готовности

- budget guard блокирует запрос до его отправки при превышении лимита;
- обычные AI-задачи не могут израсходовать резерв Hermes;
- одинаковый incident не отправляется повторно в течение cooldown;
- Hermes получает только ограниченный очищенный пакет логов;
- Supervisor вызывает Hermes после заданного числа падений или crash-loop;
- Hermes API не публикуется на внешнем интерфейсе;
- существующие tests, type check, Docker Compose и project notes contract проходят.

### Риски и ограничения

- первая фаза не записывает фактический usage в PostgreSQL;
- budget guard пока не подключён ко всем VL/RP HTTP-вызовам;
- Hermes анализирует только падения процесса Velvet, а не полный набор server health-сигналов;
- конкретные model ID нельзя фиксировать до живой проверки API провайдера;
- автоматическое исправление кода и deployment не разрешены без отдельного этапа и подтверждения.

## После завершения

### Фактически сделано

- добавлено ТЗ `docs/AI_CONTROL_PLANE_TZ.md`;
- добавлен Decimal-based `velvet_bot.core.ai_budget`;
- реализованы дневной и месячный лимит, лимит одного запроса, аварийный резерв Hermes и предупреждения 70/85/95%;
- добавлен `HermesIncidentClient` через `POST /v1/runs`;
- incident отправляется в daemon thread и не блокирует Supervisor;
- добавлены fingerprint, cooldown и ограничение размера логов;
- логи очищаются от Bearer/API/Telegram токенов, паролей и PostgreSQL DSN;
- `runtime_extended` эскалирует повторные падения и crash-loop;
- status Supervisor показывает состояние последней Hermes-эскалации;
- Docker публикует Hermes API только на `127.0.0.1:8642`;
- обновлены `.env.example` и `.env.hermes.example`;
- добавлены unit tests budget guard и Hermes incident client.

### Миграции и совместимость

Миграции БД в этой фазе отсутствуют. Новая функциональность выключена по умолчанию через `HERMES_INCIDENT_ENABLED=false`. AI budget policy не меняет существующие VL/RP вызовы до подключения единого request executor в следующей фазе.

### Проверки

- добавлены `tests/test_ai_budget.py`;
- добавлены `tests/test_supervisor_hermes_incident.py`;
- запущен полный GitHub CI для PR;
- project notes contract первоначально потребовал стандартный формат worklog, файл исправлен;
- live Hermes/BYESU запросы намеренно не выполняются в CI.

### PR и commit

- PR: `#348`
- Ветка: `agent/ai-control-plane-phase1`

### Незавершённое

- добавить таблицы `ai_usage_events` и `ai_tasks`;
- подключить budget guard к общему AI executor;
- записывать provider usage, стоимость и latency;
- добавить `/ai_budget`, `/ai_usage`, `/ai_pause`;
- реализовать Flash → Pro → sensitive VL router;
- подключить RP provider и память к usage ledger;
- добавить health-сигналы PostgreSQL, диска, очередей и второго бота.

### Следующий шаг

Добавить PostgreSQL usage ledger и единый AI request executor, который выполняет preflight budget check, вызывает выбранного провайдера, записывает фактические токены/стоимость и только затем разрешает fallback или повтор.
