# Сессия: AFK guardrails для Storage Librarian

- Дата: 2026-08-02
- ID: `storage-librarian-afk-guardrails-20260802`
- Линия/фаза: Telegram Storage Librarian, background rollout
- Статус: `проверка`
- Ветка: `feat/storage-librarian-afk-guardrails`
- Базовый commit: `c54026f9f313607abc3e680ac1e5e5e05649972a`

## Перед началом

### Цель

Включить безопасный AFK new-only режим без массового анализа старого архива и без автоматических production-действий.

### Исходный контекст

- local Ollama и Librarian Hermes healthy;
- `qwen3.5:9b-q4_K_M` установлен;
- manual анализ работает;
- простой `STORAGE_LIBRARIAN_AUTO_ENQUEUE=true` мог выбрать старые объекты;
- AFK enqueue без отдельного claim-filter мог забрать старую ранее созданную job.

### Планируемый объём

- cutoff по текущему максимальному Storage ID;
- отдельные AFK-категории;
- один объект за цикл;
- cutoff и на enqueue, и на claim;
- enable/disable scripts;
- terminal failure report;
- tests, runbook и CI.

### Критерии готовности

- старые ID не ставятся и не забираются из очереди AFK-worker;
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
- добавлен отдельный `StorageLibrarianAfkRepository`, который не может claim-ить `storage_object_id <= cutoff`;
- AFK service использует cutoff-filtered repository, manual service остаётся unrestricted;
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
- конфликтовавшая история сохранена в `backup/storage-librarian-afk-guardrails-20260802`;
- PR-ветка атомарно пересобрана от текущего `main` только из 11 продуктовых blob и снова стала mergeable.

### Миграции и совместимость

SQL-миграций нет. Existing tables, analyses и manual mode сохраняются. AFK включается отдельным явным скриптом. Обычный installer не включает background queue автоматически.

### Проверки

Первый CI подтвердил:

- bounded mypy: зелёный;
- project notes contract: зелёный;
- Docker workflow принял production Compose;
- исправлены локальные contract drift и ложное распознавание слова `update` как SQL вне persistence layer.

Сейчас штатный генератор пересчитывает package architecture и P2 stability inventory по конечному дереву без временного workflow-файла. После bot commit требуется финальный обычный owner commit и полный чистый CI.

### PR и commit

- ветка: `feat/storage-librarian-afk-guardrails`;
- PR: `#549`;
- clean product commit: `25817a4f03848e7222b692b33764c35af2800383`;
- backup старой истории: `backup/storage-librarian-afk-guardrails-20260802`;
- финальный зелёный head: ожидается после inventory sync и чистого CI;
- merge: только после отдельного разрешения владельца.

### Незавершённое

- generated inventory sync;
- финальный чистый CI;
- перевод PR из draft и merge;
- production pull/install;
- включение AFK через safe cutoff script;
- live smoke нового diagnostic/release объекта;
- наблюдение CPU/RAM/swap.

### Следующий шаг

Дождаться атомарного inventory commit, запустить чистый CI, затем после разрешения слить PR и включить AFK new-only на production.
