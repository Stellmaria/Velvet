# Changelog

Все заметные изменения Velvet Archive фиксируются в этом файле.

## [Unreleased]

### P3A: current architecture status synchronization

- Current status, project memory and architecture audit now reflect merged `main`.
- P2 generated baseline is 76 approved broad boundaries, 0 unresolved and 98 callback handlers with 0 late/missing acknowledgments.
- Legacy handler files, implementations and aliases are 0; four Telegram bundles register 60 active routers without duplicates.
- P3E is complete with 30 domain repositories, 1 PostgreSQL infrastructure adapter, 0 central repositories and 0 root repositories.
- Architecture inventory now points to the first bounded P3F static-typing baseline.

### Owner diagnostics and AI quality hotfixes

- Added owner-only `Velvet Diagnostic Bundle v1` with redacted runtime, workers, Error Center incidents and bounded log tail.
- Added five-minute critical diagnostics with per-incident and global cooldowns.
- Qwen retry now resets `media_ai_profiles.analysis` to an empty JSON object instead of violating its `NOT NULL` constraint.
- Permanent oversized/no-preview calibrated AI skips are logged as `INFO`; real provider, database and filesystem failures remain `WARNING/ERROR`.

### P3C–P3D: presentation completion and legacy consumer baseline

- All active Telegram controllers now live under canonical presentation routers; `velvet_bot/handlers` contains 35 aliases and 0 implementations.
- Added a generated inventory for production consumers of legacy `velvet_bot.handlers.*` paths.
- The first cleanup slice reduced the baseline to 20 consumer files, 30 references and 18 legacy modules.
- The next P3D slice moved multi-story KR callbacks/profile rendering to public contracts and reduced the baseline to 19 consumer files, 28 references and 17 legacy modules.
- Production imports no longer depend on `velvet_bot.handlers.*`: the generated baseline is now 0 consumer files, 0 references and 0 legacy modules.
- Archive and reference command parsing now lives in public parsing modules; remaining cross-domain menu, quality, supervisor and public archive links use canonical presentation imports.
- Archive topic deletion is now idempotent: Telegram `message to delete not found` is recorded as already absent instead of producing a warning and Error Center event.
- Character profile text and keyboard rendering moved to a public presentation contract used by character and story controllers.
- Callback prefixes, commands, SQL and user-visible behavior remain unchanged.
- The first compatibility-test migration retired 22 archive/reference aliases, reducing handler facades from 68 to 46.
- A follow-up zero-reference cleanup removed `ai_jobs` and `quality_calibration`, reducing handler facades from 46 to 44.
- Character/story compatibility tests now exercise canonical controllers directly; nine related handler facades were retired, reducing aliases from 44 to 35.
- Added a generated handler-alias consumer inventory that blocks references to deleted aliases.

### P3A–P3B: architecture organization

- Root Telegram Router now includes four ordered domain bundles instead of importing 55 handlers directly.
- Active compatibility installers are centralized into explicit pre-import and post-import stages.
- The unused discussion-dashboard package bridge was removed.
- A generated architecture-layout inventory and regression contracts now measure remaining physical debt.
- Project status, memory and architecture audit were synchronized with current `main`.

### P2AO–P2AP: final stability closure

- System health and WorkerManager boundaries were verified with cancellation/error regression tests.
- P2 inventory reached 67 approved broad boundaries, 0 unresolved boundaries and 0 late/missing callbacks.
- P2 stability has no remaining code slice.

### P2AN: media save boundaries

- Save failures are isolated and recorded.
- Cancellation propagates unchanged.
- Unresolved broad baseline decreased from 6 to 4.

### P2AM: publication stability boundaries

- Inbox capture failures no longer block the main Telegram handler.
- Publication worker iteration failures are logged and followed by another cycle.
- Cancellation remains terminal on both layers.
- Unresolved broad baseline decreased from 8 to 6.

### P2AL: public archive display fallbacks

- Viewer edit and send preview failures fall back to original documents.
- Caption, keyboard, spoiler, and cancellation contracts are verified.
- Unresolved broad baseline decreased from 10 to 8.

### P2AK: notification boundaries

- Recipient and worker failures are isolated.
- Delivery and cancellation contracts are verified.
- Unresolved broad baseline decreased from 12 to 10.

### P2AJ: media quality worker boundary

- A failed media-quality iteration is logged and the following cycle still runs.
- Cancellation remains terminal and is not logged as an iteration failure.
- Unresolved broad baseline decreased from 13 to 12.

### P2AI: archive preview fallback

- Full-quality archive preview failures now have a verified document fallback boundary.
- New cache records are reused while legacy thumbnail records rebuild themselves.
- Oversized documents skip Bot API download and cancellation propagates unchanged.
- Unresolved broad baseline decreased from 14 to 13.

### P2AH: visual analysis job boundary

