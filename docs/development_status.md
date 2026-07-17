# Текущий статус разработки Velvet

Дата актуализации: 17 июля 2026 года.

Текущая стабильная версия: `1.3.0`.

## Назначение продукта

Velvet Archive является отдельным архивным ботом для создателя и преимущественно единоличного использования. Его production-домены ограничены персонажами, историями, медиа, референсами, публикациями, аналитикой, AI-проверками и эксплуатацией владельцем.

Аукционный бот является другим продуктом. Его ставки, лоты, колоды, валюты, диапазоны ставок, победители и режимы аукционов не входят в архитектуру Velvet Archive. Это ограничение закреплено в `AGENTS.md` и автоматическом тесте production package.

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

Приоритетный P1-долг из аудита закрыт. Новые функции могут добавляться через application/domain/presentation слои без увеличения прежних монолитных контроллеров.

Исторические compatibility-фасады частично остаются для старых импортов, но больше не подменяют функции во время запуска. Они удаляются только после подтверждения отсутствия внешних вызовов.

## Фаза 18: публичная граница PostgreSQL

Статус: срезы 18A–18H реализованы; P2-перенос продолжается.

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
- десять завершённых repositories защищены source/runtime regression-тестами от возврата приватного pool access;
- отдельный AST-контракт запрещает аукционные импорты, классы и идентификаторы в production package.

Следующий срез: `DiscussionRankingRepository`.

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
- PostgreSQL integration test проверяет состояния, ownership, результат, ошибку и прерывание задания.

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

1. один последний локальный refresh старого Supervisor до commit `d49e69d`, если он ещё не выполнен;
2. живая проверка `Перезапустить Supervisor` на целевой Windows;
3. живая проверка `Обновить и перезапустить` на безопасном обновлении;
4. подтверждение success/error отчёта bootstrap в Telegram.

## Постоянная память проекта

Статус: завершена.

- `docs/project_memory.md` разделяет основную линию и Velvet AI/Qwen, а внешний аукционный проект исключён из активной карты;
- каждая рабочая сессия получает отдельный файл `docs/worklog/YYYY-MM-DD-slug.md`;
- перед началом фиксируются цель, контекст, план, критерии готовности и риски;
- после завершения фиксируются фактические изменения, проверки, PR/commit, остаток и следующий шаг;
- `AGENTS.md` делает этот порядок и предметную границу обязательными для AI-агентов;
- CI отклоняет содержательный PR без завершённой записи worklog;
- контур слит PR #96, commit `bc9e1cff00beaa23856285aff8cc0d205f00ceff`.

## Оставшийся долг

### P2

1. Продолжить Фазу 18 с `DiscussionRankingRepository`; characters, stories, archive, public archive, references, media quality, publication, discussions, discussion ingest и discussion insight завершены.
2. Уменьшать широкие `except Exception` внутри бизнес-логики.
3. Добавить автоматическую зашифрованную репликацию backup во внешнее хранилище.
4. Подготовить отдельную staging-конфигурацию и отдельного Telegram-бота.
5. Добавить метрики времени AI-задач и стоимости внешнего provider при его подключении.
6. Вынести статические тексты и клавиатуры крупных presentation-фасадов только там, где это реально уменьшает связанность.

### P3

1. Добавить статический анализ типов без блокировки текущей разработки.
2. Постепенно удалить неиспользуемые корневые compatibility-фасады после миграции всех импортов.
3. Добавить автоматическую публикацию контейнерного образа в закрытый registry.
4. Расширить release notes ссылками на миграции и эксплуатационные изменения.

## Правила дальнейшей разработки

- перед началом задачи создаётся запись в `docs/worklog/`;
- после завершения запись закрывается фактами, проверками, PR/commit и следующим шагом;
- перед переносом старой идеи проверяется, относится ли она к архивному боту, а не к внешнему аукционному проекту;
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
