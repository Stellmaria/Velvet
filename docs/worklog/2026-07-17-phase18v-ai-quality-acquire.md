# Сессия: Фаза 18V, PostgreSQL-граница AI quality repository

- Дата: 2026-07-17
- ID: `2026-07-17-phase18v-ai-quality-acquire`
- Линия/фаза: основная линия Velvet Archive, Фаза 18V
- Статус: частично
- Ветка: `agent/phase18v-ai-quality-acquire`
- Базовый commit: `cf83db5a98151e52a16dc601523763c03ca3585a`

## Перед началом

### Цель

Перевести `AIQualityRepository` и его фактически активный schema compatibility facade на публичный `Database.acquire()` и уменьшить private pool baseline с 110 до 100 обращений без изменения lifecycle AI-проверки качества.

### Исходный контекст

Фаза 18U закрыла repository калибровки. `AIQualityRepository` содержит восемь собственных connection point и управляет существующими операциями claim, ready/error transitions, summary, paginated review, detail, owner decision и retry.

Первый CI обнаружил, что `ai_quality_schema_compat.py` при импорте заменяет `list_items()` и `get_item()` двумя schema-compatible функциями. Эти фактически исполняемые функции содержали ещё два private pool access и поэтому были включены в тот же runtime-срез вместо сокрытия долга за заранее рассчитанным baseline.

Изменение улучшает существующий quality-контур: устраняет приватную связь repository и его активного compatibility facade с pool, сохраняя транзакции и SQL. Новая AI-механика, новый provider и новый пользовательский сценарий не добавляются.

### Планируемый объём

- перевести восемь методов repository и две активные compatibility-функции на `self._database.acquire()`;
- сохранить транзакционный claim с seed, stale-processing recovery, `FOR UPDATE SKIP LOCKED` и batch status update;
- сохранить provider/model limits, analysis version, attempts и target mapping;
- сохранить ready/error transitions, JSON report и skip threshold;
- сохранить summary aggregates и mapping `AIQualitySummary`;
- сохранить schema-compatible section conditions, page size 1..10, page clamp, ordering и item mapping;
- сохранить owner decision validation/status guard и retry reset;
- добавить source/runtime regression-тесты ключевых групп операций;
- уменьшить baseline до 100 обращений в 25 production-файлах;
- обновить inventory, project memory, development status и changelog;
- определить следующий repository-срез;
- прогнать полный CI и слить отдельный PR.

### Критерии готовности

- `AIQualityRepository` и `ai_quality_schema_compat.py` не содержат `._require_pool()`;
- source-контракт фиксирует восемь собственных `self._database.acquire()` и две compatibility boundary;
- claim сохраняет одну transaction и четыре SQL-операции при наличии rows;
- ready/error transitions сохраняют аргументы и JSON;
- summary/list/detail сохраняют SQL, pagination и schema-compatible mapping;
- decision/retry сохраняют guards и boolean result;
- baseline равен 100/25;
- tests, Docker build и project notes contract проходят;
- worklog закрыт точными run и следующим шагом.

### Риски и ограничения

- нельзя менять VisionClient, prompts, schemas или AI analysis;
- нельзя менять claim locking и retry semantics;
- нельзя удалять compatibility facade без отдельного import/runtime review;
- нельзя включать `ai_vision.py` или handlers в этот PR;
- нельзя ослаблять baseline;
- миграции и схема базы не изменяются.

## После завершения

### Фактически сделано

- все восемь собственных методов `AIQualityRepository` переведены на `Database.acquire()`;
- production diff `ai_quality.py` содержит ровно 8 добавлений и 8 удалений;
- две фактически исполняемые функции `list_items/get_item` в `ai_quality_schema_compat.py` также переведены на публичную границу;
- prompts, schemas, `QualityVisionClient` и `AIQualityService` не менялись;
- транзакционный claim сохранил seed, stale-processing recovery, locked fetch и batch processing update;
- сохранены `FOR UPDATE OF q SKIP LOCKED`, attempt/limit clamps, provider/model limits и analysis version;
- ready/error transitions, JSON report и permanent/attempt skip semantics сохранены;
- summary aggregates, section conditions, safe pagination, ordering и schema-compatible item mapping не менялись;
- owner decision validation/status guard и полный retry reset сохранены;
- добавлены source/runtime regression-тесты всех групп операций;
- private pool baseline уменьшен с 110 обращений в 27 файлах до 100 обращений в 25 файлах;
- следующим срезом назначена Фаза 18W: repository-контур `ai_vision.py`, 4 connection points;
- inventory, project memory, development status и changelog обновлены.

### Миграции и совместимость

Миграции и схема базы не изменялись. SQL, транзакционная граница claim, lifecycle состояний, prompts, schemas, provider contracts, compatibility mapping и публичные модели сохранены.

### Проверки

Первый CI на head `06d5f7fa1cc20f54a35c643b2b83fb902e06d874`:

- `project notes contract #73` — успешно;
- `docker build #193` — успешно;
- `tests #599` — failure в новых runtime-тестах `list_items/get_item`;
- причина: импортированный `ai_quality_schema_compat.py` подменял методы старыми функциями с `_require_pool()`;
- обнаруженные две runtime boundary переведены на `Database.acquire()`;
- baseline скорректирован с 102/26 до фактических 100/25.

Повторный полный CI ещё не завершён.

### PR и commit

- draft PR: #119 `Фаза 18V: AIQualityRepository и Database.acquire`;
- первый CI head: `06d5f7fa1cc20f54a35c643b2b83fb902e06d874`;
- финальный commit будет зафиксирован после повторного CI и merge.

### Незавершённое

- получить зелёный повторный tests workflow;
- закрыть worklog точными run;
- повторить CI на окончательном head;
- слить Фазу 18V.

### Следующий шаг

Повторить полный CI после перевода compatibility facade. После merge начать Фазу 18W отдельной сессией.
