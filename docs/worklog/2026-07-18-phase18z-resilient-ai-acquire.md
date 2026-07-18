# Сессия: Фаза 18Z — Resilient AI vision repository и Database.acquire

- Дата: 2026-07-18
- ID: `2026-07-18-phase18z-resilient-ai-acquire`
- Линия/фаза: основное развитие Velvet Archive, Фаза 18Z
- Статус: частично
- Ветка: `agent/phase18z-resilient-ai-acquire`
- Базовый commit: `9ed31953c31a98cd22fd9e07c46cd658c9d304ab`

## Перед началом

### Цель

Перевести два connection point `ResilientMediaAIRepository` в `velvet_bot/resilient_ai_vision.py` с приватного `Database._require_pool()` на публичный `Database.acquire()` без изменения Telegram retry service.

### Исходный контекст

- baseline до работы: 86 внешних обращений в 22 production-файлах;
- целевой модуль: `velvet_bot/resilient_ai_vision.py`, 2 connection points;
- после среза категория repository-in-module должна стать нулевой.

### Планируемый объём

1. Перевести оба repository connection point на `Database.acquire()`.
2. Сохранить transient Telegram failure requeue, parent claim и response-version update.
3. Добавить regression-тесты.
4. Уменьшить baseline до 84/21 и обновить документы.

### Критерии готовности

- `ResilientMediaAIRepository` не содержит `._require_pool()`;
- оба метода используют публичную границу;
- retry service не изменён;
- baseline равен 84/21;
- полный PR CI зелёный.

### Риски и ограничения

- Telegram download retry behavior не меняется;
- SQL и миграции не меняются;
- Heavy Runtime ТЗ не включается.

## После завершения

### Фактически сделано

Ожидается реализация.

### Миграции и совместимость

Ожидается реализация.

### Проверки

Ожидается реализация и CI.

### PR и commit

Ожидается открытие PR.

### Незавершённое

Реализация и проверки.

### Следующий шаг

Перейти к infrastructure-волне Фазы 18: backup service/runtime и Telegram import persistence отдельными срезами.
