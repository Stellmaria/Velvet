# Сессия: Фаза 18N, PostgreSQL-граница preview архива

- Дата: 2026-07-17
- ID: `2026-07-17-phase18n-archive-preview-database-acquire-v2`
- Линия/фаза: основная линия Velvet Archive, Фаза 18N
- Статус: частично
- Ветка: `agent/phase18n-archive-preview-acquire-v2`
- Базовый commit: `ea3f4eb65e9382c36c15c0dba0d1b3a2d4d339da`

## Перед началом

### Цель

Перевести `ArchivePreviewRepository` на публичный `Database.acquire()` и уменьшить машинный baseline private pool debt с 130 до 128 обращений, сохранив поведение существующего архива.

### Исходный контекст

Фаза 18M создала AST-инвентаризацию и зафиксировала 130 внешних обращений в 35 production-файлах. Первым срезом выбрана небольшая штатная domain repository с двумя connection points: загрузка и сохранение preview архивного медиа.

Первоначальная ветка 18N разошлась с `main` после production-hotfix callback медиасетов. Чтобы не переносить изменения через force/reset, работа начата заново от актуального `main`.

Пользователь уточнил режим стабилизации: новый код разрешён, если он улучшает скорость, простоту, надёжность, управляемость, тестируемость или удобство существующих функций Velvet Archive. Расширение предметной области и несвязанные новые механики до завершения стабилизации не допускаются.

### Планируемый объём

- заменить обе private pool connection points `ArchivePreviewRepository.load/save` на `self._database.acquire()`;
- сохранить SQL, параметры, mapping и preview semantics;
- добавить source/runtime regression-тест public acquire;
- удалить repository из machine baseline и пересчитать totals;
- актуализировать human inventory и следующий срез;
- закрепить уточнённый режим стабилизации в правилах проекта;
- обновить project memory, development status и changelog;
- прогнать полный CI и слить отдельный PR.

### Критерии готовности

- `ArchivePreviewRepository` не содержит `._require_pool()`;
- оба метода используют публичную границу базы;
- SQL, параметры и модели результата не меняются;
- baseline содержит 128 обращений в 34 production-файлах;
- inventory regression-тест подтверждает уменьшение, а не перенос долга;
- правила проекта разрешают только улучшающий существующий продукт новый код;
- полный tests workflow, Docker build при срабатывании filters и project notes contract проходят;
- дневник закрыт фактическими run, PR/commit и следующим шагом.

### Риски и ограничения

- нельзя менять формат preview или Telegram media identifiers;
- нельзя включать `PublicationValidationRepository` в этот PR;
- нельзя ослаблять baseline ради зелёного CI;
- нельзя переносить private access в helper или handler;
- нельзя добавлять новую предметную механику;
- старые миграции не изменяются;
- несвязанные дефекты фиксируются отдельным hotfix/worklog.

## После завершения

### Фактически сделано

- чистая ветка создана от актуального `main` после hotfix #109;
- `ArchivePreviewRepository.load()` и `save()` переведены на `Database.acquire()`;
- SQL, аргументы и mapping `PreviewRecord` не изменялись;
- добавлен source/runtime regression-тест обоих методов;
- private pool baseline уменьшен с 130/35 до 128/34;
- следующим срезом назначена Фаза 18O: `PublicationValidationRepository`;
- добавлен `docs/stabilization_policy.md`;
- `AGENTS.md` требует обоснования любого нового кода через улучшение существующей функции;
- changelog обновлён.

### Миграции и совместимость

Миграции и схема базы не изменялись. Telegram `file_id`, preview fields, SQL и публичный контракт repository сохранены. Изменена только инфраструктурная граница получения соединения.

### Проверки

- source/runtime-тесты добавлены, полный CI ещё не запущен;
- machine baseline обновлён и должен быть подтверждён inventory regression-тестом;
- project notes contract будет запущен после открытия draft PR.

### PR и commit

Draft PR ещё не открыт. Текущий head ветки будет зафиксирован после синхронизации project memory/development status и первого CI.

### Незавершённое

- обновить `docs/project_memory.md` и `docs/development_status.md`;
- открыть draft PR;
- получить результаты tests, Docker build и project notes contract;
- закрыть дневник точными run и merge commit;
- слить Фазу 18N.

### Следующий шаг

Синхронизировать статус проекта, открыть PR и прогнать полный CI. После слияния начать Фазу 18O для `PublicationValidationRepository` отдельным worklog/PR.
