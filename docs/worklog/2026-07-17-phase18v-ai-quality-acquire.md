# Сессия: Фаза 18V, PostgreSQL-граница AI quality repository

- Дата: 2026-07-17
- ID: `2026-07-17-phase18v-ai-quality-acquire`
- Линия/фаза: основная линия Velvet Archive, Фаза 18V
- Статус: в работе
- Ветка: `agent/phase18v-ai-quality-acquire`
- Базовый commit: `cf83db5a98151e52a16dc601523763c03ca3585a`

## Перед началом

### Цель

Перевести `AIQualityRepository` на публичный `Database.acquire()` и уменьшить private pool baseline с 110 до 102 обращений без изменения lifecycle AI-проверки качества.

### Исходный контекст

Фаза 18U закрыла repository калибровки. `AIQualityRepository` содержит восемь connection point и управляет существующими операциями claim, ready/error transitions, summary, paginated review, detail, owner decision и retry.

Изменение улучшает существующий quality-контур: устраняет приватную связь repository с pool, сохраняя транзакции и SQL. Новая AI-механика, новый provider и новый пользовательский сценарий не добавляются.

### Планируемый объём

- перевести восемь методов repository на `self._database.acquire()`;
- сохранить транзакционный claim с seed, stale-processing recovery, `FOR UPDATE SKIP LOCKED` и batch status update;
- сохранить provider/model limits, analysis version, attempts и target mapping;
- сохранить ready/error transitions, JSON report и skip threshold;
- сохранить summary aggregates и mapping `AIQualitySummary`;
- сохранить section conditions, page size 1..10, page clamp, ordering и item mapping;
- сохранить owner decision validation/status guard и retry reset;
- добавить source/runtime regression-тесты ключевых групп операций;
- уменьшить baseline до 102 обращений в 26 production-файлах;
- обновить inventory, project memory, development status и changelog;
- определить следующий repository-срез;
- прогнать полный CI и слить отдельный PR.

### Критерии готовности

- `AIQualityRepository` не содержит `._require_pool()`;
- source-контракт фиксирует восемь `self._database.acquire()`;
- claim сохраняет одну transaction и четыре SQL-операции при наличии rows;
- ready/error transitions сохраняют аргументы и JSON;
- summary/list/detail сохраняют SQL, pagination и mapping;
- decision/retry сохраняют guards и boolean result;
- baseline равен 102/26;
- tests, Docker build и project notes contract проходят;
- worklog закрыт точными run и следующим шагом.

### Риски и ограничения

- нельзя менять VisionClient, prompts, schemas или AI analysis;
- нельзя менять claim locking и retry semantics;
- нельзя включать `ai_vision.py` или handlers в этот PR;
- нельзя ослаблять baseline;
- миграции и схема базы не изменяются.

## После завершения

### Фактически сделано

Заполняется после реализации.

### Миграции и совместимость

Заполняется после реализации.

### Проверки

Заполняется после реализации.

### PR и commit

Заполняется после реализации.

### Незавершённое

Заполняется после реализации.

### Следующий шаг

Заполняется после реализации.
