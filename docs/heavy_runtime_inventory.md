# Инвентаризация тяжёлых runtime-компонентов Velvet

Дата инвентаризации: 18 июля 2026 года.

Статус: исходная карта перед модульным рефакторингом тяжёлых сервисов.

## 1. Граница работы

Цель линии Heavy Runtime — сохранить один owner-oriented Telegram-бот и одну PostgreSQL-базу, но перестать держать тяжёлые локальные сервисы активными без реальной задачи.

Эта линия не включает:

- горячую выгрузку aiogram-router;
- отдельный RP Telegram-бот;
- микросервис на каждый handler или repository;
- изменение прикладных сценариев архива, публикаций и аналитики;
- смешивание с Фазой 18W и дальнейшим погашением private pool debt.

## 2. Текущий composition root

Запуск проходит через:

```text
main.py
→ velvet_bot.app.run_application
→ velvet_bot.app.bootstrap.run_application
```

В одном процессе постоянно живут:

- aiogram polling;
- PostgreSQL pool;
- ErrorIncidentCenter;
- общий root router;
- WorkerManager;
- клиенты Supervisor;
- лёгкие middleware и owner-oriented application services.

Supervisor является отдельным внешним процессом и запускает основной процесс бота как child process.

## 3. Текущий WorkerManager

`velvet_bot.workers.manager.WorkerManager` управляет periodic tasks только в памяти процесса.

Поддерживаются состояния:

- `stopped`;
- `starting`;
- `running`;
- `failed`.

Поддерживаются:

- регистрация до старта;
- запуск всех workers;
- остановка всех workers;
- ручной `run_now`;
- restart отдельного worker;
- отдельный `asyncio.Lock` на одну итерацию worker;
- счётчики успехов и ошибок;
- время последнего запуска, успеха, ошибки и следующей итерации.

Ограничения текущего менеджера:

- нет состояний `idle/loading/pausing/paused/stopping`;
- нет общего владельца тяжёлого ресурса;
- нет приоритетов между разными workers;
- нет ожидания ресурса и кооперативной паузы;
- snapshots и task state не переживают перезапуск;
- состояние процесса не отделено от состояния задания;
- periodic worker запускается даже при пустой очереди и выполняет polling по интервалу.

## 4. Реестр постоянных workers

`velvet_bot.app.workers.build_worker_manager()` регистрирует:

| Worker | Интервал | Условие | Характер нагрузки |
|---|---:|---|---|
| `public-archive-notifications` | 5 сек. | всегда | лёгкий PostgreSQL/Telegram |
| `publication-queue` | 15 сек. | всегда | лёгкий PostgreSQL/Telegram |
| `media-quality` | 4 сек. | всегда | локальная обработка медиа и PostgreSQL |
| `krita-watermark` | 2 сек. | `KRITA_WATERMARK_ENABLED` | bridge polling, внешняя Krita запускается отдельно |
| `ai-vision` | 8 сек. | `AI_VISION_ENABLED` | локальная/remote vision model |
| `ai-quality` | 10 сек. | `AI_VISION_ENABLED` | локальная/remote vision model |
| `error-alert-reminders` | 300 сек. | ErrorIncidentCenter доступен | лёгкий PostgreSQL/Telegram |
| `postgresql-backups` | 300 сек. | всегда | проверка расписания, иногда тяжёлый `pg_dump` |

Вывод: лёгкие periodic workers можно оставить в постоянно работающем ядре. AI, Krita, импорт и реальный backup должны получить отдельный lifecycle и общий диспетчер тяжёлых ресурсов.

## 5. Feature flags и конфигурация

Сейчас единый `Settings` содержит полноценные настройки только для AI Vision:

- `AI_VISION_ENABLED`;
- provider/base URL/model/API key;
- timeout;
- max attempts.

Krita настраивается разрозненно:

- `velvet_bot.app.workers` самостоятельно читает `KRITA_WATERMARK_ENABLED` через `os.getenv`;
- `KritaProcessManager` отдельно читает `KRITA_WATERMARK_ENABLED`, `KRITA_AUTOSTART_ENABLED`, `KRITA_IDLE_TIMEOUT_SECONDS`, `KRITA_EXECUTABLE`, `KRITA_BRIDGE_DIR` и `KRITA_PLUGIN_DIR`;
- bridge также самостоятельно читает `KRITA_BRIDGE_DIR`.

Отдельных флагов для roleplay, imports, analytics aggregation, public archive и publications в едином объекте конфигурации нет.

Первый production-срез после инвентаризации должен создать типизированный единый набор feature flags и runtime timeouts без изменения текущего поведения.

## 6. Qwen Vision и локальные модели

Текущая защита локальной модели:

```text
get_local_ai_lock()
→ один process-wide asyncio.Lock
→ ai-vision и ai-quality выполняются последовательно
```

