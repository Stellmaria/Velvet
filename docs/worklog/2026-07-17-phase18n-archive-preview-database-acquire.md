# Сессия: Фаза 18N, PostgreSQL-граница preview архива

- Дата: 2026-07-17
- ID: `2026-07-17-phase18n-archive-preview-database-acquire`
- Линия/фаза: основная линия Velvet Archive, Фаза 18N
- Статус: в работе
- Ветка: `agent/phase18n-archive-preview-database-acquire`
- Базовый commit: `80bc02439c7f75758841ab298d4da56c1f4594c0`

## Перед началом

### Цель

Перевести `ArchivePreviewRepository` на публичный `Database.acquire()` и уменьшить машинный baseline private pool debt с 130 до 128 обращений.

### Исходный контекст

Фаза 18M создала AST-инвентаризацию и зафиксировала 130 внешних обращений в 35 production-файлах. Первым срезом выбрана небольшая штатная domain repository с двумя connection points: загрузка и сохранение preview архивного медиа.

Preview относится только к архивному отображению персонажей и медиа. Аукционные карточки, колоды, лоты и торговые состояния к этому домену не относятся.

### Планируемый объём

- изучить SQL и модели `ArchivePreviewRepository.load/save`;
- заменить обе private pool connection points на `self._database.acquire()`;
- сохранить ключи поиска, upsert и mapping результата;
- добавить source/runtime regression-тест public acquire;
- удалить файл repository из machine baseline и пересчитать totals;
- обновить human inventory, project memory, development status и changelog;
- определить следующий repository по очереди.

### Критерии готовности

- `ArchivePreviewRepository` не содержит `._require_pool()`;
- оба метода используют публичную границу базы;
- SQL, параметры, return models и upsert semantics не меняются;
- baseline содержит 128 обращений в 34 production-файлах;
- inventory regression-тест подтверждает уменьшение, а не перенос долга;
- полный tests workflow, Docker build при срабатывании path filters и project notes contract проходят;
- дневник закрыт фактическими run, PR/commit и следующим шагом.

### Риски и ограничения

- нельзя менять формат preview или Telegram media identifiers;
- нельзя включать `PublicationValidationRepository` в этот PR;
- нельзя ослаблять baseline ради зелёного CI;
- нельзя переносить private access в helper или handler;
- старые миграции не изменяются;
- несвязанные дефекты preview фиксируются отдельным долгом.

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