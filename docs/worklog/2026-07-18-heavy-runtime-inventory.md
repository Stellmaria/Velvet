# Сессия: HR-1, инвентаризация тяжёлых runtime-компонентов

- Дата: 2026-07-18
- ID: `2026-07-18-heavy-runtime-inventory`
- Линия/фаза: стабилизация тяжёлых runtime, HR-1
- Статус: завершено
- Ветка: `agent/heavy-runtime-inventory`
- Базовый commit: `bb6de424c35f0a5eb2a031599a43ab90e8143dea`

## Перед началом

### Цель

Зафиксировать фактическую архитектуру текущего Velvet перед модульным рефакторингом тяжёлых сервисов: перечислить workers, процессы, feature flags, точки запуска Ollama/Qwen/Krita, импорт, backup и Supervisor, затем разложить изменение на небольшие независимые PR.

### Исходный контекст

Velvet уже является одним owner-oriented Telegram-ботом с PostgreSQL, WorkerManager, устойчивыми AI job tables, Krita bridge и внешним Supervisor. Новое техническое задание требует не переписывать production одним коммитом, а сначала отделить лёгкое ядро от тяжёлых runtime и определить реальную последовательность перехода.

Актуальный `main` находится поверх Фазы 18V и содержит последующие изменения Krita и Supervisor от 18 июля 2026 года. Фаза 18W остаётся отдельным repository-срезом и не входит в HR-1.

### Планируемый объём

1. Прочитать `AGENTS.md`, `docs/project_memory.md`, `docs/development_status.md`, `docs/stabilization_policy.md` и релевантные worklog.
2. Изучить composition root, WorkerManager и полный реестр workers.
3. Изучить Settings и прямое чтение environment.
4. Изучить Qwen/Ollama lifecycle и текущую блокировку локального AI.
5. Изучить Krita process manager и bridge worker.
6. Изучить import и backup lifecycle.
7. Изучить границу Supervisor.
8. Создать отдельную архитектурную инвентаризацию.
9. Определить последовательность HR-2…HR-10.
10. Не менять production-код и применённые миграции.

### Критерии готовности

- перечислены все workers из composition root;
- перечислены process owners и интервалы polling;
- зафиксированы существующие queue/recovery гарантии;
- зафиксированы разрывы feature flags и runtime settings;
- отдельно описаны Qwen, Krita, backup, import, analytics и Supervisor;
- предложена последовательность малых PR;
- Фаза 18W не смешана с runtime-рефакторингом;
- production-код и миграции не изменены;
- project notes contract и CI проходят.

### Риски и ограничения

- GitHub connector не предоставляет локальный checkout и запуск Windows-процессов;
- живая проверка Ollama, Krita, Supervisor и Telegram в HR-1 не выполняется;
- code search приватного репозитория недоступен, поэтому карта собрана по актуальным composition root, runtime-файлам, PR и worklog;
- некоторые вторичные analytics modules требуют дополнительного source audit перед HR-8;
- нельзя преждевременно менять `keep_alive`, polling intervals или idle timeout внутри docs-only PR.

### Проверка стабилизационных критериев

1. Улучшается существующая функция: управление уже существующими AI, Krita, import, analytics и backup контурами.
2. Станет понятнее и безопаснее: дальнейшие изменения получают границы, порядок и rollback scope.
3. Новая предметная область не добавляется: HR-1 содержит только архитектурную карту существующего Velvet.
4. Улучшение проверяется полнотой inventory, отсутствием production diff и project notes contract.
5. Сохраняются один бот, одна PostgreSQL-база, owner-only режим, текущие repositories/use cases и отдельная Фаза 18.

## После завершения

### Фактически сделано

- подтверждён актуальный default branch `main` и базовый commit `bb6de424c35f0a5eb2a031599a43ab90e8143dea`;
- прочитаны обязательные правила и актуальные документы проекта;
- изучены `run_application`, composition root, root router, WorkerManager и worker registry;
- зафиксированы восемь periodic workers и их интервалы;
- установлено, что current WorkerManager хранит lifecycle только в памяти и не управляет общим тяжёлым ресурсом;
- установлено, что AI Vision и AI Quality разделяют только один process-wide `asyncio.Lock`;
- зафиксирован `keep_alive="15m"` в надёжных Ollama vision clients;
- установлено отсутствие общего start/load/unload/stop runtime для Ollama;
- подтверждён зрелый on-demand `KritaProcessManager` в Supervisor и отдельный 2-секундный bridge polling worker;
- зафиксирован разрозненный direct `os.getenv` для Krita и отсутствие единого набора feature flags;
- подтверждён 5-минутный backup polling и существующая pre-migration/daily/weekly policy;
- подтверждено, что Telegram import выполняется одной большой transaction без checkpoint/resume/pause;
- зафиксирована текущая граница Supervisor: bot, git/operations, Codex и Krita, но без Ollama/Qwen/import/backup runtime cards;
- создан `docs/heavy_runtime_inventory.md` с последовательностью HR-2…HR-10;
- обновлены project memory и development status;
- открыт draft PR #124;
- production-код и миграции не изменялись.

### Архитектурное решение

Не заменять WorkerManager и Supervisor массовой переписью. Ввести между application workers и тяжёлыми adapters новый `ResourceManager`, затем постепенно подключать существующие Qwen repositories, Ollama clients и Krita process manager.

Root router остаётся статически собранным. Feature flags управляют heavy workers и внешними runtime после безопасного restart, а не горячей выгрузкой Python-модулей.

### Изменённые файлы

- `docs/heavy_runtime_inventory.md`;
- `docs/worklog/2026-07-18-heavy-runtime-inventory.md`;
- `docs/project_memory.md`;
- `docs/development_status.md`.

### Миграции и совместимость

Миграции отсутствуют. Production behavior, SQL, Telegram handlers, worker intervals, feature flags и Supervisor API не менялись.

### Проверки

Для head `c501847d74c4f007aa6172c4968913bebc6f3f37`:

- source audit через подключённый GitHub repository — выполнен;
- compare `main...agent/heavy-runtime-inventory` — ветка впереди на 4 commits, не отстаёт, изменены только 4 документационных файла;
- production diff — отсутствует;
- применённые миграции — не изменены;
- `project notes contract #91` — успешно;
- `tests #624` — успешно.

Локальные Windows/Ollama/Krita/Telegram checks не требуются для docs-only HR-1 и не выполнялись. Они остаются обязательными на соответствующих production-срезах.

### PR и commit

- draft PR: #124 `HR-1: инвентаризация тяжёлых runtime-компонентов`;
- ветка: `agent/heavy-runtime-inventory`;
- первый commit inventory: `20a903e7c39eb1db6e6df5978397f52ff13b7750`;
- зелёный CI head до финального закрытия worklog: `c501847d74c4f007aa6172c4968913bebc6f3f37`;
- финальный documentation commit запускает повторную проверку PR перед merge.

### Незавершённое

Обязательных пунктов HR-1 не осталось. До merge необходимо дождаться повторного CI после финальной записи worklog. Живые runtime-проверки относятся к будущим HR-срезам и не блокируют завершение docs-only inventory.

### Rollback-план

Закрыть PR #124 без merge или revert его документационные commits. Production-код, база и runtime при этом не затрагиваются.

### Следующий шаг

После merge HR-1 выполнить HR-2 отдельным PR: перенести feature flags и runtime timeouts в единый типизированный `Settings`, убрать прямое чтение `KRITA_WATERMARK_ENABLED` из `app.workers` и сохранить текущее поведение без изменения scheduling.
