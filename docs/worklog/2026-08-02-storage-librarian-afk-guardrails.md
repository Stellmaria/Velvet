# Сессия: AFK guardrails для Storage Librarian

- Дата: 2026-08-02
- ID: `storage-librarian-afk-guardrails-20260802`
- Линия/фаза: Telegram Storage Librarian, background rollout
- Статус: `проверка`
- Ветка: `feat/storage-librarian-afk-guardrails`
- Базовый commit: `42522af0a19d67333e6a0c423af4d6589b201b44`

## Перед началом

### Цель

Включить безопасный AFK new-only режим без массового анализа старого архива и без автоматических production-действий.

### Исходный контекст

- local Ollama и Librarian Hermes healthy;
- `qwen3.5:9b-q4_K_M` установлен;
- manual анализ работает;
- простой `STORAGE_LIBRARIAN_AUTO_ENQUEUE=true` мог выбрать старые объекты.

### Планируемый объём

- cutoff по текущему максимальному Storage ID;
- отдельные AFK-категории;
- один объект за цикл;
- enable/disable scripts;
- terminal failure report;
- tests, runbook и CI.

### Критерии готовности

- старые ID не ставятся в очередь;
- AFK по умолчанию анализирует только diagnostics/releases;
- manual commands сохраняются;
- терминальные ошибки публикуются очищенно;
- Librarian не выполняет restart/update/rollback;
- CI зелёный.

### Риски и ограничения

- CPU-only inference медленнее cloud;
- live smoke требует нового объекта после cutoff;
- Telegram report зависит от корректной topic-конфигурации.

## После завершения

### Фактически сделано

- добавлен `enqueue_newer_than` с обязательным положительным cutoff;
- existing jobs и analyses исключаются;
- scheduler больше не вызывает bulk `enqueue_pending`;
- `process_once` по умолчанию использует `auto_enqueue=False`;
- scheduler ждёт полный scan interval после одной итерации;
- добавлены `enable_afk.sh` и `disable_afk.sh`;
- enable script фиксирует текущий `MAX(telegram_storage_objects.id)` до включения AFK;
- статус показывает cutoff, AFK categories, batch и interval;
- terminal failure публикуется в Hermes Reports после исчерпания retry;
- failure report проходит redaction и не содержит raw source;
- Librarian не выполняет restart/update/rollback и не вызывает Каэля автоматически;
- добавлены focused tests и AFK runbook;
- открыт draft PR `#549`;
- подготовлена атомарная синхронизация с текущим `main`, включая повторную генерацию пересекающихся architecture contracts.

### Миграции и совместимость

SQL-миграций нет. Existing tables, analyses и manual mode сохраняются. AFK включается отдельным явным скриптом. Обычный installer не включает background queue автоматически.

### Проверки

Первый CI подтвердил:

- bounded mypy: зелёный;
- project notes contract: зелёный;
- AFK source tests дошли до выполнения;
- Docker workflow принял существующий production Compose;
- обнаружены и исправлены два локальных contract drift: буквальная проверка env mapping и ложное распознавание слова `update` как SQL вне persistence layer.

Generated contracts синхронизированы штатными генераторами:

- package architecture: 641 production module, 139904 LOC, 548 зарегистрированных violations/exemptions;
- P2 stability schema 78: 105 broad exception boundaries, все 105 approved, unresolved 0;
- временный contents-write workflow удалил себя в том же bot commit.

Ожидается синхронизация с Krita security commit текущего `main`, повторный пересчёт generated contracts и финальный чистый прогон preflight, всех test shards, mypy, notes и Docker build.

### PR и commit

- ветка: `feat/storage-librarian-afk-guardrails`;
- PR: `#549`;
- generated inventory commit: `5f0412823cd83f49705375c867f9efe5b6d72e89`;
- финальный зелёный head: ожидается после синхронизации с `main` и чистого CI;
- merge: только после отдельного разрешения владельца.

### Незавершённое

- синхронизация с текущим `main`;
- финальный чистый CI;
- перевод PR из draft и merge;
- production pull/install;
- включение AFK через safe cutoff script;
- live smoke нового diagnostic/release объекта;
- наблюдение CPU/RAM/swap.

### Следующий шаг

Завершить атомарный merge `main`, получить полностью зелёный CI, затем после разрешения слить PR и включить AFK new-only на production.
