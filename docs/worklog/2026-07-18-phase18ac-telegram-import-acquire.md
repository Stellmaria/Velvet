# Сессия: Фаза 18AC — Telegram import persistence и Database.acquire

- Дата: 2026-07-18
- ID: `2026-07-18-phase18ac-telegram-import-acquire`
- Линия/фаза: основное развитие Velvet Archive, Фаза 18AC
- Статус: частично
- Ветка: `agent/phase18ac-telegram-import-acquire`
- Базовый commit: `d3a3633aad512a44ee19f74711099eb9826a8480`

## Перед началом

### Цель

Перевести четыре connection point Telegram export/import persistence в `velvet_bot/telegram_export_import.py` с приватного `Database._require_pool()` на публичный `Database.acquire()` без изменения JSON/ZIP parser, SHA-256 dedup и атомарности импорта.

### Исходный контекст

- baseline до работы: 67 внешних обращений в 19 production-файлах;
- целевой модуль: `velvet_bot/telegram_export_import.py`, 4 connection points;
- функции покрывают регистрацию источника, проверку/список discussion sources и основной импорт;
- основной импорт выполняет duplicate lookup и запись данных через один connection, а изменения данных помещает в одну transaction.

### Планируемый объём

1. Перевести четыре connection point на `Database.acquire()`.
2. Сохранить source-kind validation, tracked-source upsert и discussion filters.
3. Сохранить SHA-256 duplicate short-circuit и одну import transaction.
4. Добавить source/runtime regression-тесты.
5. Уменьшить baseline до 63 обращений в 18 файлах и обновить документы.

### Критерии готовности

- модуль не содержит внешних `._require_pool()`;
- ровно четыре блока используют `database.acquire()`;
- parser, record grouping, duplicate summary и transaction boundaries не изменены;
- baseline равен 63/18;
- полный PR CI зелёный.

### Риски и ограничения

- импорт не разбивается на несколько независимых транзакций;
- checkpoint/resume/pause относится к Heavy Runtime ТЗ и сюда не включается;
- формат Telegram Desktop JSON/ZIP и analytics mapping не меняются;
- миграции не изменяются.

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

Перейти к старым query-модулям Фазы 18 отдельными архитектурными срезами.
