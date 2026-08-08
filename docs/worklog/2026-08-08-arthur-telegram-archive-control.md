# Arthur Telegram archive control

- Дата: 2026-08-08
- ID: `2026-08-08-arthur-telegram-archive-control`
- Линия/фаза: Storage Librarian / Arthur owner controls
- Статус: `завершено`
- Ветка: `feat/arthur-archive-control`
- Базовый commit: `a84724836bcc603f0e609d1f58e1f1776e6eae3a`

## Перед началом

### Цель

Перенести ручное управление полным Storage Librarian archive loop из SSH lifecycle в owner-only Telegram bot Arthur: владелец должен иметь возможность явно запустить, проверить и мягко остановить архивный анализ без изменения `.env.server`, Docker pause или recreate runtime services.

### Исходный контекст

Production full-archive backfill был ранее включён через server lifecycle, затем остановлен штатным `disable_afk.sh`. Для полного повторного прохода была установлена отдельная `STORAGE_LIBRARIAN_ANALYZER_VERSION`, а существующие jobs были возвращены в `queued`. Arthur уже имел owner-only Telegram интерфейс, PostgreSQL repository и локальный Ollama analysis path, но массовый архивный цикл из самого Arthur отсутствовал. Работа началась от `9a3770db95ef820c0f36e2c07a7e7c9315279e0d`; до merge `main` продвинулся PR #741, поэтому финальная ветка была пересобрана поверх `a84724836bcc603f0e609d1f58e1f1776e6eae3a` без потери Arthur-first VL priority изменений.

### Планируемый объём

- добавить `/archive start`, `/archive stop` и `/archive status` в Arthur Telegram bot;
- оставить `STORAGE_LIBRARIAN_AUTO_ENQUEUE=false` как deployment boundary;
- запускать `enqueue_pending()` только по явной owner-команде внутри Arthur process;
- сделать stop cooperative, чтобы текущий Storage object завершался до остановки loop;
- сериализовать manual `/analyze` и archive inference общим lock;
- корректно завершать archive task при shutdown Arthur;
- добавить regression tests и обновить Arthur runbook.

### Критерии готовности

- owner может запустить полный архив через Telegram без SSH;
- повторный `/archive start` идемпотентен;
- `/archive stop` не отменяет inference посреди объекта и не оставляет intentional half-run state;
- `/archive status` показывает state, analyzer version и queue counters;
- env auto-enqueue остаётся false и Arthur не получает Docker/systemd control;
- required CI проходит перед merge.

### Риски и ограничения

`/archive start` использует текущую `STORAGE_LIBRARIAN_ANALYZER_VERSION`. Уже завершённые объекты этой же версии повторно не анализируются; для намеренного full rescan требуется новая analyzer generation. Cooperative stop может некоторое время отображаться как `stopping`, пока завершается текущий объект. Изменение не даёт Arthur Docker socket или host-control privileges.

## После завершения

### Фактически сделано

Arthur получил explicit owner-only `/archive start|stop|status`. Archive loop вызывает `enqueue_pending()` маленькими порциями и обрабатывает Storage jobs через существующий local Ollama path. Environment-driven AFK остаётся отключённым.

Stop реализован через `asyncio.Event`: команда не отменяет текущий inference, а просит loop завершиться на ближайшей границе объекта. Manual `/analyze` и archive loop используют один `asyncio.Lock`, поэтому Arthur не запускает два Storage inference одновременно. Runtime shutdown сначала просит archive loop остановиться, затем закрывает Telegram session и database.

### Миграции и совместимость

SQL-миграций нет. Формат persistent Storage, job rows и analysis rows не меняется. `.env.server` и Compose policy `STORAGE_LIBRARIAN_AUTO_ENQUEUE=false` не меняются. Команды `/analyze`, `/result`, `/ask`, `/digest`, `/queue` и `/download` сохраняются.

### Проверки

Добавлен `tests/test_arthur_archive_control.py` с async lifecycle checks для idempotent start/cooperative stop и source contracts для Telegram wiring, runtime shutdown, enqueue path, shared inference lock и трёх archive reply controls. Existing Arthur phase-2 deployment contracts продолжают требовать auto-enqueue=false и isolated container privileges.

Первый CI выявил две governance-регрессии: новый archive handler увеличивал `build_arthur_router()` выше лимита 180 строк, а broad `Exception` менял P2 stability inventory. Handler вынесен в отдельный registration helper внутри существующего модуля, а archive loop теперь ловит только конкретные Librarian/PostgreSQL/aiohttp/IO/value/timeout ошибки. Telegram navigation inventory обновлён с учётом трёх новых reply controls.

После merge PR #741 ветка была пересобрана поверх актуального `main`. Канонический package architecture inventory повторно сгенерирован для объединённого дерева одноразовым self-removing GitHub Actions helper; временный workflow удалён самим helper и отсутствует на финальном head.

### PR и commit

PR #742 `Add Telegram archive controls to Arthur` публикуется из `feat/arthur-archive-control` в `main`. Merge выполняется только после зелёного required CI на human-authored финальном head.

### Незавершённое

Production deploy Arthur после merge не входит в сам PR. Пока новая ревизия не задеплоена на VPS, Telegram bot на production не увидит `/archive` command.

### Следующий шаг

После merge выполнить canonical production update/reconcile, затем проверить `/archive status`, `/archive start` и `/archive stop` в реальном Arthur Telegram bot.
