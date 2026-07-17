# Текущий статус разработки Velvet

Дата актуализации: 17 июля 2026 года.

Текущая стабильная версия: `1.3.0`.

## Назначение продукта

Velvet Archive является отдельным архивным ботом для создателя и преимущественно единоличного использования. Его production-домены ограничены персонажами, историями, медиа, референсами, публикациями, аналитикой, AI-проверками и эксплуатацией владельцем.

Аукционный бот является другим продуктом. Его ставки, лоты, колоды, валюты, диапазоны ставок, победители и режимы аукционов не входят в архитектуру Velvet Archive. Это ограничение закреплено в `AGENTS.md` и автоматическом тесте production package.

## Режим стабилизации

До закрытия ворот из `docs/stabilization_policy.md` основной приоритет — привести текущий функционал к понятной, быстрой, надёжной и управляемой архитектуре.

Новый код разрешён только тогда, когда он улучшает существующий продукт: ускоряет сценарий, уменьшает связанность, переносит persistence в правильный слой, добавляет кеш/очередь/batching, диагностику, метрики, staging, backup automation, тесты или документацию. Несвязанные новые предметные механики не добавляются.

## Завершённые функциональные направления

- архив персонажей, медиа и референсов;
- категории, вселенные, истории и несколько историй КР;
- публичный архив, лайки, подписки и уведомления;
- спойлеры, качественные preview и скачивание оригиналов;
- промты материалов и медиасетов;
- визуальные дубли, удаление и группировка в сеты;
- аналитика канала и обсуждений;
- импорт истории Telegram;
- проверка, расписание и отправка публикаций;
- резервные копии и предмиграционная защита;
- WorkerManager, системная диагностика и центр ошибок;
- Velvet Supervisor и Codex workflow;
- безопасная удалённая консоль и self-restart Supervisor;
- Velvet AI, фазы 1–8.

## Фаза 11: hardening и deployment

Статус: завершена.

Реализованы:

- актуальные README, changelog и конфигурация;
- единая матрица Python 3.13 / PostgreSQL 16;
- Dockerfile и Compose для PostgreSQL, бота и Ollama;
- container healthcheck и CI сборки образа;
- автоматический restore drill;
- регулярная CI-проверка восстановления;
- release workflow;
- документация deployment, backup и production checklist.

## Фазы 12–17: архитектурная очистка P1

Статус: завершена.

Реализованы:

- единый presentation-контракт навигации аналитики;
- удаление `handler → handler` импорта между аналитическими контроллерами;
- перенос parent-channel lookup обсуждений в repository/service/query;
- удаление прямого SQL из discussion handler;
- `PublicationActions` как transport-neutral application coordinator;
- перевод центра публикаций с compatibility-фасадов на coordinator и штатный service;
- разделение analytics management на теги, алиасы, классификацию и общий presentation helper;
- сокращение analytics management до тонкого action dispatcher;
- перенос нескольких историй в штатные character/story repositories;
- транзакционная синхронизация `character_story_links` и `characters.story_id`;
- удаление runtime monkeypatch каталогов персонажей и историй;
- разделение владельческих reply-форм на media, profiles, references и data;
- сокращение владельческого reply-controller до action dispatcher;
- перенос ручной классификации на явно типизированный PostgreSQL SQL;
- явное подключение safe analytics edit;
- перенос архивного logging filter в штатный handler;
- удаление вызова legacy compatibility installer из root router;
- преобразование исторических installer-модулей в безопасные no-op фасады;
- постоянные regression-тесты архитектурных границ и compatibility contracts.

## Архитектурный результат версии 1.3.0

Приоритетный P1-долг из аудита закрыт. Улучшающие существующий продукт функции должны добавляться через application/domain/presentation слои без увеличения прежних монолитных контроллеров.

Исторические compatibility-фасады частично остаются для старых импортов, но больше не подменяют функции во время запуска. Они удаляются только после подтверждения отсутствия внешних вызовов.

## Фаза 18: публичная граница PostgreSQL

Статус: срезы 18A–18N реализованы; погашение зафиксированного baseline продолжается.

