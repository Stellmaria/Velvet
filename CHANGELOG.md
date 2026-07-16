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
- `PublicationRepository` для атомарных переходов состояния очереди публикаций;
- `PublicNotificationRepository` для выборки и фиксации доставок подписчикам;
- application layer `velvet_bot/app` для composition root, Dispatcher, команд и workers;
- presentation layer `velvet_bot/presentation/telegram` для сборки Telegram router;
- media quality domain с `MediaQualityRepository`, `MediaQualityService` и отдельными моделями;
- целевая архитектура и порядок доменного переноса в `docs/architecture_target.md`;
- архитектурные регрессионные тесты;
- версия приложения `1.2.0-dev.1`.

### Changed

- запуск и остановка фоновых процессов централизованы в `WorkerManager`;
- одновременный повторный запуск одной задачи блокируется отдельным lock;
- очередь публикаций и публичные уведомления получили отдельные функции одной итерации;
- SQL переходов `publishing`, `published` и `error` вынесен из Telegram transport-модуля;
- SQL выборки и фиксации публичных уведомлений вынесен из worker-а;
- автоматические копии и контроль качества медиа подключены к общему runtime-контуру;
- `main.py` сокращён до настройки логирования и запуска application layer;
- каталог Telegram-команд вынесен из точки запуска;
- регистрация middleware и workflow dependencies вынесена в `app/dispatcher.py`;
- регистрация периодических процессов вынесена в `app/workers.py`;
- сборка корневого router и порядок handlers вынесены из `handlers/__init__.py`;
- legacy monkey-patching изолирован в compatibility layer;
- фоновый `media-quality` больше не зависит от приватных функций монолитного модуля;
- захват очереди, fingerprint persistence, duplicate candidate persistence и file checks выполняются через domain repository/service.

## [1.0.0] - 2026-07-16

### Added

- аналитический центр;
- алиасы и классификация публикаций;
- проверка и очередь публикаций;
- визуальные дубли и контроль качества;
- аналитика обсуждений;
- проверяемые резервные копии PostgreSQL.