- Palette/composition AI job failure compensation and cancellation behavior are verified.
- Palette-card delivery failures occur after the job is ready and do not rewrite its lifecycle.
- Compensation persistence failures remain visible.
- Unresolved broad baseline decreased from 15 to 14.

### P2AG: formatting boundaries

- Formatting source parsing now handles only expected ValueError and RuntimeError failures.
- Unexpected parsing failures and cancellation propagate unchanged.
- Formatting AI job failure compensation is verified.
- Raw broad baseline decreased from 68 to 67; unresolved decreased from 17 to 15.

### P2AF: prompt/result job boundary

- Prompt/result AI job failures now have a verified compensation boundary.
- Prompt sessions remain available after failure or cancellation for a retry.
- Compensation persistence failures are not silently swallowed.
- Unresolved broad baseline decreased from 18 to 17.

### P2AE: watcher boundary

- Background watcher failures are logged and isolated.
- Cancellation propagates unchanged.
- Unresolved broad baseline decreased from 19 to 18.

### P2AD: reference form job boundary

- Reference-comparison form jobs now have a verified failure-compensation boundary.
- Cancellation records interruption and propagates unchanged.
- Compensation persistence failures are not silently swallowed.
- Unresolved broad baseline decreased from 20 to 19.

### P2AC: reference comparison audit

- Reference-comparison failures now create a real Telegram audit incident with character, reference, result, and user context.
- User-facing failure status remains available when the audit logger is disabled.
- Cancellation continues to propagate without creating a false incident.
- Unresolved broad baseline decreased from 21 to 20.

### P2AB: quality sets safe edit

- Narrowed quality-set message editing to TelegramBadRequest.
- Non-Telegram failures and cancellation now propagate unchanged.
- Raw broad baseline decreased from 69 to 68; unresolved decreased from 22 to 21.

### P2AA: set analysis job boundaries

- Callback and slash-command set analysis failures compensate their AI jobs.
- Cancellation records interruption and continues to propagate in both paths.
- Unresolved broad baseline decreased from 24 to 22.

### P2Z: manual quality job boundary

- Manual quality failures compensate the created AI job with an error state.
- Cancellation records an interrupted job and continues to propagate.
- Unresolved broad baseline decreased from 25 to 24.

### P2Y: quality duplicate safe edit

- Duplicate list edits now catch only TelegramBadRequest.
- Runtime failures and cancellation are no longer swallowed by a Telegram-specific fallback.
- Raw broad baseline decreased from 70 to 69; unresolved decreased from 26 to 25.

### P2X: publication report boundary

- Publication failures retain a local traceback and use source-chat or private fallback reporting.
- Telegram reporting failures no longer replace the original publication failure.
- Unresolved broad baseline decreased from 27 to 26.


### P2W: public manager download boundary

- Manager original delivery is separated from callback success reporting.
- Callback-answer failure no longer turns a completed delivery into a false send failure.
- Unresolved broad baseline decreased from 28 to 27.


### P2V: public archive boundaries

- Classified five public archive failure boundaries and added behavior tests.
- Successful like, subscription, and download operations are no longer reported as failed when Telegram presentation fails afterwards.
- Unresolved broad baseline decreased from 33 to 28.


### P2U: media browser boundaries

- Full-size image preview failures fall back to the original archived media.
- Image-document send failures fall back to the original document with caption and navigation preserved.
- Archive page load and delete failures retain audit context and user-facing alerts.
- Cancellation continues to propagate through all four boundaries.
- Unresolved broad baseline decreased from 37 to 33.


### P2T: guest archive boundaries

- Guest topic delivery failures now create one specific audit incident instead of a specific and a generic duplicate.
- General Guest Mode failures still create one generic audit incident and return a user-facing response.
- Cancellation continues to propagate.
- Unresolved broad baseline decreased from 39 to 37.

### P2S: error-center markup cleanup

- Error acknowledgement remains complete when Telegram markup cleanup fails.
- Cleanup failures are now logged and cancellation still propagates.
- Unresolved broad baseline decreased from 40 to 39.

### P2R: character topic boundaries

- Unexpected character create and topic binding failures now retain local tracebacks.
- Classified two user-facing handler boundaries.
- Unresolved broad baseline decreased from 42 to 40.

### P2Q: channel analytics ingest boundary

- Classified channel post analytics ingest failure reporting.
- Added tracked-channel, audit-context and cancellation tests.
- Unresolved broad baseline decreased from 43 to 42.

### P2P: backup center callback boundary

- Preserved the original unexpected backup error when Telegram cannot render the error message.
- Classified the backup callback reporting boundary.
- Unresolved broad baseline decreased from 44 to 43.

### P2O: topic archive boundary

- Classified automatic topic archive failure reporting boundary.
- Unresolved broad baseline decreased from 45 to 44.

