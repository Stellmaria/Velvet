# Сессия: Фаза 18Z — Resilient AI vision repository и Database.acquire

- Дата: 2026-07-18
- ID: `2026-07-18-phase18z-resilient-ai-acquire`
- Линия/фаза: основное развитие Velvet Archive, Фаза 18Z
- Статус: завершено
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

- оба connection point `ResilientMediaAIRepository.claim_targets()` переведены на `Database.acquire()`;
- сохранены transient Telegram failure requeue, parent claim и обновление `analysis_version = 3`;
- `ResilientMediaAIVisionService` и download retry behavior не изменены;
- добавлены source/runtime regression-тесты для успешного и пустого claim;
- baseline уменьшен с 86/22 до 84/21;
- repository-классы внутри крупных модулей полностью удалены из baseline;
- inventory, project memory, development status и changelog обновлены.

### Миграции и совместимость

- миграции и SQL не изменялись;
- Telegram download retry, timeout и error handling не изменялись;
- публичные Python-контракты не изменялись.

### Проверки

- production commit `d7a4677e1942f7c13aa065695d802002846641d5`: diff содержит только две замены private boundary на public boundary;
- PR CI `tests #636`, run `29639400374`: успешно;
- PR CI `docker build #226`, run `29639400340`: успешно;
- PR CI `project notes contract #100`, run `29639400342`: успешно.

### PR и commit

- PR: #128 `Фаза 18Z: Resilient AI repository и Database.acquire`;
- production commit: `d7a4677e1942f7c13aa065695d802002846641d5`;
- проверенный CI head: `3e0e3104b94af43662fffdd03fdef864faadfad4`.

### Незавершённое

В рамках Фазы 18Z незавершённых изменений нет. Живая Telegram-проверка не требуется, потому что retry service не менялся.

### Следующий шаг

Фаза 18AA: перевести два connection point backup runtime на `Database.acquire()`, затем отдельной Фазой 18AB обработать 15 connection points базового backup service.