Реализованы:

- публичный `Database.acquire()` для infrastructure и domain repositories;
- character repository переведён с приватного `_require_pool()`;
- story repository переведён с приватного `_require_pool()`;
- archive repository переведён на публичную границу без изменения SQL и транзакций;
- public archive repository переведён без изменения лайков, подписок и notification delivery;
- reference repository переведён без изменения транзакций, dedup, count, list и пагинации;
- media quality repository переведён без изменения claim locks, fingerprint persistence, duplicate decisions и file-check transitions;
- publication repository переведён без изменения owner scope, draft pagination, queue transitions, event logging и `FOR UPDATE SKIP LOCKED` расписания;
- discussion repository переведён без изменения tracked-channel filters, parent-channel lookup, reaction transaction, overview и participant stats;
- discussion ingest repository переведён без изменения root resolution, character alias lookup, post/hashtag/link transaction и discussion thread matching;
- discussion insight repository переведён без изменения linked-comments CTE, period filters, publication aggregates и `DiscussionSummary`;
- discussion ranking repository переведён без изменения общего `_rank_page`, count/rows SQL, page normalization и `DashboardPage`;
- discussion activity repository переведён без изменения silent-publication CTE, pagination, weekday/hour buckets и daily activity models;
- discussion post insight repository переведён без изменения count/detail CTE, pagination, first-comment delay и `DiscussedPost` mapping;
- discussion relink repository переведён без изменения единой транзакции, root marking, recursive reply tree, exact-text matching, backfill и `RelinkResult`;
- archive preview repository переведён без изменения load/save SQL, Telegram preview fields и `PreviewRecord` mapping;
- AST-инвентаризация сканирует прямые обращения и динамический `getattr(..., "_require_pool")`;
- первоначальный baseline составлял 130 внешних обращений в 35 production-файлах;
- после Фазы 18N baseline составляет 128 обращений в 34 production-файлах;
- baseline хранит count и SHA-256 набора методов для каждого файла и запрещает новый неучтённый долг;
- точные категории и порядок очистки описаны в `docs/private_pool_inventory.md`;
- отдельный AST-контракт запрещает аукционные импорты, классы и идентификаторы в production package.

Следующий срез: Фаза 18O, `PublicationValidationRepository`; ожидаемое уменьшение baseline с 128 до 126 обращений.

## Фаза 19: полный операционный контур Velvet AI

Статус: завершена.

Реализованы:

- восстановлено полное меню управления проверкой качества;
- добавлены кнопки ручной проверки изображения, последних файлов, повторения ошибок, дублей и медиасетов;
- добавлен постоянный PostgreSQL-журнал AI-заданий;
- у задания видны ID, тип, этап, провайдер, модель, результат или причина ошибки;
- зависшие задания автоматически получают статус `interrupted`;
- история доступна отдельной кнопкой из Velvet AI;
- промт/результат, палитра/композиция, оформление, ручная проверка изображения, сравнение с референсом и анализ медиасета используют единый lifecycle;
- сравнение с референсом выполняется кнопочной reply-формой без обязательного `/compare_ref`;
- длительный запуск quality worker подтверждает callback до выполнения;
- regression-тест сопоставляет все literal `quality:` callbacks с реальными handlers;
- PostgreSQL integration test проверяет состояния, ownership, результат, ошибку и прерывание задания;
- callback списка и открытия медиасетов подтверждается до долгих операций;
- протухший callback response Telegram не создаёт ложный ERROR, остальные Bad Request не скрываются.

## Фаза 20: удалённая эксплуатация Supervisor

Статус: реализация завершена; первая живая Windows-проверка остаётся обязательной.

Реализованы:

- единый UTF-8-контракт между Supervisor и дочерним Python-процессом;
- восстановимые `ServerDisconnectedError` polling больше не создают аварийные уведомления;
- стартовый отпечаток показывает PID, каталог, Git HEAD и кодировку;
- безопасная удалённая консоль использует точный allowlist и `shell=False`;
- команда проходит preview, одноразовое подтверждение, таймаут, аудит и маскирование секретов;
- отдельный Windows bootstrap переживает остановку текущего Supervisor;
- self-update допускает только clean tree и fast-forward;
- после обновления выполняются полные тесты, rollback при ошибке и healthcheck нового Supervisor;
- lock-файл блокирует параллельные bootstrap-операции;
- результат сохраняется в истории и отправляется в Telegram;
- код слит PR #95, commit `d49e69daa07e8654638015fde9944ad7d09003cb`.

