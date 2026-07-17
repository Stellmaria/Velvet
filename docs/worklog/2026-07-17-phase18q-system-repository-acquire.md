# Сессия: Фаза 18Q, PostgreSQL-граница системной диагностики

- Дата: 2026-07-17
- ID: `2026-07-17-phase18q-system-repository-acquire`
- Линия/фаза: основная линия Velvet Archive, Фаза 18Q
- Статус: завершено
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

- `ping()` и `get_runtime_snapshot()` переведены на `Database.acquire()`;
- `SELECT 1` и read-only snapshot SQL сохранены;
- mapping `RuntimeDatabaseSnapshot` и nullable backup/schema fields не менялись;
- добавлены source/runtime-тесты ping, полного snapshot и отсутствующего row;
- private pool baseline уменьшен с 118 обращений в 32 файлах до 116 обращений в 31 файле;
- явный infrastructure repository удалён из baseline;
- следующим срезом назначена Фаза 18R: `PromptResultReportRepository`;
- inventory, project memory, development status и changelog обновлены.

### Миграции и совместимость

Миграции и схема базы не изменялись. Диагностические метрики, SQL, модели и публичные методы сохранены.

### Проверки

На head `fa3168ec66dbb72c0f79db67c043fe120c3ed3b2` успешно завершены:

- `project notes contract #53`;
- `docker build #168`;
- полный workflow `tests #574` с PostgreSQL 16.

После этой итоговой записи CI запускается повторно на финальном head перед merge.

### PR и commit

- PR: #113 `Фаза 18Q: SystemRepository и Database.acquire`;
- зелёный промежуточный head: `fa3168ec66dbb72c0f79db67c043fe120c3ed3b2`;
- финальный squash commit фиксируется GitHub при слиянии PR #113.

### Незавершённое

Обязательных пунктов Фазы 18Q не осталось. Живые эксплуатационные проверки Supervisor, staging и независимый backup/restore drill остаются отдельными стабилизационными воротами.

### Следующий шаг

Начать Фазу 18R: перевести `PromptResultReportRepository` на `Database.acquire()` отдельным worklog/PR и уменьшить baseline с 116 до 115 обращений.
