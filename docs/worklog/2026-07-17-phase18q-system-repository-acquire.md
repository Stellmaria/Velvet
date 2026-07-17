# Сессия: Фаза 18Q, PostgreSQL-граница системной диагностики

- Дата: 2026-07-17
- ID: `2026-07-17-phase18q-system-repository-acquire`
- Линия/фаза: основная линия Velvet Archive, Фаза 18Q
- Статус: в работе
- Ветка: `agent/phase18q-system-repository-acquire`
- Базовый commit: `ee826c7689af8d8d29e6e02ec0092bdcdc90a94a`

## Перед началом

### Цель

Перевести `SystemRepository` на публичный `Database.acquire()` и уменьшить private pool baseline с 118 до 116 обращений без изменения системной диагностики.

### Исходный контекст

Фаза 18P закрыла явные domain repositories. Следующий малый infrastructure-срез содержит `ping()` и read-only snapshot PostgreSQL, публикаций, качества файлов и backup.

Изменение улучшает существующую диагностику: устраняет приватную связь с pool и делает infrastructure boundary единообразной. Новый пользовательский функционал не добавляется.

### Планируемый объём

- перевести `ping()` и `get_runtime_snapshot()` на `self.database.acquire()`;
- сохранить `SELECT 1` и сводный read-only SQL;
- сохранить mapping `RuntimeDatabaseSnapshot` и обработку nullable backup/schema fields;
- добавить source/runtime regression-тесты;
- уменьшить baseline до 116 обращений в 31 production-файле;
- обновить inventory, project memory, development status и changelog;
- определить следующую волну repository-классов;
- прогнать полный CI и слить отдельный PR.

### Критерии готовности

- repository не содержит `._require_pool()`;
- оба метода используют публичную границу;
- ping, snapshot SQL и mapping не меняются;
- baseline равен 116/31;
- полный tests workflow, Docker build и project notes contract проходят;
- worklog закрыт точными run и следующим срезом.

### Риски и ограничения

- нельзя менять диагностические метрики в этом PR;
- нельзя добавлять новые запросы или кеширование без отдельного измерения;
- нельзя включать AI/quality repositories в этот срез;
- нельзя ослаблять baseline;
- старые миграции не редактируются.

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
