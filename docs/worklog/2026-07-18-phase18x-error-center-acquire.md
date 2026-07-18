# Сессия: Фаза 18X — ErrorIncidentRepository и Database.acquire

- Дата: 2026-07-18
- ID: `2026-07-18-phase18x-error-center-acquire`
- Линия/фаза: основное развитие Velvet Archive, Фаза 18X
- Статус: завершено
- Ветка: `agent/phase18x-error-center-acquire`
- Базовый commit: `3880e119589543ead3d70f11e598f6cbee1c2562`

## Перед началом

### Цель

Перевести восемь connection point `ErrorIncidentRepository` в `velvet_bot/error_center.py` с приватного `Database._require_pool()` на публичный `Database.acquire()` без изменения error lifecycle и Telegram presentation.

### Исходный контекст

- baseline до работы: 96 внешних обращений в 24 production-файлах;
- целевой модуль: `velvet_bot/error_center.py`, 8 connection points;
- методы: record, set log message, acknowledge, acknowledge all, unacknowledged list/counts, digest due и digest sent.

### Планируемый объём

1. Перевести все восемь repository connection point на `Database.acquire()`.
2. Сохранить transaction/locking, incident reopen, acknowledgment, pagination clamps и digest cooldown.
3. Добавить source/runtime regression-тесты.
4. Уменьшить baseline до 88 обращений в 23 файлах и обновить проектные документы.

### Критерии готовности

- `ErrorIncidentRepository` не содержит `._require_pool()`;
- восемь методов используют публичную границу;
- SQL, mapping и транзакции сохранены;
- baseline равен 88/23;
- полный PR CI зелёный.

### Риски и ограничения

- logging handler и Telegram delivery не изменяются;
- схема и миграции не изменяются;
- Heavy Runtime ТЗ не смешивается с Фазой 18.

## После завершения

### Фактически сделано

- восемь connection point `ErrorIncidentRepository` переведены на `Database.acquire()`;
- сохранены transaction/locking в `record()` и `acknowledge_all()`;
- сохранены incident reopen, logger truncation, row mapping, acknowledgment, list/count clamps и digest cooldown;
- добавлены source/runtime regression-тесты;
- baseline уменьшен с 96/24 до 88/23;
- inventory, project memory, development status и changelog обновлены.

### Миграции и совместимость

- миграции и схема не изменялись;
- SQL и публичные Python-контракты не изменялись;
- logging handler, Telegram delivery и owner digest presentation не изменялись.

### Проверки

- production commit `476d32fa695bbce96fbd58dbae50991a487a0759`: diff содержит только восемь замен private boundary на public boundary;
- PR CI `tests #630`, run `29638902963`: успешно;
- PR CI `docker build #220`, run `29638902945`: успешно;
- PR CI `project notes contract #96`, run `29638902954`: успешно.

### PR и commit

- PR: #126 `Фаза 18X: ErrorIncidentRepository и Database.acquire`;
- production commit: `476d32fa695bbce96fbd58dbae50991a487a0759`;
- проверенный CI head: `7bb287ba217d6f2a6616f36e79bf034dee198b76`.

### Незавершённое

В рамках Фазы 18X незавершённых изменений нет. Живая Telegram-проверка не требуется, потому что delivery и presentation не менялись.

### Следующий шаг

Фаза 18Y: перевести два connection point Ollama vision repository в `ollama_vision.py` на `Database.acquire()`.
