# Сессия: Фаза 18AD — Public media lookup и Database.acquire

- Дата: 2026-07-18
- ID: `2026-07-18-phase18ad-public-media-lookup`
- Линия/фаза: основное развитие Velvet Archive, Фаза 18AD
- Статус: частично
- Ветка: `agent/phase18ad-public-media-lookup`
- Базовый commit: `e0f0c98ff852733b40680e0a56aec16fe2b04c36`

## Перед началом

### Цель

Перевести единственный connection point `get_character_media_offset()` в `velvet_bot/public_media_lookup.py` на публичный `Database.acquire()` без изменения newest-first offset query.

### Исходный контекст

- baseline до работы: 63 внешних обращения в 18 production-файлах;
- модуль содержит одну изолированную query-функцию;
- SQL вычисляет смещение через `ROW_NUMBER()` по `created_at DESC, media_id DESC`;
- публичный контракт возвращает `int | None`.

### Планируемый объём

1. Перевести connection point на `Database.acquire()`.
2. Сохранить character/media filters, порядок сортировки и `None` mapping.
3. Добавить source/runtime regression-тесты.
4. Уменьшить baseline до 62 обращений в 17 файлах.
5. Обновить inventory и проектные документы.

### Критерии готовности

- модуль не содержит `._require_pool()`;
- функция использует один `database.acquire()`;
- SQL и mapping сохранены;
- baseline равен 62/17;
- полный PR CI зелёный.

### Риски и ограничения

- public archive handlers и presentation не меняются;
- SQL не переносится в Telegram handler;
- миграции и Heavy Runtime ТЗ не затрагиваются.

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

Фаза 18AE: discussion thread links и analytics reactions, 2 connection points.
