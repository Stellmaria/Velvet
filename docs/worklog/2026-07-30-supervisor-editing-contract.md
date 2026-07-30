# 2026-07-30 — Supervisor editing contract

- Дата: 2026-07-30
- ID: `supervisor-editing-contract`
- Issue: #419
- Линия/фаза: P3 shared helper family migration
- Статус: `частично`
- Ветка: `agent/shared-helper-safe-edit-family`
- Базовый commit: `0b2a9b32385ad287ee2b4469ad491fd4e1e090c6`

## Перед началом

### Цель

Убрать private cross-module contract `_safe_edit` между focused Supervisor routers и
`supervisor.views`, сохранив точное Telegram editing behavior через уже слитый shared
contract.

### Исходный контекст

После foundation PR #462 package-wide inventory фиксировал несколько прямых импортов
`_safe_edit` из `velvet_bot.presentation.telegram.supervisor.views`. Сам helper уже
делегировал в canonical `safe_edit_message_text`, но внешние routers продолжали зависеть
от приватного имени presentation-модуля.

### Планируемый объём

- создать публичный Supervisor editing adapter;
- перевести status, process, git, logs, console, self-control и Codex routers;
- удалить неиспользуемый private import из composition router;
- сохранить тексты, клавиатуры, callback payloads и Supervisor I/O behavior;
- добавить AST regression против возврата private import;
- пересобрать shared contract inventory и выполнить полный CI.

### Критерии готовности

- Supervisor routers не импортируют `_safe_edit` из `supervisor.views`;
- все реальные editing consumers используют `edit_supervisor_message`;
- adapter делегирует в `safe_edit_message_text` без изменения аргументов;
- callback и error semantics не меняются;
- versioned inventory отражает уменьшение private debt;
- полный repository CI проходит.

### Риски и ограничения

Срез не меняет Supervisor UX, команды, права, remote I/O или lifecycle операций. Другие
private view helpers не мигрируются попутно: смешивание нескольких families в одном PR
снова создало бы дифф, который можно только принять на веру, любимый жанр плохих PR.

## После завершения

### Фактически сделано

- добавлен публичный `supervisor.editing.edit_supervisor_message`;
- logs, status, process, git, self-control, Codex и console routers переведены на него;
- composition router больше не импортирует неиспользуемый `_safe_edit`;
- добавлен AST regression, перечисляющий семь публичных consumers;
- wrapper contract покрыт async delegation test.

### Миграции и совместимость

Миграций базы данных нет. Тексты, клавиатуры, callback payloads, подтверждения,
SupervisorClient calls и exception boundaries не изменены. Private `_safe_edit` пока
может оставаться локальной деталью `views.py` для внутреннего consumer, но больше не
является межмодульным контрактом.

### Проверки

- focused contract tests: ожидают запуск в CI;
- package-wide inventory: ожидает пересборку;
- full unit tests: ожидают запуск;
- type check: ожидает запуск;
- Docker build: ожидает запуск;
- project notes contract: ожидает запуск.

### PR и commit

- ветка: `agent/shared-helper-safe-edit-family`;
- PR будет открыт после фиксации code/test/worklog scope;
- итоговый merge commit будет указан после зелёного CI.

### Незавершённое

- пересобрать JSON/Markdown shared inventory;
- получить зелёный полный CI;
- завершить review и слить family-срез;
- продолжить active installer safe-edit/state migrations отдельным PR.

### Следующий шаг

Открыть draft PR, получить точный generated inventory delta и обновить versioned
contracts безопасным read-only способом. После слияния перейти к private safe-edit и
state access в active Ауф installers, не затрагивая progress/media structural work из
#455/#457.
