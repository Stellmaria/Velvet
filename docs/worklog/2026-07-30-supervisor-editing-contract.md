# 2026-07-30 — Supervisor editing contract

- Дата: 2026-07-30
- ID: `supervisor-editing-contract`
- Issue: #419
- Линия/фаза: P3 shared helper family migration
- Статус: `завершено`
- Ветка: `agent/shared-helper-safe-edit-family`
- Базовый commit: `0b2a9b32385ad287ee2b4469ad491fd4e1e090c6`

## Перед началом

### Цель

Убрать private cross-module contract `_safe_edit` между focused Supervisor routers и
`supervisor.views`, сохранив точное Telegram editing behavior через уже слитый shared
contract.

### Исходный контекст

После foundation PR #462 package-wide inventory фиксировал восемь прямых импортов
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
- старые tests переведены с patch приватного имени на public editing dependency;
- добавлен AST regression, перечисляющий семь публичных consumers;
- wrapper contract покрыт async delegation test;
- versioned shared inventory и Telegram navigation inventory пересобраны;
- временный inventory workflow и artifact-dump удалены до итогового CI.

### Миграции и совместимость

Миграций базы данных нет. Тексты, клавиатуры, callback payloads, подтверждения,
SupervisorClient calls и exception boundaries не изменены. Private `_safe_edit` может
оставаться локальной деталью `views.py` для внутреннего consumer, но больше не является
межмодульным контрактом.

Package-wide baseline изменился следующим образом:

- production Python files: 594 → 595;
- functions inventoried: 3304 → 3305;
- registered private cross-module debt: 152 → 144;
- Supervisor private `_safe_edit` accesses: 8 → 0;
- blocking known private contracts: 0 → 0;
- exact/normalized/semantic groups: 56 / 92 / 9 без изменения.

### Проверки

Для чистого head `a0273d49e7a127211fb8384171092da9cba85752` успешно прошли:

- full unit tests: 1758 tests;
- type check;
- Docker build;
- project notes contract;
- AST regression public Supervisor editing consumers;
- package-wide inventory validation;
- generated Telegram navigation inventory contract.

### PR и commit

- PR: #468;
- ветка: `agent/shared-helper-safe-edit-family`;
- проверенный clean head: `a0273d49e7a127211fb8384171092da9cba85752`;
- итоговый squash merge commit будет зафиксирован GitHub после merge.

### Незавершённое

- слить PR #468 после повторного notes-only CI;
- продолжить #419 active installer safe-edit/state family отдельным PR;
- не смешивать следующий срез с progress/media structural work из #455/#457.

### Следующий шаг

После merge PR #468 открыть следующий reviewable family-срез для private safe-edit и
state access в active Ауф installers. Versioned inventory с baseline 144 использовать
как измеримую отправную точку, а не как декоративную цифру для архитектурного отчёта.
