# Changelog

Все заметные изменения Velvet Archive фиксируются в этом файле.

## [Unreleased]

Пока нет изменений после выпуска `1.3.0`.

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
- управление аналитикой разделено на независимые модули тегов, алиасов и классификации;
- владельческие reply-формы разделены на media, profiles, references и data presentation-модули;
- несколько историй перенесены в штатные character/story repositories;
- `character_story_links` используется для публичной готовности, фильтрации и статистики;
- ручная классификация публикаций получила явно типизированные PostgreSQL-параметры;
- safe analytics edit подключается явно, без runtime-подмены;
- фильтр шумных архивных ошибок устанавливается в штатном модуле;
- документация backup различает проверку списка архива и реальное восстановление.

### Removed

- прямой SQL из analytics discussion handler;
- handler-to-handler импорт приватных helper-функций аналитики;
- runtime monkeypatch нескольких историй;
- runtime monkeypatch media-quality и ручной классификации;
- вызов legacy compatibility installer из root router;
- бизнес-ветки из монолитных `analytics_management.py` и `owner_actions.py`.

## [1.2.0-dev.1] - 2026-07-17

### Added

- единый менеджер периодических фоновых процессов;
- системная диагностика и диагностический JSON;
- модульная архитектура application/domain/infrastructure/presentation;
- домены media quality, publication, characters, stories, references, archive и discussions;
- Velvet Supervisor с обновлением, rollback, логами и Codex worktree;
- кнопочный центр владельца и формы служебных действий;
- центр ошибок с подтверждением и повторными уведомлениями;
- медиасеты, удаление дублей и общий промт;
- семантический vision-анализ изображений;
- Velvet AI: качество, сравнение с референсом, целостность сетов, калибровка, промт против результата, палитра, композиция и оформление публикаций.

### Changed

- `main.py` сокращён до запуска application layer;
- Supervisor разделён на status, process, git, logs и Codex controllers;
- owner-операции переведены на application use cases;
- SQL-миграции защищены SHA-256 checksum;
- публичные права закреплены точным allowlist;
- загрузка Telegram и structured JSON Qwen получили fallback и повторные попытки.

## [1.0.0] - 2026-07-16

### Added

- архив персонажей, категории, вселенные и истории;
- публичный каталог, лайки, подписки и уведомления;
- аналитический центр;
- алиасы и классификация публикаций;
- проверка и очередь публикаций;
- визуальные дубли и контроль качества;
- аналитика обсуждений;
- проверяемые резервные копии PostgreSQL.
