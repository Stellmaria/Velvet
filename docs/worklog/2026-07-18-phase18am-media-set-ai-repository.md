# Сессия: Фаза 18AM — Media-set AI repository boundary

- Дата: 2026-07-18
- ID: `2026-07-18-phase18am-media-set-ai-repository`
- Линия/фаза: основное развитие Velvet Archive, Фаза 18AM
- Статус: частично
- Ветка: `agent/phase18am-media-set-ai-repository`
- Базовый commit: `643c97b5d58c88d5bae29646ac31c9957696c60c`

## Перед началом

### Цель

Убрать два direct persistence connection point из `velvet_bot/media_set_ai_discovery.py`, сохранив semantic grouping в application service и перенеся profile loading и candidate persistence в отдельный `MediaSetAIRepository`.

### Исходный контекст

- baseline до работы: 14 внешних обращений в 8 production-файлах;
- сервис одновременно строил semantic groups и владел двумя SQL-блоками;
- первый SQL загружал ready semantic profiles и character context;
- второй SQL транзакционно retire-ил слабые filename/context proposals, upsert-ил AI candidate и candidate items;
- invalid JSON profiles пропускались;
- discovery сначала запускал штатный fallback detector, затем добавлял AI-created count;
- runtime installer подменял `media_sets.discover_media_set_candidates`.

### Планируемый объём

1. Создать `MediaSetAIRepository` с типизированными read/write DTO.
2. Перенести profile loading в repository.
3. Перенести candidate retirement/upsert transaction в repository.
4. Оставить semantic grouping, title/reason/score и JSON decode в application service.
5. Сохранить fallback discovery и monkeypatch installer.
6. Добавить repository и service regression-тесты.
7. Уменьшить baseline до 12 обращений в 7 файлах.
8. Обновить inventory и проектные документы.

### Критерии готовности

- `media_set_ai_discovery.py` не содержит `_require_pool()` и `database.acquire()`;
- repository содержит ровно два `self._database.acquire()`;
- application service не содержит SQL;
- load limit clamp и row mapping сохранены;
- retirement и candidate/item upserts остаются в одной транзакции;
- empty candidate tuple не retire-ит старые proposals;
- invalid profile JSON пропускается;
- semantic draft fields и item reasons сохраняются;
- fallback short-circuit и суммарный created-count сохранены;
- baseline равен 12/7;
- полный PR CI зелёный.

### Риски и ограничения

- SQL и миграции не изменяются;
- semantic comparison, component grouping и threshold не меняются;
- runtime installer и публичная discovery-функция сохраняются;
- `media_set_actions.py` и другие application/presentation модули остаются следующими отдельными срезами.

## После завершения

### Фактически сделано

- создан `MediaSetAIRepository` с `MediaSetAIContextRow`, `MediaSetAICandidateDraft` и item draft;
- profile loading перенесён в repository с limit clamp 20..1000;
- retirement старых filename/context proposals и candidate/item upsert перенесены в одну repository transaction;
- semantic grouping, title, reason, group/item score и common prompt остались в application service;
- `_load_ai_contexts()` декодирует repository rows и по-прежнему пропускает invalid JSON;
- `_candidate_drafts()` формирует типизированные persistence drafts;
- `_store_ai_candidates()` делегирует repository;
- fallback discovery, short-circuit при менее двух profiles, group building и created-count сохранены;
- runtime installer и публичный API сохранены;
- добавлены repository/service regression-тесты;
- baseline уменьшен с 14/8 до 12/7;
- application-service direct DB access полностью удалён из baseline;
- inventory, project memory, development status и changelog синхронизированы.

### Миграции и совместимость

- миграции и SQL semantics не изменялись;
- публичная функция `discover_media_set_candidates_with_ai()` и installer сохранены;
- semantic thresholds, grouping и title/reason builders не изменялись.

### Проверки

- source regression требует отсутствие direct DB access в service и два public acquire в repository;
- repository tests проверяют load mapping, clamp, retirement transaction, candidate/item upsert и empty input;
- service tests проверяют JSON decode, semantic drafts, repository delegation, fallback short-circuit и итоговый created-count;
- AST baseline ожидает 12 внешних обращений в 7 production-файлах;
- требуется полный PR CI.

### PR и commit

- PR будет создан после синхронизации документации;
- repository commit: `187f090180539b990332e7caa3d2971c79fafeba`;
- service refactor commit: `d96885a4a4596a553122efcba8db4cb6ff65d4a0`;
- regression tests commit: `a68d7f3bdd490da905bb20941dbbc40b7c18f396`.

### Незавершённое

Требуется полный зелёный PR CI и финальное закрытие записи перед merge.

### Следующий шаг

Фаза 18AN: вынести один persistence connection point из `media_set_actions.py` в repository boundary. Ожидаемый baseline: 11 обращений в 6 production-файлах.
