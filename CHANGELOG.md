# Changelog

Все заметные изменения Velvet Archive фиксируются в этом файле.

## [Unreleased]

### Added

- единый менеджер периодических фоновых процессов;
- состояние, счётчики запусков, последние ошибки и следующий запуск каждого worker-а;
- команды `/system`, `/health` и `/version`;
- системная диагностика PostgreSQL, Telegram, диска, резервных копий и очередей;
- карточки отдельных worker-ов;
- безопасный ручной запуск одной итерации и перезапуск отдельного процесса;
- экспорт диагностического JSON без токенов, паролей и строки подключения;
- маскирование возможных секретов внутри текстов ошибок;
- `SystemRepository` и `SystemHealthService` для эксплуатационной диагностики;
- `PublicNotificationRepository` для выборки и фиксации доставок подписчикам;
- application layer `velvet_bot/app` для composition root, Dispatcher, команд и workers;
- presentation layer `velvet_bot/presentation/telegram` для сборки Telegram router;
- media quality domain с repository, service и отдельными моделями;
- publication domain с моделями, repository и service;
- Telegram publication delivery adapter в infrastructure layer;
- целевая архитектура и порядок доменного переноса в `docs/architecture_target.md`;
- архитектурные регрессионные тесты;
- версия приложения `1.2.0-dev.1`.

### Changed

- запуск и остановка фоновых процессов централизованы в `WorkerManager`;
- одновременный повторный запуск одной задачи блокируется отдельным lock;
- `main.py` сокращён до настройки логирования и запуска application layer;
- каталог Telegram-команд вынесен из точки запуска;
- регистрация middleware и workflow dependencies вынесена в `app/dispatcher.py`;
- регистрация периодических процессов вынесена в `app/workers.py`;
- сборка корневого router и порядок handlers вынесены из `handlers/__init__.py`;
- legacy monkey-patching изолирован в compatibility layer;
- фоновый media quality переведён на domain repository/service;
- `media_quality.py` превращён в compatibility facade;
- публикационный worker переведён на долгоживущий `PublicationService`;
- SQL чтения черновиков, очереди и переходов состояний публикации собран в domain repository;
- Telegram sendMessage/sendMediaGroup вынесены из domain service в infrastructure adapter;
- `publication_worker.py` превращён в compatibility facade;
- `app` package сделан ленивым для предотвращения циклических импортов.

## [1.0.0] - 2026-07-16

### Added

- аналитический центр;
- алиасы и классификация публикаций;
- проверка и очередь публикаций;
- визуальные дубли и контроль качества;
- аналитика обсуждений;
- проверяемые резервные копии PostgreSQL.