Эксплуатационно ещё требуется:

1. обновить локальный `main` до `ea3f4eb65e9382c36c15c0dba0d1b3a2d4d339da` или более нового;
2. живая проверка `Перезапустить Supervisor` на целевой Windows;
3. живая проверка `Обновить и перезапустить` на безопасном обновлении;
4. подтверждение success/error отчёта bootstrap в Telegram;
5. проверка основных AI/медиасет-кнопок после обновления.

## Постоянная память проекта

Статус: завершена и расширена режимом стабилизации.

- `docs/project_memory.md` разделяет основную линию и Velvet AI/Qwen, а внешний аукционный проект исключён из активной карты;
- `docs/stabilization_policy.md` определяет допустимый новый код и эксплуатационные ворота;
- каждая рабочая сессия получает отдельный файл `docs/worklog/YYYY-MM-DD-slug.md`;
- перед началом фиксируются цель, контекст, план, критерии готовности и риски;
- после завершения фиксируются фактические изменения, проверки, PR/commit, остаток и следующий шаг;
- `AGENTS.md` делает этот порядок, предметную границу и стабилизационный фильтр обязательными для AI-агентов;
- CI отклоняет содержательный PR без завершённой записи worklog;
- исходный контур памяти слит PR #96, commit `bc9e1cff00beaa23856285aff8cc0d205f00ceff`.

## Оставшийся долг

### P2

1. Выполнить Фазу 18O: перевести `PublicationValidationRepository` и уменьшить baseline до 126 обращений.
2. Затем переводить `PublicationDraftRepository` и `SystemRepository` отдельными срезами.
3. Вынести прямой DB access из handlers в application/domain services.
4. Проверить долгие callback-сценарии и ранний Telegram acknowledgment.
5. Уменьшать широкие `except Exception` внутри бизнес-логики.
6. Добавить автоматическую зашифрованную репликацию backup во внешнее хранилище.
7. Подготовить отдельную staging-конфигурацию и отдельного Telegram-бота.
8. Выполнить backup/restore drill на отдельной тестовой базе.
9. Добавить метрики времени AI-задач и стоимости внешнего provider при его подключении.
10. Вынести статические тексты и клавиатуры крупных presentation-фасадов только там, где это реально уменьшает связанность.

### P3

1. Добавить статический анализ типов без блокировки текущей разработки.
2. Постепенно удалить неиспользуемые корневые compatibility-фасады после миграции всех импортов.
3. Добавить автоматическую публикацию контейнерного образа в закрытый registry.
4. Расширить release notes ссылками на миграции и эксплуатационные изменения.

## Правила дальнейшей разработки

- перед началом задачи создаётся запись в `docs/worklog/`;
- после завершения запись закрывается фактами, проверками, PR/commit и следующим шагом;
- перед переносом старой идеи проверяется, относится ли она к архивному боту, а не к внешнему аукционному проекту;
- новый код обязан улучшать существующую функцию и проходить фильтр `docs/stabilization_policy.md`;
- новый private pool срез обязан уменьшать baseline, а не переносить обращение в другой файл;
- новая команда получает кнопку или явный статус аварийной команды;
- новый callback получает отдельный типизированный префикс;
- старая применённая миграция не редактируется;
- новая бизнес-операция сначала создаётся как use case или domain service;
- handler не выполняет SQL;
- каждый перенос SQL сопровождается PostgreSQL integration test;
- backup-функции считаются проверенными только после restore drill;
- изменение deployment проходит CI до слияния;
- runtime monkeypatch не принимается как постоянная архитектура;
- новая фаза всегда указывает линию, чтобы не смешивать основную разработку и Velvet AI/Qwen.
