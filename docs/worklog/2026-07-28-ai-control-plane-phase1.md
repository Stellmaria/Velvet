# 2026-07-28 — AI control plane, фаза 1

## Цель

Начать реализацию каскадного AI-контура с оплатой только по факту использования и безопасной эскалацией повторных падений в Hermes.

## Выполнено

- добавлено полное ТЗ `docs/AI_CONTROL_PLANE_TZ.md`;
- добавлен Decimal-based бюджетный guard:
  - дневной и месячный лимит;
  - лимит одного запроса;
  - отдельный аварийный резерв Hermes;
  - предупреждения 70/85/95%;
- добавлен Hermes incident client через `POST /v1/runs`;
- incident отправляется асинхронно и не блокирует monitor loop Supervisor;
- добавлена дедупликация одинаковых инцидентов по fingerprint и cooldown;
- логи очищаются от Bearer/API/Telegram токенов, паролей и PostgreSQL DSN;
- Supervisor эскалирует повторные падения и crash loop в Hermes;
- статус Supervisor показывает состояние последней Hermes-эскалации;
- внутренний Hermes API публикуется только на `127.0.0.1:8642`;
- добавлены env-параметры бюджетов и аварийной эскалации;
- добавлены unit tests бюджетной policy и Hermes incident client.

## Ограничения фазы

- budget guard пока является чистой policy и ещё не подключён ко всем VL/RP HTTP-вызовам;
- usage ledger в PostgreSQL и фактическая стоимость по provider usage будут добавлены следующей миграцией;
- Hermes получает инциденты только процесса Velvet; проверки PostgreSQL, диска, очередей и второго бота добавляются далее;
- конкретные model ID не фиксируются до живого теста доступных моделей провайдера.

## Следующий этап

1. миграция `ai_usage_events` и `ai_tasks`;
2. единый AI request executor с preflight budget check;
3. запись токенов, latency, provider/model и стоимости;
4. команды владельца `/ai_budget`, `/ai_usage`, `/ai_pause`;
5. VL router Flash → Pro → sensitive;
6. подключение RP provider и памяти к usage ledger.
