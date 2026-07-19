# Актуальный аудит архитектуры Velvet

Дата актуализации: 20 июля 2026 года.

## Объём проверки

Проверены:

- composition root и lifecycle;
- application/use-case слой;
- domain repositories и services;
- PostgreSQL boundaries;
- Telegram Router composition и порядок обработчиков;
- callback acknowledgment;
- широкие exception boundaries;
- compatibility installers и package side effects;
- Supervisor, backup и CI contracts;
- источники истины проекта.

## Итог

Логический рефакторинг основных бизнес- и persistence-границ завершён. Проект использует composition root, application use cases, repositories/services, централизованный WorkerManager и проверенные Telegram/error boundaries.

Физическая структура пакетов остаётся переходной: активные Telegram controllers уже перенесены в `velvet_bot/presentation/telegram/routers`, но 68 старых handler paths сохраняются как module aliases, часть repositories и services расположена в исторических корневых модулях, а несколько runtime compatibility adapters всё ещё нужны до завершения очистки consumers.

## Закрытые архитектурные долги

### Composition root

- `main.py` является короткой точкой входа;
- сборка приложения, ресурсов и workers находится в `velvet_bot/app`;
- root Router создаётся централизованно;
- частично собранные ресурсы безопасно закрываются при ошибках запуска.

### Application layer

- основные owner operations вынесены из Telegram handlers;
- application layer не импортирует aiogram;
- резервные slash-команды используют те же use cases/boundary services, что и кнопки;
- handler-to-handler вызовы через искусственные Telegram objects удалены.

### PostgreSQL boundary

Фаза 18 закрыта:

- исходный baseline: 130 внешних `_require_pool()` в 35 production-файлах;
- текущий baseline: 0/0;
- новые внешние обращения блокируются CI;
- SQL и транзакции основных доменов находятся в repository/query boundaries.

### P2 stability

P2 закрыта:

- 67 broad exception boundaries;
- 67 approved;
- 0 unresolved;
- 97 callback handlers;
- 0 late/missing acknowledgments.

### Telegram contracts

CI контролирует:

- уникальность callback prefixes;
- фактический каталог команд и UI-покрытие;
- отсутствие неожиданных command duplicates;
- единственное владельческое значение `/menu`;
- точную матрицу public/editor/owner;
- порядок catch-all-sensitive routers;
- отсутствие нового SQL в handlers;
- отсутствие внешнего private pool access;
- P2 exception/callback inventory.

### Миграции

- применённые SQL-файлы защищены SHA-256;
- новые дубли номеров запрещены;
- историческая пара `003` остаётся явным исключением;
- старые применённые миграции не редактируются.

## Текущая структура

```text
velvet_bot/
  app/                         composition root и lifecycle
  application/                 transport-neutral owner/use cases
  core/                        config, access и общие contracts
  domains/                     часть канонических domain boundaries
  infrastructure/              Telegram/filesystem/Krita adapters
  presentation/telegram/       root Router, views, contracts и bundles
  repositories/                часть исторических repository implementations
  services/                    application/integration services
  workers/                     WorkerManager и worker boundaries
  handlers/                    68 временных module aliases, 0 implementations
  *.py                         compatibility и исторические domain modules
```

Это рабочая переходная архитектура. Она безопасна по границам, но ещё не соответствует физическому критерию `docs/architecture_target.md`, согласно которому корень должен содержать только общие точки входа и тонкие compatibility facades.

## P3A: источники истины

Необходимо поддерживать согласованность:

- `docs/project_memory.md`;
- `docs/development_status.md`;
- этого аудита;
- `CHANGELOG.md`;
- architecture/stability inventories.

P2 не должна продолжать числиться незавершённой после inventory `67/67`.

## P3B: Telegram Router composition

Корневой Router должен подключать крупные последовательные bundles:

1. core owner/operations;
2. analytics;
3. backup/quality/Velvet AI;
4. archive/public/publication.

Root composition не должен импортировать отдельные `velvet_bot.handlers.*`. Каждый активный handler должен быть зарегистрирован ровно один раз. Publication Router должен оставаться перед archive catch-all.

## P3C: физический перенос presentation

Статус: завершено.

- 68 legacy handler-файлов являются module aliases;
- активных implementations в `velvet_bot/handlers` нет;
- canonical controllers зарегистрированы через четыре ordered bundles;
- callback prefixes, команды и use cases сохранены.

## P3D: compatibility retirement

Статус: выполняется. Legacy-consumer inventory после второго cleanup-среза фиксирует 19 production-файлов, 28 references и 17 старых handler modules. Compatibility должен быть явным, перечисленным и стадийным.

Допустимы временные категории:

- schema adapters;
- UI formatting adapters;
- import-order adapters;
- старые import facades.

Недопустимы:

- скрытые package-level assignments без потребителя;
- неинвентаризированные monkeypatches;
- installer, который невозможно связать с regression-тестом;
- no-op bridge, существующий только потому, что старый тест проверяет его наличие.

Неиспользуемый discussion dashboard package bridge удалён. Оставшиеся active components перечисляются в `velvet_bot/presentation/telegram/compat.py`, а consumers старых handler paths — в `docs/legacy_handler_consumer_inventory.*`.

## P3E: repository layout

Сейчас одновременно существуют:

- `velvet_bot/domains/<domain>/repository.py`;
- `velvet_bot/repositories/*.py`;
- корневые `*_repository.py`.

Целевое правило:

- domain interface/operations находятся внутри домена;
- PostgreSQL-specific implementation может находиться в `infrastructure/postgres`;
- старый путь становится re-export facade и затем удаляется;
- новый repository не создаёт ещё один вариант размещения.

## P3F: статическая типизация

Открытый долг:

- начать с transport-neutral core/application/domains/services/workers;
- использовать ограниченный baseline;
- расширять scope только после зелёного CI;
- не включать strict-mode на весь repository одним PR.

## Эксплуатационные ворота

Кодовая архитектура не может заменить внешнюю проверку. Остаются:

1. живой Supervisor self-restart на Windows;
2. update-and-restart и Telegram bootstrap report;
3. отдельный staging bot/database;
4. независимый restore drill в целевом окружении;
5. encrypted offsite backup;
6. AI duration/error/cost metrics;
7. smoke test основных owner-сценариев после обновления.

## Правило следующих изменений

- новый Telegram handler не получает SQL;
- новая business operation сначала создаётся как use case/domain service;
- новая команда получает кнопку либо явный аварийный статус;
- новый callback получает уникальный typed prefix;
- старый applied SQL не редактируется;
- физический перенос не смешивается с изменением поведения;
- compatibility removal получает regression-тест;
- инфраструктурная возможность не называется production-ready без доступной живой проверки.
