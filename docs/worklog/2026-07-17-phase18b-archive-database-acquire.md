# Сессия: Фаза 18B, публичная PostgreSQL-граница архива

- Дата: 2026-07-17
- ID: `2026-07-17-phase18b-archive-database-acquire`
- Линия/фаза: основная линия Velvet Archive, Фаза 18B
- Статус: завершено
- Ветка: `agent/phase18b-archive-database-acquire`
- Базовый commit: `bc9e1cff00beaa23856285aff8cc0d205f00ceff`

## Перед началом

### Цель

Продолжить P2-перенос repositories с приватного `Database._require_pool()` на публичную границу `Database.acquire()` отдельным безопасным архивным срезом.

### Исходный контекст

Фаза 18A добавила публичный `Database.acquire()` и перевела character/story repositories. В актуальном `main` архивные repositories всё ещё напрямую вызывают приватный `_require_pool()`:

- `velvet_bot/domains/archive/repository.py`;
- `velvet_bot/domains/public_archive/repository.py`.

Оба модуля относятся к одному предметному контуру: карточки архива, изменения медиа, публичные лайки, подписки и уведомления. Массовая замена по всему проекту запрещена архитектурным планом; перенос выполняется доменными срезами.

### Планируемый объём

- перевести `ArchiveRepository` на `self._database.acquire()`;
- перевести `PublicArchiveRepository` на `self._database.acquire()`;
- сохранить существующие SQL, транзакционные границы и возвращаемые модели;
- расширить архитектурный regression-тест Фазы 18;
- добавить/актуализировать PostgreSQL integration tests архивных операций, если текущего покрытия недостаточно;
- обновить карту проекта, development status и changelog;
- после завершения удалить эти repositories из списка оставшегося P2-долга.

### Критерии готовности

- в обоих archive repositories отсутствует `._require_pool()`;
- все соединения открываются через `self._database.acquire()`;
- транзакционные операции удаления, лайков и подписок сохраняют поведение;
- unit- и PostgreSQL integration tests проходят;
- полный CI проходит;
- worklog закрыт фактическими проверками, PR/commit и следующим P2-срезом.

### Риски и ограничения

- механическая замена не должна менять вложенность `transaction()`;
- возвраты изнутри transaction context должны корректно освобождать соединение;
- старые миграции и SQL-запросы не изменяются без необходимости;
- публичные лайки, подписки и notification delivery являются пользовательским поведением и требуют сохранения контрактов;
- остальные repositories остаются отдельным долгом и не включаются в этот PR.

## После завершения

### Фактически сделано

- `ArchiveRepository` переведён на `Database.acquire()` во всех пяти точках получения соединения;
- `PublicArchiveRepository` переведён на `Database.acquire()` во всех семи точках получения соединения;
- SQL-тексты, порядок запросов, вложенные `connection.transaction()` и возвращаемые модели не изменены;
- regression-тест Фазы 18 теперь контролирует characters, stories, archive и public archive repositories;
- карта проекта фиксирует завершение 18B и следующий срез `ReferenceRepository`;
- development status очищен от устаревшей формулировки о внедрении worklog и дополнен фактическим commit PR #96;
- changelog дополнен проектной памятью и текущим составом repositories на публичной границе.

### Миграции и совместимость

Миграции базы отсутствуют. Схема PostgreSQL, SQL-запросы и публичные интерфейсы repositories не менялись. Изменён только способ получения соединения через уже существующий публичный API `Database.acquire()`.

### Проверки

- GitHub compare подтвердил изолированный diff без временных patch/workflow-файлов;
- `project notes contract #3` — успешно;
- полный workflow `tests #508`, включая PostgreSQL integration tests — успешно;
- `docker build #114` — успешно;
- после закрытия этой записи workflows повторно запускаются на финальном head PR.

### PR и commit

- PR: #97 `Фаза 18B: перевести архивные repositories на Database.acquire`;
- проверенный head до закрытия дневника: `e499175d812685b2bb54ac07ce008fcb84746cb9`;
- итоговый squash commit фиксируется GitHub при слиянии PR #97.

### Незавершённое

Обязательных пунктов Фазы 18B не осталось. Эксплуатационные проверки Фазы 20 остаются отдельным обязательством и этим PR не затрагиваются.

### Следующий шаг

Начать Фазу 18C отдельной веткой и worklog: перевести `ReferenceRepository` на `Database.acquire()`, сохранить транзакции добавления/удаления референсов и расширить PostgreSQL-контракты.