# Сессия: Фаза 18AJ — Channel analytics и Database.acquire

- Дата: 2026-07-18
- ID: `2026-07-18-phase18aj-channel-analytics`
- Линия/фаза: основное развитие Velvet Archive, Фаза 18AJ
- Статус: завершено
- Ветка: `agent/phase18aj-channel-analytics`
- Базовый commit: `521b8cc9d4af6f2621e596054433a471c5030268`

## Перед началом

### Цель

Перевести восемь connection point в `velvet_bot/channel_analytics.py` на публичный `Database.acquire()` без изменения парсинга Telegram-поста, ingest-транзакции и статистических запросов канала.

### Исходный контекст

- baseline до работы: 36 внешних обращений в 11 production-файлах;
- `ingest_channel_post()` в одной транзакции обновляет tracked channel и post, заменяет hashtag/link children и связывает распознанные character hashtags;
- channel overview объединяет три независимых агрегата;
- hashtag, character, prompt, media и link statistics используют собственные row mappings;
- list queries ограничивают пользовательский limit безопасными диапазонами.

### Планируемый объём

1. Перевести восемь connection point на `Database.acquire()`.
2. Сохранить parse result и полную ingest transaction.
3. Сохранить replacement старых hashtag/link children.
4. Сохранить character hashtag mapping и link persistence.
5. Сохранить overview и все статистические row mappings.
6. Сохранить normalization и limit clamps.
7. Добавить source/runtime regression-тесты.
8. Уменьшить baseline до 28 обращений в 10 файлах.
9. Обновить inventory и проектные документы.

### Критерии готовности

- `channel_analytics.py` не содержит `._require_pool()`;
- модуль содержит ровно восемь вызовов `database.acquire()`;
- compare с базой показывает только восемь замен границы;
- ingest выполняется внутри одного transaction context;
- tracked/post upsert, child delete и hashtag/link inserts проверены;
- overview использует три aggregate query и сохраняет mapping;
- stat mappings, normalization и limit clamps проверены runtime-тестами;
- baseline равен 28/10;
- полный PR CI зелёный.

### Риски и ограничения

- SQL и миграции не изменяются;
- parsing helpers и prompt heuristics не меняются;
- публичные dataclasses и сигнатуры сохраняются;
- handlers и presentation не затрагиваются;
- quality audit остаётся следующим отдельным срезом.

## После завершения

### Фактически сделано

- все восемь connection point `channel_analytics.py` переведены на `Database.acquire()`;
- compare с базовым commit подтвердил ровно 8 additions и 8 deletions в production-файле;
- сохранены parsing result и единая ingest transaction;
- сохранены tracked channel/post upsert, child replacement и error guard для отсутствующего post id;
- сохранены character hashtag mapping и link persistence;
- сохранены три channel overview aggregates и полный dataclass mapping;
- сохранены hashtag list/detail, character usage, prompt structure, media type и link domain mappings;
- сохранены hashtag normalization и limit clamps;
- добавлены source/runtime regression-тесты для всех восьми persistence entry points;
- baseline уменьшен с 36/11 до 28/10;
- inventory, project memory, development status и changelog синхронизированы.

### Миграции и совместимость

- миграции и SQL не изменялись;
- публичные Python-сигнатуры и dataclasses не изменялись;
- parsing helpers и prompt scoring сохранены.

### Проверки

- source regression запрещает `._require_pool()` и требует восемь `database.acquire()`;
- runtime regression проверяет ingest transaction, overview, hashtag list/detail, character usage, prompt structure и named-count queries;
- AST baseline подтверждает 28 внешних обращений в 10 production-файлах;
- GitHub Actions `tests` run 681: success;
- GitHub Actions `docker build` run 266: success;
- GitHub Actions `project notes contract` run 134: success.

### PR и commit

- PR: #139 `Фаза 18AJ: Channel analytics и Database.acquire`;
- production commit: `82738a8f79c299862d9fc67b142860643bd9e66a`;
- test commit: `2026e082d079c7c920ae8dc090790bb873576c40`;
- synchronized branch head до финального worklog: `118a2434d7994776541c9da389ecd5ea646b4aff`.

### Незавершённое

Нет незавершённых задач внутри среза. Живая проверка ingestion и аналитических экранов остаётся частью общего эксплуатационного smoke test.

### Следующий шаг

Фаза 18AK: quality audit, 5 connection points. Ожидаемый baseline: 23 обращения в 9 production-файлах.
