# Текущий статус разработки Velvet

Дата актуализации: 18 июля 2026 года.

Текущая стабильная версия: `1.3.0`.

## Назначение

Velvet Archive — owner-oriented архивный Telegram-бот. Его домены: персонажи, истории, медиа, референсы, публикации, аналитика, AI-проверки и эксплуатация владельцем.

Аукционный бот является отдельным продуктом. Его ставки, лоты, колоды, валюты и режимы торгов в Velvet Archive не входят.

## Режим стабилизации

Приоритет определяется `docs/stabilization_policy.md`:

- стабилизировать и упростить существующий функционал;
- улучшать скорость, надёжность, контроль и читаемость;
- добавлять новый код только как улучшение существующего сценария;
- не расширять предметную область без отдельного плана после стабилизации.

## Существующий функционал

- архив персонажей, историй, медиа и референсов;
- категории, вселенные и несколько историй;
- публичный архив, лайки, подписки и уведомления;
- preview и оригиналы изображений;
- промты, медиасеты и визуальные дубли;
- аналитика канала и обсуждений;
- импорт истории Telegram;
- проверка, расписание и отправка публикаций;
- backup и restore drill;
- WorkerManager, диагностика и центр ошибок;
- Velvet AI;
- Supervisor, Codex workflow и безопасная удалённая консоль.

## Production foundation

Завершены:

- Python 3.13 и PostgreSQL 16;
- Dockerfile и Docker Compose;
- container healthcheck и Docker CI;
- автоматический restore drill;
- release workflow;
- production checklist;
- стабильный релиз `1.3.0`.

## Архитектурная очистка P1

Фазы 12–17 завершены:

- SQL удалён из части handlers;
- publication operations используют `PublicationActions`;
- analytics management и owner forms разделены;
- multi-story использует domain repositories;
- runtime monkeypatch удалён;
- compatibility installers превращены в безопасные фасады/no-op;
- добавлены архитектурные regression-тесты.

## Фаза 18: публичная PostgreSQL-граница

Статус: завершена, private-pool baseline 0/0.

Переведены на `Database.acquire()` либо отдельные repository boundaries:

- character и story repositories;
- archive и public archive;
- reference;
- media quality;
- publication repository;
- полный discussion-контур;
- archive preview;
- publication validation;
- publication draft;
- system diagnostics repository;
- prompt/result report repository;
- palette/composition report repository;
- Velvet formatting report repository;
- quality calibration repository;
- AI quality repository и его активный schema compatibility facade;
- Media AI repository в `ai_vision.py`;
- Error Incident repository в `error_center.py`;
- Reliable Media AI repository в `ollama_vision.py`;
- Resilient Media AI repository в `resilient_ai_vision.py`;
- runtime-hardened Backup Service в `backup_runtime.py`;
- базовый Backup Service в `backup_service.py`;
- Telegram import persistence в `telegram_export_import.py`;
- public media lookup query в `public_media_lookup.py`;
- discussion thread links в `discussion_thread_links.py`;
- analytics reaction persistence в `analytics_reactions.py`;
- alias management queries в `alias_management.py`;
- полный character alias persistence в `character_aliases.py`;
- analytics dashboard queries в `analytics_dashboard.py`;
- analytics review queries и classification workflows в `analytics_review.py`;
- channel post ingest и channel statistics в `channel_analytics.py`;
- quality summary, issue pages и reset workflow в `quality_audit.py`;
- полный media-set candidate, create, duplicate-conversion и deletion workflow в `media_sets.py`;
- `MediaSetAIRepository` для semantic profile loading и candidate persistence.

Контракты сохранены:

- lifecycle публикаций и owner scope;
- SQL, транзакции и event logging;
- runtime diagnostics и AI-report arguments;
- calibration filters, formulas и pagination;
- транзакционный AI quality claim с seed, stale recovery и `FOR UPDATE SKIP LOCKED`;
- provider/model limits, attempts, analysis version и target mapping;
- ready/error transitions, JSON report и skip threshold;
- schema-compatible summary/list/detail, page clamp и item mapping;
- owner decision validation/status guard и полный retry reset;
- Media AI claim transaction, semantic profile persistence и aggregate summary;
- error incident transaction/locking, reopen, acknowledgment, list/count clamps и digest cooldown;
- Ollama legacy JSON-error requeue и transient Telegram failure requeue с parent claim и response-version updates;
- backup expected-table decode, timezone/date schedule check, running/completed/failed lifecycle, history, settings, validation и retention;
- pending discussion-thread linking, affected-row mapping, reaction cleaning, JSONB payload и boolean update result;
- alias lookup mapping, protected name aliases, delete delegation и character summary short-circuit;
- name-alias seeding, ordered listing, validation/conflict handling, hashtag linking/unlinking и транзакционный rebuild;
- analytics period filters, overview/prompt aggregates, page clamps, unresolved hashtag filters, rank-item mapping и discussion fallback;
- analytics review tokens, unresolved-tag/publication pagination, detail mapping, manual/automatic classification audit и пакетный reclassify;
- channel ingest transaction, post/hashtag/link replacement, overview aggregates, hashtag/character/prompt/media/link stat mapping и limit clamps;
- quality summary counters, dynamic placeholder pagination, media offset mapping, unresolved item numbering и broken-check reset count;
- media-set discovery с двумя соединениями, candidate pagination/detail, toggle/decision, set creation, duplicate conversion и каскадное удаление;
- semantic grouping/title/reason/score остаются в application service, profile loading и candidate retirement/upsert transaction находятся в `MediaSetAIRepository`;
- invalid semantic JSON по-прежнему пропускается, fallback discovery и суммарный created-count сохранены.

