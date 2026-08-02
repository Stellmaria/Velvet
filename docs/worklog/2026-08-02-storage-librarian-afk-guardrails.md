# Сессия: AFK guardrails для Storage Librarian

- Дата: 2026-08-02
- ID: `storage-librarian-afk-guardrails-20260802`
- Линия/фаза: Telegram Storage Librarian, background rollout
- Статус: `частично`
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
- scheduler ждёт полный scan interval после одной итерации;
- добавлены `enable_afk.sh` и `disable_afk.sh`;
- статус показывает cutoff, AFK categories, batch и interval;
- terminal failure публикуется в Hermes Reports;
- добавлены focused tests и AFK runbook.

### Миграции и совместимость

SQL-миграций нет. Existing tables и manual mode сохраняются. AFK включается отдельным скриптом.

### Проверки

Ожидаются Python compile, bash syntax, focused tests, architecture preflight, type check, notes contract и Docker build.

### PR и commit

- ветка: `feat/storage-librarian-afk-guardrails`;
- PR: ожидается после проверок;
- merge: только после отдельного разрешения владельца.

### Незавершённое

- CI;
- generated inventories при необходимости;
- draft PR;
- production rollout и live smoke.

### Следующий шаг

Запустить focused checks, исправить фактические failures и открыть draft PR.