### P2N: admin media preview boundaries

- Classified two administrative preview fallback boundaries.
- Unresolved broad baseline decreased from 47 to 45.

### P2M: error center boundaries

- Classified four logging and consumer isolation boundaries.
- Unresolved broad baseline decreased from 51 to 47.

### P2L: discussion middleware boundary

- Added a persistent P2 inventory generator.
- Unresolved broad baseline decreased from 52 to 51.

### P2K: backup service boundaries

- Cancellation теперь завершает running backup как failed.
- Worker iteration boundary классифицирован.
- Unresolved broad baseline уменьшен с 54 до 52.

### P2J: backup runtime cleanup

- Cancellation теперь удаляет созданные backup artifacts.
- Unresolved broad baseline уменьшен с 55 до 54.

### P2I: audit sink boundary

- Классифицирован best-effort Telegram audit sink.
- Unresolved broad baseline уменьшен с 56 до 55.

### P2H: bootstrap fatal boundaries

- Fatal reporting вынесен в отдельный helper и покрыт тестами.
- Unresolved broad baseline уменьшен с 58 до 56.

### P2G: bootstrap cleanup boundaries

- Классифицированы пять независимых shutdown cleanup boundaries.
- Unresolved broad baseline уменьшен с 63 до 58.

### P2F: AI job tracker boundary

- Классифицирована компенсационная граница создания status message для AI job.
- Unresolved broad baseline уменьшен с 64 до 63.

### P2E: AI worker boundaries

- Классифицированы claimed-target compensation boundaries в AI quality, semantic vision и calibrated quality workers.
- Unresolved broad baseline уменьшен с 67 до 64.

### P2D: media-quality scan boundary

- Claimed media scan broad catch отмечен как approved compensation boundary.
- Добавлены тесты записи scan error и cancellation propagation.
- Unresolved broad-exception baseline уменьшен с 68 до 67.

### P2C: publication broad boundaries

- Publication compensation и scheduled-item isolation отмечены как approved orchestration boundaries.
- Добавлены тесты mark-error compensation, queue isolation и cancellation propagation.
- Unresolved broad-exception baseline уменьшен с 70 до 68.

### P2B: quality callback acknowledgment

- Retry/reset/enqueue callbacks отвечают после mutation result и до тяжёлого UI reload.
- Late/missing callback baseline уменьшен с 5 до 0.

### P2A: stability inventory

- Добавлена AST-инвентаризация callback acknowledgment и широких исключений.
- Удалены устаревшие ссылки на незавершённую Фазу 18AN из текущего плана.
- Multi-story admin/public callbacks подтверждаются после guard lookup и до тяжёлого рендера.

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
- документ `docs/stabilization_policy.md`, определяющий допустимый новый код и стабилизационные ворота проекта;
- `MediaSetAIRepository` для изолированной загрузки semantic profiles и транзакционного сохранения AI-кандидатов медиасетов.

### Changed

- Фаза 18 завершена: private-pool baseline уменьшен с 130/35 до 0/0; media-set persistence вынесен в repositories, SQL удалён из AI/set/reference handlers, compatibility dashboard делегирует каноническому query.

- watermark worker обрабатывает только текущую revision; исторические pending revisions остаются историей, а не лишней очередью;
- оригинал watermark-сценария никогда не перезаписывается, preview и финальный PNG создаются отдельными артефактами;
- Krita bridge выключен по умолчанию до живой Windows-проверки;
- добавлена публичная граница `Database.acquire()` для PostgreSQL repositories;
- character, story, archive, public archive, reference, media quality, publication, publication validation, publication draft, discussion, discussion ingest, discussion insight, discussion ranking, discussion activity, discussion post insight, discussion relink, archive preview, system, prompt/result report, palette/composition report, Velvet formatting report, quality calibration, AI quality repository, его schema compatibility facade, Media AI repository, Error Incident repository, Reliable Ollama vision repository, Resilient AI vision repository, runtime Backup Service, базовый Backup Service, Telegram import persistence, public media lookup, discussion thread links, analytics reactions, alias management, character aliases, analytics dashboard, analytics review, channel analytics, quality audit, media sets и media-set AI discovery больше не обращаются к приватному `_require_pool()`;
- semantic grouping, названия, причины и оценки AI-медиасетов остаются в application service, а profile loading и candidate persistence перенесены в `MediaSetAIRepository`;
- private pool baseline уменьшен с 130 обращений в 35 production-файлах до 12 обращений в 7 файлах;
- legacy query-модули и application-service direct DB access полностью удалены из private pool baseline;
- repository-классы внутри крупных модулей, весь backup infrastructure, Telegram import persistence, public media lookup, discussion thread links, analytics reactions, alias management, character aliases, analytics dashboard, analytics review, channel analytics, quality audit, media sets и media-set AI discovery удалены из private pool baseline;
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
