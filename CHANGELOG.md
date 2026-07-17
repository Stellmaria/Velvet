# Changelog

Все заметные изменения Velvet Archive фиксируются в этом файле.

## [Unreleased]

### Added

- Dockerfile для Velvet Bot на Python 3.13;
- полный Docker Compose с PostgreSQL 16, ботом и опциональной Ollama;
- контейнерный healthcheck PostgreSQL и схемы миграций;
- автоматический restore drill: dump, новая база, полное восстановление, миграции и контроль данных;
- еженедельный GitHub Actions workflow проверки восстановления;
- актуальная документация функций, ролей, AI, Supervisor и deployment;
- подготовка версии `1.3.0-dev.1`.

### Changed

- Docker и CI используют одну основную версию PostgreSQL 16;
- `.env.example` содержит параметры Docker и `CODEX_MODEL`;
- документация backup различает чтение архива и реальное восстановление;
- README больше не описывает устаревший временный preview как текущую архитектуру.

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
