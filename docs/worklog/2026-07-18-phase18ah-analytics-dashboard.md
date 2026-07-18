# Сессия: Фаза 18AH — Analytics dashboard и Database.acquire

- Дата: 2026-07-18
- ID: `2026-07-18-phase18ah-analytics-dashboard`
- Линия/фаза: основное развитие Velvet Archive, Фаза 18AH
- Статус: завершено
- Ветка: `agent/phase18ah-analytics-dashboard`
- Базовый commit: `4715c7398e19435deb483b5ffbcc3a024128bc5f`

## Перед началом

### Цель

Перевести восемь connection point в `velvet_bot/analytics_dashboard.py` на публичный `Database.acquire()` без изменения period filters, агрегатов, пагинации и discussion fallback.

### Исходный контекст

- baseline до работы: 53 внешних обращения в 13 production-файлах;
- dashboard overview использует два связанных запроса и объединяет post/hashtag metrics;
- prompt dashboard считает section coverage и среднюю длину;
- hashtag, character и discussion participant lists имеют page-size clamp и нормализацию страницы;
- unresolved hashtag mode динамически добавляет один SQL filter;
- discussion dashboard сохраняет fallback для отсутствующего tracked source.

### Планируемый объём

1. Перевести восемь connection point на `Database.acquire()`.
2. Сохранить period/since arguments и два overview query.
3. Сохранить page clamp, offset/limit и unresolved filter.
4. Сохранить dataclass mapping для всех dashboard экранов.
5. Добавить source/runtime regression-тесты.
6. Уменьшить baseline до 45 обращений в 12 файлах.
7. Обновить inventory и проектные документы.

### Критерии готовности

- `analytics_dashboard.py` не содержит `._require_pool()`;
- модуль содержит ровно восемь вызовов `database.acquire()`;
- compare с базой показывает только восемь замен границы;
- overview, prompt, hashtag, character, post type и discussion mapping сохранены;
- page clamp и unresolved filter проверены runtime-тестами;
- baseline равен 45/12;
- полный PR CI зелёный.

### Риски и ограничения

- SQL и миграции не изменяются;
- временная логика `period_since()` не меняется;
- analytics review и channel analytics остаются отдельными следующими срезами;
- handlers и presentation не затрагиваются.

## После завершения

### Фактически сделано

- все восемь connection point `analytics_dashboard.py` переведены на `Database.acquire()`;
- compare с базовым commit подтвердил ровно 8 additions и 8 deletions в production-файле;
- сохранены overview/relation query и единый since argument;
- сохранены prompt section aggregates и numeric mapping;
- сохранены hashtag/character/participant page clamps, offsets и limits;
- сохранён `unresolved_only` filter в count и list SQL;
- сохранены post type и discussion source mappings;
- сохранён discussion dashboard fallback для отсутствующего tracked source;
- добавлены source/runtime regression-тесты для всех восьми persistence entry points;
- baseline уменьшен с 53/13 до 45/12;
- inventory, project memory, development status и changelog синхронизированы.

### Миграции и совместимость

- миграции и SQL не изменялись;
- публичные Python-сигнатуры и dataclasses не изменялись;
- period normalization и timezone-aware since calculation сохранены.

### Проверки

- source regression запрещает `._require_pool()` и требует восемь `database.acquire()`;
- runtime regression проверяет overview, prompt, hashtag, character, post type, sources, dashboard fallback и participants;
- AST baseline подтверждает 45 внешних обращений в 12 production-файлах;
- GitHub Actions `tests` run 675: success;
- GitHub Actions `docker build` run 260: success;
- GitHub Actions `project notes contract` run 130: success.

### PR и commit

- PR: #137 `Фаза 18AH: Analytics dashboard и Database.acquire`;
- production commit: `1c4a7608aa01f8743f7ee4ea3c4aae83dbefcfea`;
- test commit: `bb943aa31737c7eaae0f05de7dc1d5fbf4a157ad`;
- проверенный connector head до финального закрытия worklog: `f30f5ac63ede7287056a1c1649602979c8a2e965`.

### Незавершённое

Внутри среза незавершённых задач нет. После merge продолжить Фазой 18AI.

### Следующий шаг

Фаза 18AI: analytics review, 9 connection points. Ожидаемый baseline: 36 обращений в 11 production-файлах.
