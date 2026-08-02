# Сессия: AFK guardrails для Storage Librarian

- Дата: 2026-08-02
- ID: `storage-librarian-afk-guardrails-20260802`
- Линия/фаза: Telegram Storage Librarian, background rollout
- Статус: `частично`
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
- PR-ветка атомарно пересобрана от текущего `main` только из продуктовых blob и снова стала mergeable;
- generated contracts рассчитаны на точном synthetic merge и применены self-cleaning job;
- временные exporter/test workflow modifications удалены из конечной ветки;
- repository layout inventory пересчитан штатным генератором: 43 repository-модуля, 36 domain и 7 infrastructure.

### Миграции и совместимость

SQL-миграций нет. Existing tables, analyses и manual mode сохраняются. AFK включается отдельным явным скриптом. Обычный installer не включает background queue автоматически.

### Проверки

Подтверждено до финального чистого прогона:

- bounded mypy выполнялся успешно;
- project notes contract выполнялся успешно на продуктовой ветке;
- Docker workflow принял production Compose;
- focused AFK source tests выполняются;
- ложное распознавание слова `update` как SQL вне persistence layer устранено;
- package architecture inventory: 642 production modules, 140228 LOC, 548 registered violations/exemptions;
- repository layout inventory: 43 modules, 36 domain, 7 infrastructure;
- Telegram navigation inventory: 642 Python files, 1053 buttons, 0 violations;
- P2 stability schema 78: 105 broad boundaries, 105 approved, unresolved 0;
- штатные `tests.yml` и `scripts/ci_preflight.py` восстановлены из `main`.

Ожидается последний обычный прогон preflight, всех test shards, mypy, notes и Docker build на owner commit без временных CI-файлов.

### PR и commit

- ветка: `feat/storage-librarian-afk-guardrails`;
- PR: `#549`;
- clean product commit: `25817a4f03848e7222b692b33764c35af2800383`;
- generated package contracts commit: `b9cf358c30f01da4799fc475e54cb03ad98dda61`;
- generated repository layout commit: `a5a8ab5381075cf8853889005ee3ec8ac1c00c78`;
- backup старой истории: `backup/storage-librarian-afk-guardrails-20260802`;
- финальный зелёный head: ожидается после чистого CI;
- merge: только после отдельного разрешения владельца.

### Незавершённое

- финальный чистый CI;
- перевод PR из draft и merge;
- production pull/install;
- включение AFK через safe cutoff script;
- live smoke нового diagnostic/release объекта;
- наблюдение CPU/RAM/swap.

### Следующий шаг

Получить полностью зелёный CI, затем после разрешения слить PR и включить AFK new-only на production.
