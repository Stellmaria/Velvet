# Сессия: Фаза 18O, PostgreSQL-граница проверки публикаций

- Дата: 2026-07-17
- ID: `2026-07-17-phase18o-publication-validation-acquire`
- Линия/фаза: основная линия Velvet Archive, Фаза 18O
- Статус: завершено
- Ветка: `agent/phase18o-publication-validation-acquire`
- Базовый commit: `ffee8ebeeb308b34b8ac93ff9d5c3f4549c78ef4`

## Перед началом

### Цель

Перевести `PublicationValidationRepository` на публичный `Database.acquire()` и уменьшить private pool baseline с 128 до 126 обращений без изменения существующей проверки публикаций.

### Исходный контекст

Фаза 18N перевела archive preview repository и закрепила режим стабилизации. Следующий минимальный domain-срез содержит два connection point: чтение контекста проверки и транзакционное сохранение результата.

Изменение улучшает существующую функцию проверки публикаций: делает persistence boundary единообразной и контролируемой. Это не новая предметная область и не добавление нового пользовательского сценария.

### Планируемый объём

- заменить два вызова private pool на `self._database.acquire()`;
- сохранить запросы персонажей, дублей черновиков и публикаций;
- сохранить транзакцию update + publication event;
- сохранить owner scope, JSON report и status transitions;
- добавить source/runtime regression-тесты;
- уменьшить baseline до 126 обращений в 33 production-файлах;
- обновить inventory, project memory, development status и changelog;
- прогнать полный CI и слить отдельный PR.

### Критерии готовности

- repository не содержит `._require_pool()`;
- `load_context()` и `save_result()` используют публичную границу;
- `save_result()` сохраняет одну транзакцию и два SQL-вызова;
- mapping `PublicationValidationContext` и result draft не меняется;
- baseline равен 126/33;
- полный tests workflow, Docker build и project notes contract проходят;
- worklog закрыт точными run и следующим срезом.

### Риски и ограничения

- нельзя менять правила валидации и severity counts;
- нельзя менять owner scope или event payload;
- нельзя включать `PublicationDraftRepository` в этот PR;
- нельзя ослаблять inventory baseline;
- старые миграции не изменяются;
- несвязанные улучшения фиксируются отдельной сессией.

## После завершения

### Фактически сделано

- `load_context()` и `save_result()` переведены на `Database.acquire()`;
- запросы персонажей, дубликатов и channel posts сохранены;
- транзакция update draft + insert publication event сохранена;
- owner scope, severity counts, validation status и JSON payload не менялись;
- добавлены source/runtime regression-тесты чтения и сохранения;
- private pool baseline уменьшен с 128 обращений в 34 файлах до 126 обращений в 33 файлах;
- следующим срезом назначена Фаза 18P: `PublicationDraftRepository`;
- project memory и development status сокращены без удаления фаз, обязательств и product boundary;
- inventory и changelog обновлены.

### Миграции и совместимость

Миграции и схема базы не изменены. Публичные модели, SQL, параметры, transaction scope и event payload сохранены.

### Проверки

Первый CI на head `a974db24fb9c43e1214dd2bed8a1f32a4f68dc8d`:

- `project notes contract #47` — успешно;
- `docker build #160` — успешно;
- `tests #566` — один failure в release documentation contract;
- все repository/inventory тесты прошли;
- причина: каноническая строка стабильной версии была сокращена при редактировании документации.

После восстановления release-формулировки на head `30202c8ffc692aa32ca26ab3f331ce101ac99dc3` успешно завершены:

- `project notes contract #49`;
- `docker build #162`;
- полный workflow `tests #568` с PostgreSQL 16.

После этой итоговой записи CI запускается ещё раз на финальном head перед merge.

### PR и commit

- PR: #111 `Фаза 18O: PublicationValidationRepository и Database.acquire`;
- зелёный промежуточный head: `30202c8ffc692aa32ca26ab3f331ce101ac99dc3`;
- финальный squash commit фиксируется GitHub при слиянии PR #111.

### Незавершённое

Обязательных пунктов Фазы 18O не осталось. Живые эксплуатационные проверки Supervisor, staging и независимый backup/restore drill остаются отдельными стабилизационными воротами.

### Следующий шаг

Начать Фазу 18P: перевести `PublicationDraftRepository` на `Database.acquire()` отдельным worklog/PR и уменьшить baseline с 126 до 118 обращений.