Private pool inventory:

- исходно: 130 обращений в 35 production-файлах;
- после 18N: 128 в 34 файлах;
- после 18O: 126 в 33 файлах;
- после 18P: 118 в 32 файлах;
- после 18Q: 116 в 31 файле;
- после 18R: 115 в 30 файлах;
- после 18S: 114 в 29 файлах;
- после 18T: 113 в 28 файлах;
- после 18U: 110 в 27 файлах;
- после 18V: 100 в 25 файлах;
- после 18W: 96 в 24 файлах;
- после 18X: 88 в 23 файлах;
- после 18Y: 86 в 22 файлах;
- после 18Z: 84 в 21 файле;
- после 18AA: 82 в 20 файлах;
- после 18AB: 67 в 19 файлах;
- после 18AC: 63 в 18 файлах;
- после 18AD: 62 в 17 файлах;
- после 18AE: 60 в 15 файлах;
- после 18AF: 58 в 14 файлах;
- после 18AG: 53 в 13 файлах;
- после 18AH: 45 в 12 файлах;
- после 18AI: 36 в 11 файлах;
- после 18AJ: 28 в 10 файлах;
- после 18AK: 23 в 9 файлах;
- после 18AL: 14 в 8 файлах;
- после 18AM: 12 в 7 файлах;
- legacy query-модули и application-service direct DB access полностью удалены из baseline;
- baseline контролируется AST-тестом и SHA-256 identity методов;
- новые неучтённые обращения блокируются CI.

Фаза 18 закрыта полностью; следующий архитектурный долг ведётся отдельной P2 stability inventory.

## Фаза 19: Velvet AI

Статус: завершена.

- единое меню качества;
- журнал AI-заданий;
- lifecycle `pending/processing/ready/error/interrupted`;
- проверка изображения, референса, промта, палитры, оформления и медиасета;
- PostgreSQL integration tests и callback contracts;
- callbacks медиасетов подтверждаются до долгих операций.

## Фаза 20: Supervisor

Статус кода: завершён.

Реализованы:

- безопасная удалённая консоль;
- self-restart/self-update через внешний Windows bootstrap;
- fast-forward update, tests, rollback, lock и healthcheck;
- Telegram-отчёт операции.

Не подтверждено живой эксплуатацией:

1. self-restart на целевой Windows;
2. update-and-restart;
3. success/error Telegram report после bootstrap.

## Документация и контроль

- `docs/project_memory.md` — долгосрочная карта;
- `docs/development_status.md` — текущий статус;
- `docs/stabilization_policy.md` — допустимый новый код и ворота;
- `docs/private_pool_inventory.*` — измеримый PostgreSQL-долг;
- `docs/worklog/` — дневники до/после работы;
- `AGENTS.md` — обязательные правила;
- `CHANGELOG.md` — заметные изменения;
- CI блокирует PR без завершённого worklog.

## Текущий P2-план

1. P2A: stability inventory создан; multi-story callbacks подтверждаются до тяжёлого рендера.
2. P2B: late/missing callback baseline закрыт 0; quality retry/reset/enqueue подтверждаются до reload UI.
3. P2U: media browser fallbacks and failure reporting are verified; unresolved broad baseline 37 → 33.
4. Создать staging-бота и staging-базу.
5. Провести независимый backup/restore drill.
6. Добавить encrypted offsite backup.
7. Добавить AI duration/error/cost metrics.

## Правила дальнейшей разработки

- новый код обязан улучшать существующую функцию;
- handler не получает SQL;
- business operation создаётся через use case/domain service;
- private pool срез уменьшает baseline, а не переносит долг;
- старая применённая миграция не редактируется;
- инфраструктура считается production-ready только после доступной живой проверки;
- каждая работа имеет worklog, CI, PR/commit и следующий шаг.


## Завершение Фазы 18

Фаза 18 полностью закрыта: private-pool baseline уменьшен с 130 обращений в 35 production-файлах до 0/0. Persistence медиасетов вынесен в repositories, SQL удалён из трёх Telegram handlers, discussion compatibility делегирует каноническому dashboard, а оставшийся quality-set facade использует публичную границу. Новые внешние `_require_pool()` блокируются AST-контрактом.
