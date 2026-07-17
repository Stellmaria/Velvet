# Changelog

Все заметные изменения Velvet Archive фиксируются в этом файле.

## [Unreleased]

### Added

- постоянный журнал AI-заданий со статусами `pending`, `processing`, `ready` и `error`;
- кнопка истории AI-запросов с сохранёнными результатами и причинами ошибок;
- операционное меню проверки качества с ручным анализом изображения, управлением очередью, ошибками и worker;
- кнопочная форма сравнения результата с референсом без обязательной slash-команды;
- PostgreSQL integration tests жизненного цикла AI-заданий;
- автоматическая проверка соответствия всех literal `quality:` callbacks реальным handlers;
- безопасная удалённая консоль Supervisor с allowlist, preview, подтверждением, таймаутами и аудитом;
- внешний Windows bootstrap для удалённого перезапуска и self-update самого Supervisor;
- постоянная карта фаз `docs/project_memory.md` и рабочий журнал `docs/worklog/`;
- CI-контракт, требующий завершённую запись разработки для каждого содержательного PR;
- AST-контракт, запрещающий аукционные доменные зависимости в production package Velvet Archive;
- AST-инвентаризация обращений к `Database._require_pool()`, включая dynamic `getattr`;
- машинный baseline private pool debt с count и SHA-256 identity для каждого production-файла;
- документированная очередь погашения private pool debt по архитектурным слоям.

### Changed

- добавлена публичная граница `Database.acquire()` для PostgreSQL repositories;
- character, story, archive, public archive, reference, media quality, publication, discussion, discussion ingest, discussion insight, discussion ranking, discussion activity, discussion post insight и discussion relink repositories больше не обращаются к приватному `_require_pool()`;
- новые либо изменённые private pool access блокируются CI до отдельного review и обновления baseline;
- `AGENTS.md` и карта проекта закрепляют Velvet Archive как отдельный owner-oriented архивный продукт без логики аукционного бота;
- промт против результата, палитра и композиция, оформление, ручная проверка изображения, сравнение с референсом и анализ медиасета регистрируются до обращения к Qwen;
- длинные AI-результаты отправляются отдельным сообщением и полностью сохраняются в истории;
- кнопка ручного запуска worker подтверждает нажатие до выполнения длительного цикла;
- Supervisor показывает отдельные экраны `Консоль` и `Сам Supervisor`;
- команды удалённой диагностики выполняются без shell из фиксированного каталога с маскированием секретов.

### Fixed

- кнопка «Проверка качества» снова открывает полный операционный экран, а не только список отчётов;
- восстановлены кнопки проверки нового изображения, последних файлов, повторения ошибок, дублей и медиасетов;
- зависшие после перезапуска AI-задания получают состояние `interrupted` вместо бесконечного ожидания;
- удалён разрыв, при котором кнопка сравнения с референсом требовала вручную вводить `/compare_ref`.

## [1.3.0] - 2026-07-17

### Added

- Dockerfile для Velvet Bot на Python 3.13;
- Docker Compose с PostgreSQL 16, ботом и опциональной Ollama;
- контейнерные healthcheck и отдельный CI workflow сборки Docker-образа;
- автоматический restore drill: dump, новая база, полное восстановление, миграции и контроль данных;
- еженедельная GitHub Actions проверка восстановления backup;
- release workflow с проверкой соответствия Git tag и `APP_VERSION`;
- актуальная документация функций, ролей, AI, Supervisor, backup и deployment;
- transport-neutral `PublicationActions`;
- PostgreSQL integration tests для нескольких историй КР и восстановления backup.

### Changed

- Docker и CI используют PostgreSQL 16;
- версия приложения переведена с `1.3.0-dev.1` на стабильную `1.3.0`;
- analytics navigation вынесена в единый presentation-контракт;
- parent-channel lookup обсуждений перенесён из Telegram handler в repository/service/query;
- центр публикаций переведён с набора compatibility-фасадов на application coordinator;
- управление аналитикой разделено на независимые модули тегов, алиасы и классификацию;
- владельческие reply-формы разделены на media, profiles, references и data presentation-модули;
- несколько историй перенесены в штатные character/story repositories;
- `character_story_links` используется для публичной готовности, фильтрации и статистики;
- ручная классификация публикаций получила явно типизированный PostgreSQL SQL;
- safe analytics edit подключается явно, без runtime-подмены;
- фильтр шумных архивных ошибок устанавливается в штатном модуле;
- документация backup различает проверку списка архива и реальное восстановление.