Это предотвращает одновременный локальный vision request внутри одного процесса, но не является диспетчером ресурсов.

Текущее поведение:

- два periodic workers постоянно проверяют provider и очередь;
- provider health кешируется на 30 секунд;
- каждое задание claim-ится из PostgreSQL с `FOR UPDATE SKIP LOCKED`;
- stale `processing` возвращается в `pending`;
- одновременно обрабатывается одно изображение на worker iteration;
- Qwen/Ollama запросы используют `keep_alive="15m"` в основных надёжных vision-клиентах;
- базовый `VisionClient` не задаёт управляемый unload;
- нет общего `LocalModelRuntime`;
- бот не запускает и не останавливает Ollama;
- нет явного переключения модели RP ↔ Qwen;
- нет приоритетов interactive/background;
- нет режима «закончить текущее изображение и не брать следующее»;
- нет единого idle timeout, который гарантированно выгружает модель.

Существующие таблицы AI уже обеспечивают устойчивый lifecycle заданий, поэтому будущий scheduler должен адаптировать текущие repositories, а не создавать параллельную несовместимую очередь без необходимости.

## 7. Krita

Krita является наиболее зрелым on-demand runtime в текущем проекте.

Supervisor уже содержит `KritaProcessManager`, который:

- запускает Krita по запросу;
- не создаёт второй экземпляр;
- отличает managed и вручную открытый процесс;
- хранит managed PID в runtime marker;
- восстанавливает ownership после self-restart Supervisor;
- синхронизирует плагин перед managed start;
- не закрывает вручную открытый экземпляр;
- не закрывает managed Krita при pending/processing bridge request;
- отслеживает idle и завершает управляемый процесс;
- отдаёт status/ensure/touch/stop через локальный Supervisor API.

Текущий default idle timeout Supervisor: 600 секунд. В целевом ТЗ указан безопасный default 300 секунд. Изменение значения должно выполняться отдельным срезом после живой Windows-проверки, а не внутри инвентаризации.

Оставшийся архитектурный разрыв:

- bridge worker продолжает polling каждые 2 секунды;
- Krita не участвует в общем ResourceManager;
- Supervisor не показывает единый ресурсный приоритет и владельца;
- settings всё ещё читаются несколькими компонентами напрямую из environment.

## 8. Backup

Текущий backup lifecycle:

- перед миграциями выполняется проверяемая pre-migration backup;
- daily/weekly policy хранится в PostgreSQL;
- periodic worker каждые 300 секунд проверяет, наступило ли расписание;
- при due выполняется `pg_dump`, валидация и cleanup;
- при отсутствующем `pg_dump` бот продолжает работу с warning.

Плюсы:

- backup metadata уже сохраняется;
- pre-migration guard уже существует;
- daily/weekly retention уже реализован;
- тяжёлый `pg_dump` не выполняется без due condition.

Разрыв с целевой архитектурой:

- проверка всё равно выполняется постоянным циклом;
- backup не оформлен как низкоприоритетное устойчивое задание;
- нет общего запрета запуска во время интерактивной AI/Krita/импорт операции;
- нет события «пропущенная ежедневная копия после выключенного ПК» в общей очереди;
- Supervisor не показывает backup как отдельный runtime/job.

## 9. Импорт Telegram

Текущий импорт запускается непосредственно из Telegram handler и ожидается внутри callback/message coroutine.

Текущее поведение:

- документ полностью скачивается в память;
- JSON/ZIP полностью разбирается;
- все records формируются до записи;
- duplicate import определяется по SHA-256;
- импорт выполняется одной большой PostgreSQL transaction;
- records обрабатываются последовательным Python-циклом;
- после discussion import сразу запускается relink;
- итог сохраняется в `telegram_export_imports` только после завершения.

Ограничения:

- нет job state `pending/running/paused/completed/failed/cancelled`;
- нет checkpoint;
- нет batch commit;
- нет продолжения после рестарта;
- нет паузы при интерактивной задаче;
- прогресс не доступен Supervisor;
- крупный импорт удерживает handler и одну transaction до завершения.

Это один из самых рискованных тяжёлых срезов. Его нельзя переносить в background простым `asyncio.create_task`, потому что такое решение потеряет состояние после перезапуска.

## 10. Аналитика

В центральном WorkerManager отсутствует отдельный тяжёлый analytics aggregation worker.

Сейчас:

- channel/discussion events записываются middleware и прикладными функциями;
- dashboards и отчёты в основном строятся по запросу;
- импорт исторических данных является отдельной тяжёлой операцией;
- нет единой таблицы raw analytics events для всех доменов, перечисленных в целевом ТЗ;
- нет явной операции «завершить рабочую сессию» с агрегацией и optional backup.

Следующий аналитический срез должен сначала отделить уже лёгкое event capture от действительно тяжёлых пересчётов. Нельзя объявлять всю аналитику тяжёлым сервисом и останавливать сбор сырых событий.

