# Сессия: Фаза 18P, PostgreSQL-граница черновиков публикаций

- Дата: 2026-07-17
- ID: `2026-07-17-phase18p-publication-draft-acquire`
- Линия/фаза: основная линия Velvet Archive, Фаза 18P
- Статус: частично
- Ветка: `agent/phase18p-publication-draft-acquire`
- Базовый commit: `0b2a539962dd0aa056f581bc436107ae249bf406`

## Перед началом

### Цель

Перевести `PublicationDraftRepository` на публичный `Database.acquire()` и уменьшить private pool baseline с 126 до 118 обращений без изменения существующего lifecycle черновиков.

### Исходный контекст

Фазы 18N–18O закрыли preview и validation repositories. `PublicationDraftRepository` содержит восемь connection point и управляет существующими операциями inbox capture, сборки черновика, spoiler, текста, расписания, отмены и retry.

Изменение улучшает существующий публикационный контур: делает доступ к PostgreSQL единообразным и контролируемым. Новых пользовательских функций и новой предметной области не добавляется.

### Планируемый объём

- перевести все восемь connection point на `self._database.acquire()`;
- сохранить inbox upsert и выбор media group/single message;
- сохранить транзакционное создание draft/items/event;
- сохранить транзакции spoiler, text, schedule и cancel;
- сохранить owner scope, status guards и retry semantics;
- сохранить event payload и последующий reload draft;
- добавить source/runtime regression-тесты ключевых групп операций;
- уменьшить baseline до 118 обращений в 32 production-файлах;
- обновить inventory, project memory, development status и changelog;
- прогнать полный CI и слить отдельный PR.

### Критерии готовности

- repository не содержит `._require_pool()`;
- source-контракт фиксирует восемь `self._database.acquire()`;
- транзакционные методы по-прежнему используют одну connection и одну transaction;
- SQL, параметры, owner scope, status transitions и события сохранены;
- baseline равен 118/32;
- полный tests workflow, Docker build и project notes contract проходят;
- worklog закрыт точными run и следующим срезом.

### Риски и ограничения

- нельзя менять lifecycle публикаций и правила status guards;
- нельзя объединять отдельные SQL-запросы без доказанного улучшения;
- нельзя включать `SystemRepository` в этот PR;
- нельзя ослаблять baseline;
- старые миграции не редактируются;
- найденные несвязанные дефекты получают отдельную запись.

## После завершения

### Фактически сделано

- все восемь методов repository переведены на `Database.acquire()`;
- inbox upsert и group/single source queries сохранены;
- создание draft/items/event остаётся в одной транзакции;
- spoiler, text, schedule и cancel сохраняют отдельные транзакции;
- retry сохраняет status guard `status = 'error'`;
- owner scope, event payload и reload draft не менялись;
- добавлен source-контракт восьми acquire и пяти transactional methods;
- добавлены runtime-тесты inbox capture, empty skip, source mapping, create draft и retry;
- private pool baseline уменьшен с 126/33 до 118/32;
- явные domain repositories удалены из baseline;
- следующим срезом назначена Фаза 18Q: `SystemRepository`;
- inventory, project memory, development status и changelog обновлены.

### Миграции и совместимость

Миграции и схема базы не изменялись. SQL, параметры, status transitions, owner scope, event logging и публичные модели сохранены.

### Проверки

Полный CI ещё не запущен. Добавленные тесты должны подтвердить восемь public acquire, пять транзакционных методов, inbox semantics, создание черновика и retry guard.

### PR и commit

Draft PR ещё не открыт. Head будет зафиксирован после открытия PR и первого CI.

### Незавершённое

- открыть draft PR;
- получить tests, Docker build и project notes contract;
- исправить только фактические регрессии;
- закрыть worklog точными run;
- слить Фазу 18P.

### Следующий шаг

Открыть PR и прогнать полный CI. После merge начать Фазу 18Q отдельной сессией.
