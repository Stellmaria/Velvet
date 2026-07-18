# Changelog

Все заметные изменения Velvet Archive фиксируются в этом файле.

## [Unreleased]

### Added

- owner-only контур нанесения водяного знака через локальный Krita bridge;
- PostgreSQL-задания и revisions для положения, цвета, прозрачности, размера, отступа, отката и финального результата;
- кнопка `💧 Водяной знак` в центре управления и аварийная команда `/watermark`;
- worker Krita без публичного сетевого порта, с восстановлением stale `*.processing` и контролируемыми ошибками;
- исходники, сборщик ZIP и документация Python-плагина Krita с автоматической обработкой bridge-запросов;
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
- документированная очередь погашения private pool debt по архитектурным слоям;
- документ `docs/stabilization_policy.md`, определяющий допустимый новый код и стабилизационные ворота проекта.

### Changed

- watermark worker обрабатывает только текущую revision; исторические pending revisions остаются историей, а не лишней очередью;
- оригинал watermark-сценария никогда не перезаписывается, preview и финальный PNG создаются отдельными артефактами;
- Krita bridge выключен по умолчанию до живой Windows-проверки;
- добавлена публичная граница `Database.acquire()` для PostgreSQL repositories;
- character, story, archive, public archive, reference, media quality, publication, publication validation, publication draft, discussion, discussion ingest, discussion insight, discussion ranking, discussion activity, discussion post insight, discussion relink, archive preview, system, prompt/result report, palette/composition report, Velvet formatting report, quality calibration, AI quality repository, его schema compatibility facade, Media AI repository и Error Incident repository больше не обращаются к приватному `_require_pool()`;
- private pool baseline уменьшен с 130 обращений в 35 production-файлах до 88 обращений в 23 файлах;
- явные domain/infrastructure, одиночные report, calibration, AI quality, Media AI и Error Incident repositories вместе с активным compatibility facade удалены из private pool baseline;
- новые либо изменённые private pool access блокируются CI до отдельного review и обновления baseline;
- `AGENTS.md` и карта проекта закрепляют Velvet Archive как отдельный owner-oriented архивный продукт без логики аукционного бота;
- в режиме стабилизации новый код допускается только для ускорения, упрощения, надёжности, контроля и удобства существующих функций;
- промт против результата, палитра и композиция, оформление, ручная проверка изображения, сравнение с референсом и анализ медиасета регистрируются до обращения к Qwen;
- длинные AI-результаты отправляются отдельным сообщением и полностью сохраняются в истории;
- кнопка ручного запуска worker подтверждает нажатие до выполнения длительного цикла;
- Supervisor показывает отдельные экраны `Консоль` и `Сам Supervisor`;
- команды удалённой диагностики выполняются без shell из фиксированного каталога с маскированием секретов.

### Fixed

- stale `*.processing` Krita request безопасно возвращается в очередь только при отсутствии готового response и обычного request-файла;
- `output_path` из response повторно нормализуется, сверяется с ожидаемым output и отклоняется при traversal, UNC или выходе через symlink;
- approve блокирует job и текущую ready revision в одной PostgreSQL-транзакции, поэтому устаревший output нельзя подтвердить;
- старый callback отмены не меняет approved watermark job и получает спокойный доменный ответ;
- повторная настройка watermark удаляет прежний векторный слой и строит новую версию из исходника вместо наслаивания логотипов;
- callback списка медиасетов подтверждается до discovery, PostgreSQL-запросов и редактирования сообщения;
- открытие кандидата медиасета подтверждается до последовательной отправки Telegram preview;
- точный ответ Telegram `query is too old / query ID is invalid` больше не создаёт ложный ERROR, остальные `TelegramBadRequest` не подавляются;
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
- фильтр шумных архивных ошибок устанавливается в штатном handler;
- документация backup различает проверку списка архива и реальное восстановление.
