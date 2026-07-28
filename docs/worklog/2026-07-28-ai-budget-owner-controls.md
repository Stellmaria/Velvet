# 2026-07-28 — owner-контроль AI-бюджета

- Дата: 2026-07-28
- ID: ai-budget-owner-controls
- Линия/фаза: Линия B — Velvet AI / owner budget controls
- Статус: `частично`
- Ветка: `agent/ai-budget-owner-controls`
- Базовый commit: `820d1104a32d4ad913dfe2eb37bdede03511ccc3`

## Перед началом

### Цель

Добавить владельцу Telegram-команды для просмотра AI-бюджета и расходов, ручной приостановки и возобновления платных запросов, а также однократные месячные предупреждения при достижении настроенных порогов.

### Исходный контекст

После PR #350 реальные РП-запросы резервируют бюджет и записывают фактические токены и стоимость в `ai_usage_events`. Владелец пока не может просмотреть эти данные или остановить AI-контур из Telegram. Пороговые значения 70/85/95% вычисляются policy, но уведомления не отправляются и не защищены от повторов после рестарта.

### Планируемый объём

- создать единый `AIUsageService` в composition root и передавать его РП-клиенту и Telegram-контроллерам;
- добавить `/ai_budget`, `/ai_usage`, `/ai_pause`, `/ai_resume`;
- показывать фактические расходы, активные резервации, остатки лимитов и состояние pause;
- добавить новую неизменяемую миграцию для хранения последнего отправленного месячного порога;
- атомарно фиксировать достигнутый порог и отправлять предупреждение в приватный audit-чат;
- добавить команды в owner-only access contract и справочник;
- покрыть domain, repository и Telegram formatting тестами.

### Критерии готовности

- не-владелец не проходит owner-only gate новых команд;
- `/ai_budget` показывает лимиты, расходы, резервации и pause-state без прямого SQL в handler;
- `/ai_usage` выводит компактный список последних операций;
- `/ai_pause` блокирует новые provider calls, `/ai_resume` снимает блокировку;
- порог 70/85/95% отправляется не более одного раза за календарный месяц;
- новый месяц сбрасывает дедупликацию автоматически;
- существующие tests, type check, Docker build и project notes contract проходят.

### Риски и ограничения

- предупреждение отправляется через существующий `LOG_CHAT_ID`; если audit-чат не настроен, состояние порога всё равно сохраняется, но Telegram-сообщение отсутствует;
- стоимость provider error без usage остаётся нулевой, как зафиксировано в предыдущем срезе;
- этот этап не подключает VL router и не переносит production на VPS;
- applied migrations не редактируются, используется новая `z005`.

## После завершения

### Фактически сделано

- добавлены owner-команды `/ai_budget`, `/ai_usage`, `/ai_pause`, `/ai_resume`;
- создан единый `AIUsageService` в composition root и передан РП-клиенту и Telegram workflow data;
- `/ai_budget` показывает дневной и месячный лимиты, фактические расходы, reservations, остаток обычных задач и полный остаток с резервом Hermes;
- `/ai_usage` показывает последние операции с scope, model, operation, стоимостью, токенами и latency;
- pause/resume записываются в `ai_runtime_state` и немедленно применяются к новым provider calls;
- пороги 70/85/95% фиксируются атомарно и не повторяются в пределах месяца;
- новый месяц допускает повторную отправку порогов;
- предупреждение доставляется через существующий приватный `TelegramAuditLogger`;
- команды зарегистрированы в owner-only access contract, owner help и UI/direct route inventory;
- лишняя broad exception boundary не добавлялась: audit logger уже изолирует ошибку Telegram sink;
- добавлены PostgreSQL integration tests и unit-тесты Telegram formatting/access.

### Миграции и совместимость

Добавлена новая неизменяемая миграция `migrations/z005_ai_budget_warning_state.sql`. Она добавляет nullable-поля `warning_month` и `warning_percent` в singleton `ai_runtime_state`; старые миграции не изменены. Backup/restore drill подтвердил применение и восстановление схемы. При пустом `LOG_CHAT_ID` бюджет и дедупликация продолжают работать, но Telegram-предупреждение не отправляется.

### Проверки

На head `a2d746da0c2775c0ecf39a3c4e699a634ed31a72` успешно прошли:

- tests workflow `#2073`: 1465 тестов;
- type check `#726`;
- Docker build `#1452`;
- project notes contract `#1312`;
- backup restore drill `#455`.

Live-вызовы платных провайдеров и живой Telegram-smoke намеренно не выполнялись в CI.

### PR и commit

- PR: `#351` — «Добавить owner-контроль AI-бюджета».
- Ветка: `agent/ai-budget-owner-controls`.
- Проверенный head: `a2d746da0c2775c0ecf39a3c4e699a634ed31a72`.

### Незавершённое

- живой Telegram-smoke `/ai_budget`, `/ai_usage`, `/ai_pause`, `/ai_resume` после обновления production;
- проверка реального порогового сообщения при платном provider call;
- подключение VL-клиентов к executor;
- Flash → Pro → sensitive маршрутизация и task queue worker;
- серверный deployment и внешний uptime-monitor.

### Следующий шаг

Подключить Flash → Pro → sensitive VL router к единому `AIRequestExecutor`, добавить pricing для трёх маршрутов, cache/dedupe по image hash и очередь `ai_tasks`.