## 11. Supervisor

Текущий Supervisor управляет:

- основным процессом Telegram-бота;
- auto-restart и crash loop;
- git/update/test/bootstrap operations;
- Codex tasks;
- безопасной remote console;
- managed Krita process.

Текущий status содержит:

- Supervisor PID и uptime;
- Bot PID, desired state, restart counters и exit state;
- git branch/head/dirty;
- последнюю operation;
- Codex status;
- Krita status.

Пока отсутствуют отдельные runtime cards для:

- PostgreSQL;
- Ollama service;
- загруженной локальной модели;
- Qwen queue и pause state;
- RP runtime;
- analytics aggregation;
- import jobs;
- backup jobs;
- общего владельца тяжёлого ресурса.

Supervisor уже подходит как внешний process-control слой. Его не следует заменять вторым оркестратором. Новый ResourceManager должен жить в приложении и публиковать согласованный snapshot Supervisor.

## 12. Router registration

Root router сейчас собирается один раз и подключает все handlers.

Это соответствует целевому решению не выполнять горячую выгрузку aiogram-router. Feature flags должны управлять регистрацией тяжёлых workers, внешними процессами и доступностью операций, но не пытаться выгружать Python-модули из памяти во время работы.

## 13. Целевая последовательность малых PR

### HR-1. Инвентаризация и карта зависимостей

- этот документ;
- отдельный worklog;
- фиксация линии в project memory/status;
- без production-кода и миграций.

### HR-2. Единая runtime-конфигурация

- типизированные feature flags;
- типизированные idle timeouts;
- безопасные defaults и validation;
- убрать прямой `os.getenv` из `app.workers`;
- сохранить фактическое поведение;
- unit-тесты конфигурации.

### HR-3. ResourceManager foundation

- enum состояний ресурса и приоритетов;
- cooperative acquire/release;
- один active heavy owner при `ALLOW_PARALLEL_LOCAL_MODELS=false`;
- ожидание, cancel-safe cleanup и incident logging;
- immutable snapshot;
- unit-тесты всех переходов;
- пока без изменения Qwen/Krita production scheduling.

### HR-4. LocalModelRuntime для Ollama

- единый health/start/load/unload/stop contract;
- lock от повторного запуска;
- текущая модель и timestamps;
- timeout/error recovery;
- явная выгрузка модели;
- integration adapter для существующих vision clients;
- без RP handler.

### HR-5. Qwen scheduling

- interactive и background priority;
- завершить текущее изображение, затем paused;
- не claim-ить следующее задание при ожидании более высокого приоритета;
- idle unload;
- продолжение существующих PostgreSQL queues;
- status для Supervisor;
- recovery tests.

### HR-6. Один RP runtime

- один character profile и одна активная owner session;
- PostgreSQL history/memory;
- запуск модели по первому сообщению;
- idle unload;
- приоритет над background Qwen;
- без каталога персонажей, публичного доступа и отдельного бота.

### HR-7. Krita adapter

- подключить существующий `KritaProcessManager` к ResourceManager;
- сохранить managed/unmanaged safety;
- сделать bridge worker demand-aware;
- согласовать idle timeout через единый Settings;
- расширить status без переписывания работающего process manager.

### HR-8. Лёгкие analytics events и тяжёлая агрегация

- унифицированный append-only event contract;
- on-demand/daily aggregation;
- операция завершения рабочей сессии;
- не останавливать лёгкий capture событий.

### HR-9. Import jobs и event-driven backup

- новая миграция только для новых job/checkpoint metadata;
- batch import, checkpoint, resume и pause;
- backup requests по событиям и возрасту;
- low priority через ResourceManager;
- retention и текущий BackupService сохранить.

### HR-10. Supervisor runtime dashboard

- единый runtime snapshot;
- процессы и jobs показываются отдельно;
- owner, priority, queue size, idle timeout и last error;
- start/stop/pause/resume/run-once/release-memory;
- runtime profiles;
- Windows smoke-test и rollback runbook.

## 14. Параллельная работа с текущей картой проекта

Фаза 18W остаётся отдельным repository-срезом и не должна включаться в HR-ветки. Допустима параллельная работа только при отсутствии пересечения файлов или после последовательного rebase.

Рекомендуемый порядок:

1. слить HR-1;
2. завершить или синхронизировать 18W;
3. выполнить HR-2;
4. выполнить HR-3;
5. только затем менять lifecycle Ollama/Qwen.

## 15. Критерий завершения HR-1

- существующие workers и process owners перечислены;
- точки прямого environment/config доступа перечислены;
- текущие queue/lifecycle ограничения зафиксированы;
- риски import/backup/Qwen/Krita разделены;
- определена последовательность малых PR;
- production-код и применённые миграции не изменены.
