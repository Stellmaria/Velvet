# Сессия: Фаза 18O, PostgreSQL-граница проверки публикаций

- Дата: 2026-07-17
- ID: `2026-07-17-phase18o-publication-validation-acquire`
- Линия/фаза: основная линия Velvet Archive, Фаза 18O
- Статус: в работе
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
