# Сессия: P2B — quality callback acknowledgment

- Дата: 2026-07-18
- ID: `2026-07-18-p2b-quality-callback-ack`
- Линия/фаза: основное развитие Velvet Archive, P2B
- Статус: завершено
- Ветка: `agent/p2b-quality-callback-ack`
- Базовый commit: `324f18a52a4be2f12ce3303ea3f619bd8861d84e`

## Перед началом

### Цель

Закрыть пять оставшихся late callbacks, сохранив mutation-result alert и перенеся тяжёлый UI reload после acknowledgment.

### Исходный контекст

P2A создала baseline: 5 late/missing callbacks в 3 файлах. Все пять выполняли одну mutation/query, затем reload UI и только после этого отвечали Telegram.

### Планируемый объём

1. Переставить acknowledgment в quality AI retry.
2. Переставить acknowledgment в два quality center reset callback.
3. Переставить acknowledgment в два quality operations queue callback.
4. Пересчитать inventory.
5. Добавить source-order regression tests.

### Критерии готовности

- mutation result и alert text сохранены;
- acknowledgment выполняется до reload UI;
- risky callback baseline равен 0;
- полный PR CI зелёный.

### Риски и ограничения

Mutation/query остаётся до acknowledgment, чтобы сохранить точный count/result. Она классифицируется как guarded; тяжёлая перерисовка переносится после ответа.

## После завершения

### Фактически сделано

- пять callbacks переведены из late в guarded;
- callback late/missing baseline уменьшен с 5 до 0;
- общий callback count и payload не изменены;
- добавлены source-order tests;
- inventory, status, memory и changelog синхронизированы.

### Миграции и совместимость

Миграции, callback payload, тексты alert и repository operations не изменялись.

### Проверки

Требуются unit tests, Docker build и project notes contract на финальном head.

### PR и commit

PR создаётся после выполнения подготовительного runner; номер фиксируется финальным connector-коммитом.

### Незавершённое

Остаётся broad-exception baseline: 70 в 43 файлах.

### Следующий шаг

Классифицировать и сузить broad exceptions в `velvet_bot/domains/publication/service.py`.
