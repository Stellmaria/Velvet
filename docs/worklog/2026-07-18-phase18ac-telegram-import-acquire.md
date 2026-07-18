# Сессия: Фаза 18AC — Telegram import persistence и Database.acquire

- Дата: 2026-07-18
- ID: `2026-07-18-phase18ac-telegram-import-acquire`
- Линия/фаза: основное развитие Velvet Archive, Фаза 18AC
- Статус: завершено
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

- четыре connection point `telegram_export_import.py` переведены на `Database.acquire()`;
- production diff содержит только четыре точечные замены;
- сохранены tracked-source upsert, discussion existence/list filters, duplicate lookup и одна import transaction;
- добавлены regression-тесты source boundary, upsert arguments, discussion mapping, duplicate short-circuit и transaction/history write;
- private pool baseline уменьшен с 67/19 до 63/18;
- machine inventory, human inventory, project memory, development status и changelog синхронизированы;
- временные generator/workflow файлы полностью удалены из итогового diff.

### Миграции и совместимость

- миграции не изменялись;
- JSON/ZIP parser, publication grouping, hashtag/link extraction, analytics mapping и SQL не изменялись;
- checkpoint/resume/pause не добавлялись и остаются в Heavy Runtime ТЗ.

### Проверки

- точный production diff подтверждает четыре замены private boundary на public boundary;
- локальная проверка сгенерированной копии: 604 строки, 0 private calls, 4 public calls;
- PR CI head `5c95c8bba70365c96b12727acf1a828220ecb54f`:
  - `tests #659`, run `29641586886`: успешно;
  - `docker build #244`, run `29641586888`: успешно;
  - `project notes contract #119`, run `29641586894`: успешно.

### PR и commit

- PR: #131 `Фаза 18AC: Telegram import persistence и Database.acquire`;
- production commit из self-cleaning workflow: `ed3ee9bfcc2e33909eb7df275d6f39203b7265bd`;
- проверенный CI head до финального worklog: `5c95c8bba70365c96b12727acf1a828220ecb54f`.

### Незавершённое

В рамках Фазы 18AC незавершённых изменений нет. Живая Telegram-проверка не требуется, потому что parser, handler и presentation не изменялись.

### Следующий шаг

Фаза 18AD: public media lookup query boundary, 1 connection point, ожидаемый baseline 62/17.
