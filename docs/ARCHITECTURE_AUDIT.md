# Актуальный аудит архитектуры Velvet

Дата актуализации: 21 июля 2026 года.

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

Физическая структура пакетов остаётся переходной только по 110 историческим root modules и 8 explicit runtime compatibility-компонентам. Активные Telegram controllers перенесены в `velvet_bot/presentation/telegram/routers`, старые handler paths и aliases удалены полностью, а все repositories размещены в domain либо PostgreSQL infrastructure boundary.

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

P2 закрыта. Актуальный generated baseline:

- 76 broad exception boundaries;
- 76 approved;
- 0 unresolved;
- 98 callback handlers;
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
  domains/                     30 канонических repository boundaries
  infrastructure/              PostgreSQL/Telegram/filesystem/Krita adapters
  presentation/telegram/       root Router, views, contracts и 4 bundles
  services/                    application/integration services
  workers/                     WorkerManager и worker boundaries
  *.py                         110 исторических root modules для классификации
```

Handler compatibility слой и central/root repositories уже удалены. Оставшаяся физическая работа касается классификации root modules и 8 explicit runtime compatibility-компонентов, а не восстановления старых путей.

## P3A: источники истины

Статус: завершено. Status, memory, audit, changelog и inventories синхронизированы с `main`.

## P3B: Telegram Router composition

Статус: завершено. Четыре ordered bundles содержат 60 активных routers без дублей; root composition не импортирует legacy handlers.

## P3C: физический перенос presentation

Статус: завершено. Legacy handler-файлов, implementations и aliases осталось 0.

## P3D: compatibility retirement

Handler compatibility retirement завершён. Старые handler paths не имеют consumers и удалены. Остаются 8 explicit runtime compatibility-компонентов: 7 pre-import и 1 post-import. Каждый дальнейший компонент должен стать постоянным contract либо быть удалён вместе с regression-тестом.

## P3E: repository layout

Статус: завершено.

- repository modules: 31;
- domain: 30;
- infrastructure/postgres: 1;
- central: 0;
- root: 0;
- пакет `velvet_bot/repositories` отсутствует.

## P3F: статическая типизация

Следующий кодовый срез:

- выбрать один transport-neutral package;
- создать ограниченный mypy/pyright baseline;
- блокировать новые typing errors в выбранном scope;
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
